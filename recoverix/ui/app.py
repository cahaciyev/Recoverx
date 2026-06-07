"""Main application window, navigation and shared state."""
from __future__ import annotations

import threading
from tkinter import messagebox

import customtkinter as ctk

from . import theme
from ..core.logging_setup import get_logger
from ..core.database import Database
from ..core.devices import describe_size
from ..core.scanner import ScanConfig, Scanner, MODE_IMAGE, MODE_LOST
from .screens.complete import CompleteScreen
from .screens.device_select import DeviceSelectScreen
from .screens.recovery_dest import RecoveryDestScreen
from .screens.results import ResultsScreen
from .screens.scan_mode import ScanModeScreen
from .screens.scan_progress import ScanProgressScreen
from .screens.welcome import WelcomeScreen
from .. import __version__

log = get_logger("ui")


class RecoverixApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(f"Recoverix - Data Recovery  v{__version__}")
        self.geometry("1080x720")
        self.minsize(960, 640)

        self.db = Database()
        theme.init_appearance(self.db.get_pref("appearance", "dark"))

        # shared state
        self.source: dict | None = None
        self.scanner: Scanner | None = None
        self.scan_logs: list[str] = []
        self.scan_mode_default: str | None = None
        self.pending_recovery: list = []
        self.recovery_result = None
        self.recovery_cancel = threading.Event()
        self._scan_thread: threading.Thread | None = None

        self._build_chrome()
        self._build_screens()
        self.show("welcome")
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # -- chrome ------------------------------------------------------------
    def _build_chrome(self) -> None:
        bar = ctk.CTkFrame(self, height=56, corner_radius=0, fg_color=theme.CARD)
        bar.pack(fill="x", side="top")
        ctk.CTkLabel(bar, text="  Recoverix", font=theme.font(18, "bold")).pack(side="left", padx=12)
        ctk.CTkLabel(bar, text="read-only - offline", font=theme.font(11),
                     text_color=theme.MUTED).pack(side="left", padx=8)

        ctk.CTkButton(bar, text="Theme", width=80, height=32, command=self._toggle_theme,
                      fg_color="transparent", border_width=1, border_color=theme.CARD_BORDER,
                      text_color=theme.MUTED, hover_color=theme.SURFACE).pack(side="right", padx=8)
        ctk.CTkButton(bar, text="Privacy & Limits", width=130, height=32, command=self._about,
                      fg_color="transparent", border_width=1, border_color=theme.CARD_BORDER,
                      text_color=theme.MUTED, hover_color=theme.SURFACE).pack(side="right", padx=4)

        self.container = ctk.CTkFrame(self, fg_color="transparent")
        self.container.pack(fill="both", expand=True)

    def _build_screens(self) -> None:
        self.screens: dict[str, ctk.CTkFrame] = {}
        for cls in (WelcomeScreen, DeviceSelectScreen, ScanModeScreen, ScanProgressScreen,
                    ResultsScreen, RecoveryDestScreen, CompleteScreen):
            screen = cls(self.container, self)
            self.screens[cls.name] = screen
            screen.place(relx=0, rely=0, relwidth=1, relheight=1)

    # -- navigation --------------------------------------------------------
    def show(self, name: str) -> None:
        screen = self.screens[name]
        screen.tkraise()
        if hasattr(screen, "on_show"):
            screen.on_show()

    # -- state helpers -----------------------------------------------------
    def set_source(self, device, partition) -> None:
        is_image = getattr(device, "is_image", False)
        name = device.name if (is_image or partition is None) else (
            f"{device.name} - {partition.drive_letter + ':' if partition.drive_letter else 'partition'}"
            f" ({partition.file_system or 'Unknown'})")
        self.source = {
            "device": device,
            "partition": partition,
            "name": name,
            "is_image": is_image,
            "is_ssd": getattr(device, "is_ssd", False),
            "type": "Disk image" if is_image else (device.media_type or device.bus_type or "Disk"),
            # path/size/sector are finalised in start_scan
            "path": device.path,
            "size": device.size_bytes,
            "sector": device.sector_size,
        }

    def _effective_config(self, mode: str) -> ScanConfig:
        src = self.source
        device = src["device"]
        partition = src["partition"]
        sector = device.sector_size
        if mode == MODE_IMAGE or src["is_image"]:
            path, size, start, end = device.path, device.size_bytes, 0, device.size_bytes
        elif mode == MODE_LOST or partition is None:
            path, size, start, end = device.path, device.size_bytes, 0, device.size_bytes
        elif partition.path:
            path, size, start, end = partition.path, partition.size_bytes, 0, partition.size_bytes
        else:
            # partition without a drive letter: read it via the whole device + offset
            path, size = device.path, device.size_bytes
            start, end = partition.offset_bytes, partition.offset_bytes + partition.size_bytes
        # finalise source paths used by preview/recovery
        self.source.update({"path": path, "size": size, "sector": sector})
        return ScanConfig(
            source_path=path, source_id=device.id, source_name=src["name"], mode=mode,
            size_bytes=size, sector_size=sector, start_offset=start, end_offset=end,
        )

    def start_scan(self, mode: str) -> None:
        cfg = self._effective_config(mode)
        self.scanner = Scanner(cfg)
        self.scan_logs = []

        def worker():
            try:
                self.scanner.run(on_log=lambda m: self.scan_logs.append(m))
            except Exception as exc:  # noqa: BLE001
                self.scan_logs.append(f"ERROR: {exc}")
                self.scanner.status = "error"
                self.after(0, lambda: messagebox.showerror(
                    "Scan error",
                    f"Could not scan the source.\n\n{exc}\n\n"
                    "Physical disks require running Recoverix as Administrator."))

        self._scan_thread = threading.Thread(target=worker, daemon=True)
        self._scan_thread.start()
        self.show("scan_progress")

    def persist_session(self) -> None:
        if self.scanner:
            try:
                self.db.save_session(self.scanner)
            except Exception as exc:  # noqa: BLE001
                log.warning("Failed to persist session: %s", exc)

    # -- chrome actions ----------------------------------------------------
    def _toggle_theme(self) -> None:
        mode = theme.toggle_mode()
        self.db.set_pref("appearance", mode)

    def _about(self) -> None:
        messagebox.showinfo(
            "Privacy & Limitations",
            "Recoverix runs fully offline. It never uploads your files, sends telemetry, "
            "or writes to the source disk.\n\n"
            "Limitations:\n"
            "- Recovery is never guaranteed.\n"
            "- Overwritten data cannot be recovered.\n"
            "- SSD TRIM may make deleted data unrecoverable.\n"
            "- Physically damaged drives may require a lab.\n"
            "- Fragmented large files may recover only partially.\n\n"
            "Logs and history are stored locally and can be cleared from the database folder.")

    def _on_close(self) -> None:
        if self.scanner and self.scanner.status == "running":
            if not messagebox.askyesno("Quit", "A scan is running. Stop it and quit?"):
                return
            self.scanner.request_cancel()
        try:
            self.db.close()
        except Exception:  # noqa: BLE001
            pass
        self.destroy()


def run() -> None:
    app = RecoverixApp()
    app.mainloop()
