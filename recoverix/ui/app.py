"""Main application window, navigation and shared state."""
from __future__ import annotations

import threading
from tkinter import messagebox

import customtkinter as ctk

from . import theme
from . import i18n
from .i18n import t
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
        i18n.set_language(self.db.get_pref("language", "en"))
        self._current = "welcome"

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
        self._ro_label = ctk.CTkLabel(bar, text=t("read-only - offline"), font=theme.font(11),
                                      text_color=theme.MUTED)
        self._ro_label.pack(side="left", padx=8)

        # Sun/Moon theme toggle (no text label).
        self._theme_btn = ctk.CTkButton(
            bar, text=self._theme_glyph(), width=40, height=32, command=self._toggle_theme,
            font=theme.font(16), fg_color="transparent", border_width=1,
            border_color=theme.CARD_BORDER, text_color=theme.MUTED, hover_color=theme.SURFACE)
        self._theme_btn.pack(side="right", padx=8)
        # Language selector.
        self._lang_menu = ctk.CTkOptionMenu(
            bar, values=[name for name, _ in i18n.LANGUAGES], width=120, height=32,
            command=self._on_language)
        self._lang_menu.set(i18n.current_name())
        self._lang_menu.pack(side="right", padx=6)
        self._privacy_btn = ctk.CTkButton(
            bar, text=t("Privacy & Limits"), width=140, height=32, command=self._about,
            fg_color="transparent", border_width=1, border_color=theme.CARD_BORDER,
            text_color=theme.MUTED, hover_color=theme.SURFACE)
        self._privacy_btn.pack(side="right", padx=4)

        # Credit footer (visible on every screen).
        footer = ctk.CTkFrame(self, height=26, corner_radius=0, fg_color=theme.CARD)
        footer.pack(fill="x", side="bottom")
        ctk.CTkLabel(footer, text="Developed by Jaweed", font=theme.font(11, "bold"),
                     text_color=theme.MUTED).pack(side="right", padx=16, pady=2)

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
        self._current = name
        screen = self.screens[name]
        screen.tkraise()
        if hasattr(screen, "on_show"):
            screen.on_show()

    def _theme_glyph(self) -> str:
        return "☀" if ctk.get_appearance_mode() == "Dark" else "\U0001F319"  # sun / moon

    def _on_language(self, name: str) -> None:
        code = i18n.code_for_name(name)
        i18n.set_language(code)
        self.db.set_pref("language", code)
        self._ro_label.configure(text=t("read-only - offline"))
        self._privacy_btn.configure(text=t("Privacy & Limits"))
        self.rebuild_screens()

    def rebuild_screens(self) -> None:
        """Recreate all screens so every string reflects the current language."""
        cur = self._current
        for screen in list(self.screens.values()):
            screen.destroy()
        self._build_screens()
        self.show(cur if cur in self.screens else "welcome")

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
                    t("Scan error"), t("scan_error_body", err=exc)))

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
        self._theme_btn.configure(text=self._theme_glyph())
        # Native (non-CTk) widgets don't auto-recolour on appearance change.
        for screen in self.screens.values():
            if hasattr(screen, "on_theme_changed"):
                try:
                    screen.on_theme_changed()
                except Exception:  # noqa: BLE001
                    pass

    def _about(self) -> None:
        messagebox.showinfo(t("Privacy & Limitations"), t("about_body"))

    def _on_close(self) -> None:
        if self.scanner and self.scanner.status == "running":
            if not messagebox.askyesno(t("Quit"), t("A scan is running. Stop it and quit?")):
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
