"""Recovery complete screen."""
from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime

import customtkinter as ctk

from .. import theme
from ..base import Screen
from ..i18n import t
from ..widgets import Banner, Card, Heading, StatChip, ghost_button, primary_button
from ...core.devices import describe_size
from ...core.dialogs import ask_save_file


class CompleteScreen(Screen):
    name = "complete"

    def build(self) -> None:
        wrap = ctk.CTkFrame(self, fg_color="transparent")
        wrap.pack(fill="both", expand=True, padx=40, pady=30)

        Heading(wrap, t("Recovery complete"),
                t("Your files have been written to the destination folder.")).pack(anchor="w")

        stats = ctk.CTkFrame(wrap, fg_color="transparent")
        stats.pack(fill="x", pady=20)
        stats.grid_columnconfigure((0, 1, 2), weight=1, uniform="s")
        self.chip_ok = StatChip(stats, t("Recovered"))
        self.chip_fail = StatChip(stats, t("Failed"))
        self.chip_size = StatChip(stats, t("Written"))
        for i, c in enumerate((self.chip_ok, self.chip_fail, self.chip_size)):
            c.grid(row=0, column=i, sticky="nsew", padx=8)

        dest_card = Card(wrap)
        dest_card.pack(fill="x", pady=8)
        ctk.CTkLabel(dest_card, text=t("Destination"), font=theme.font(12), text_color=theme.MUTED).pack(
            anchor="w", padx=16, pady=(12, 0))
        self.dest_lbl = ctk.CTkLabel(dest_card, text="", font=theme.font(13, "bold"), anchor="w")
        self.dest_lbl.pack(anchor="w", padx=16, pady=(0, 12))

        self.fail_banner = Banner(wrap, "", kind="warning")

        btns = ctk.CTkFrame(wrap, fg_color="transparent")
        btns.pack(fill="x", pady=16)
        primary_button(btns, t("Open Folder"), self._open_folder, width=170).pack(side="left")
        primary_button(btns, t("Recover More Files"), self._back_to_results, width=190).pack(side="left", padx=10)
        ghost_button(btns, t("Export Report"), self._export, width=160).pack(side="left", padx=(0, 10))
        ghost_button(btns, t("New Scan"), lambda: self.app.show("welcome"), width=130).pack(side="left")

    def on_show(self) -> None:
        r = self.app.recovery_result
        if not r:
            return
        self.chip_ok.set(str(r.recovered))
        self.chip_fail.set(str(r.failed))
        self.chip_size.set(describe_size(r.bytes_written))
        self.dest_lbl.configure(text=r.destination)

        notes = []
        if getattr(r, "repaired", 0):
            notes.append(t("{n} file(s) were repaired so they open correctly.", n=r.repaired))
        if r.failed:
            notes.append(t("{n} file(s) failed to recover.", n=r.failed))
        if getattr(r, "unopenable", 0):
            notes.append(t("{n} recovered file(s) still do not open "
                           "(the original data was incomplete or overwritten).", n=r.unopenable))
        if notes:
            notes.append(t("See the activity log for details."))
            self.fail_banner.set_text("  ".join(notes))
            self.fail_banner.pack(fill="x", pady=6)
        else:
            self.fail_banner.pack_forget()

    def _back_to_results(self) -> None:
        """Return to the results screen keeping the existing scan intact."""
        self.app.show("results")

    def _open_folder(self) -> None:
        r = self.app.recovery_result
        if r and os.path.isdir(r.destination):
            try:
                os.startfile(r.destination)  # noqa: S606 - Windows explorer
            except Exception:  # noqa: BLE001
                subprocess.Popen(["explorer", r.destination])

    def _export(self) -> None:
        r = self.app.recovery_result
        sc = self.app.scanner
        if not r:
            return
        path = ask_save_file(
            title=t("Export Report"),
            filter_str="JSON report (*.json)|*.json|Text report (*.txt)|*.txt",
            default_ext="json",
            initial_file=f"recoverix_report_{datetime.now():%Y%m%d_%H%M%S}.json",
        )
        if not path:
            return
        report = {
            "app": "Recoverix",
            "generated": datetime.now().isoformat(timespec="seconds"),
            "session_id": sc.session_id if sc else None,
            "source": self.app.source.get("name") if self.app.source else None,
            "scan_mode": sc.config.mode if sc else None,
            "files_found": len(sc.results) if sc else 0,
            "recovered": r.recovered,
            "failed": r.failed,
            "bytes_written": r.bytes_written,
            "destination": r.destination,
            "failures": r.failures,
        }
        with open(path, "w", encoding="utf-8") as fh:
            if path.lower().endswith(".txt"):
                for k, v in report.items():
                    fh.write(f"{k}: {v}\n")
            else:
                json.dump(report, fh, indent=2)
        self.app.scan_logs.append(f"Report exported to {path}")
