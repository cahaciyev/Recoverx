"""Scan-progress screen with live stats and logs."""
from __future__ import annotations

import customtkinter as ctk

from .. import theme
from ..base import Screen
from ..i18n import t
from ..widgets import Card, Heading, StatChip, ghost_button, primary_button
from ...core.devices import describe_size
from ...core.scanner import MODE_LABELS


def _fmt_time(seconds: float) -> str:
    s = int(seconds)
    if s < 60:
        return f"{s}s"
    if s < 3600:
        return f"{s // 60}m {s % 60}s"
    return f"{s // 3600}h {(s % 3600) // 60}m"


class ScanProgressScreen(Screen):
    name = "scan_progress"

    def build(self) -> None:
        self._polling = False
        self._log_len = 0

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=30, pady=(24, 6))
        self.heading = Heading(top, t("Scanning..."), "")
        self.heading.pack(anchor="w")

        self.bar = ctk.CTkProgressBar(self, height=16, corner_radius=8)
        self.bar.pack(fill="x", padx=30, pady=(10, 4))
        self.bar.set(0)
        self.pct = ctk.CTkLabel(self, text="0%", font=theme.font(12), text_color=theme.MUTED)
        self.pct.pack(anchor="w", padx=30)

        stats = ctk.CTkFrame(self, fg_color="transparent")
        stats.pack(fill="x", padx=30, pady=10)
        stats.grid_columnconfigure((0, 1, 2, 3), weight=1, uniform="s")
        self.chip_scanned = StatChip(stats, t("Scanned"))
        self.chip_total = StatChip(stats, t("Total"))
        self.chip_found = StatChip(stats, t("Files found"))
        self.chip_eta = StatChip(stats, t("Est. remaining"))
        for i, c in enumerate((self.chip_scanned, self.chip_total, self.chip_found, self.chip_eta)):
            c.grid(row=0, column=i, sticky="nsew", padx=6)

        self.types_lbl = ctk.CTkLabel(self, text=t("Detected types: -"), font=theme.font(12),
                                      text_color=theme.MUTED, anchor="w")
        self.types_lbl.pack(anchor="w", padx=30, pady=(0, 6))

        logcard = Card(self)
        logcard.pack(fill="both", expand=True, padx=30, pady=(4, 8))
        ctk.CTkLabel(logcard, text=t("Activity log"), font=theme.font(13, "bold")).pack(
            anchor="w", padx=16, pady=(12, 4))
        self.logbox = ctk.CTkTextbox(logcard, font=theme.font(11), activate_scrollbars=True)
        self.logbox.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self.logbox.configure(state="disabled")

        nav = ctk.CTkFrame(self, fg_color="transparent")
        nav.pack(fill="x", padx=30, pady=(4, 20))
        self.pause_btn = ghost_button(nav, t("Pause"), self._toggle_pause, width=130)
        self.pause_btn.pack(side="left")
        self.stop_btn = ghost_button(nav, t("Stop"), self._stop, width=130,
                                     text_color=theme.DANGER)
        self.stop_btn.pack(side="left", padx=10)
        self.results_btn = primary_button(nav, f"{t('View Results')} >", lambda: self.app.show("results"),
                                          width=180, state="disabled")
        self.results_btn.pack(side="right")

    def on_show(self) -> None:
        sc = self.app.scanner
        if not sc:
            return
        self.heading.winfo_children()[0].configure(text=t(MODE_LABELS.get(sc.config.mode, "Scanning...")))
        self._log_len = 0
        self.logbox.configure(state="normal")
        self.logbox.delete("1.0", "end")
        self.logbox.configure(state="disabled")
        self.bar.set(0)
        self.results_btn.configure(state="disabled")
        self.pause_btn.configure(text=t("Pause"))
        self._polling = True
        self._poll()

    def _poll(self) -> None:
        if not self._polling:
            return
        sc = self.app.scanner
        if sc is None:
            return
        p = sc.progress
        self.bar.set(p.percent / 100.0)
        self.pct.configure(text=f"{p.percent:.1f}%")
        self.chip_scanned.set(describe_size(p.scanned_bytes))
        self.chip_total.set(describe_size(p.total_bytes))
        self.chip_found.set(str(p.files_found))
        self.chip_eta.set(_fmt_time(p.eta_s) if p.eta_s else "-")

        if p.type_counts:
            top = sorted(p.type_counts.items(), key=lambda kv: -kv[1])[:8]
            self.types_lbl.configure(text=t("Detected types: ") +
                                     ", ".join(f"{k} ({v})" for k, v in top))

        logs = self.app.scan_logs
        if len(logs) > self._log_len:
            new = logs[self._log_len:]
            self._log_len = len(logs)
            self.logbox.configure(state="normal")
            for line in new:
                self.logbox.insert("end", line + "\n")
            self.logbox.see("end")
            self.logbox.configure(state="disabled")

        if sc.status in ("completed", "cancelled", "error"):
            self._polling = False
            self.results_btn.configure(state="normal")
            self.pause_btn.configure(state="disabled")
            self.stop_btn.configure(state="disabled")
            if sc.status == "completed":
                self.app.persist_session()
                self.app.show("results")
            return
        self.after(250, self._poll)

    def _toggle_pause(self) -> None:
        sc = self.app.scanner
        if not sc:
            return
        paused = sc.toggle_pause()
        self.pause_btn.configure(text=t("Resume") if paused else t("Pause"))

    def _stop(self) -> None:
        sc = self.app.scanner
        if sc:
            sc.request_cancel()
