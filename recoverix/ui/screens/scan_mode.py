"""Scan-mode selection screen."""
from __future__ import annotations

import customtkinter as ctk

from .. import theme
from ..base import Screen
from ..widgets import Banner, Card, Heading, ghost_button, primary_button
from ...core.scanner import MODE_DEEP, MODE_IMAGE, MODE_LOST, MODE_QUICK

_MODES = [
    (MODE_QUICK, "Quick Scan",
     "Fast signature pass over the first region. Best for recently deleted files."),
    (MODE_DEEP, "Deep Scan",
     "Full read-only scan with raw file carving. Best for formatted or corrupted media."),
    (MODE_LOST, "Lost Partition Scan",
     "Probe the whole device for boot sectors / partitions, then carve. Use when partitions are gone."),
    (MODE_IMAGE, "Disk Image Scan",
     "Carve a disk image file (.img/.dd/.raw/.iso) instead of a physical disk."),
]


class ScanModeScreen(Screen):
    name = "scan_mode"

    def build(self) -> None:
        self._selected = None
        self._cards = {}

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=30, pady=(24, 8))
        Heading(top, "Choose a scan mode",
                "Each mode reads the source only - it never writes to it.").pack(anchor="w")

        self.source_lbl = ctk.CTkLabel(self, text="", font=theme.font(12), text_color=theme.MUTED)
        self.source_lbl.pack(anchor="w", padx=30, pady=(0, 8))

        grid = ctk.CTkFrame(self, fg_color="transparent")
        grid.pack(fill="both", expand=True, padx=30)
        grid.grid_columnconfigure((0, 1), weight=1, uniform="m")
        for i, (mode, title, desc) in enumerate(_MODES):
            self._make_card(grid, mode, title, desc, i)

        self.warn = Banner(self, "", kind="warning")
        self.warn.pack(fill="x", padx=30, pady=(8, 4))

        nav = ctk.CTkFrame(self, fg_color="transparent")
        nav.pack(fill="x", padx=30, pady=(8, 20))
        ghost_button(nav, "< Back", lambda: self.app.show("device_select"), width=120).pack(side="left")
        self.continue_btn = primary_button(nav, "Start Scan >", self._start, width=180, state="disabled")
        self.continue_btn.pack(side="right")

    def _make_card(self, grid, mode, title, desc, i) -> None:
        card = Card(grid)
        card.grid(row=i // 2, column=i % 2, sticky="nsew", padx=8, pady=8)
        t = ctk.CTkLabel(card, text=title, font=theme.font(16, "bold"), anchor="w")
        t.pack(anchor="w", padx=18, pady=(16, 2))
        d = ctk.CTkLabel(card, text=desc, font=theme.font(12), text_color=theme.MUTED,
                         wraplength=360, justify="left", anchor="w")
        d.pack(anchor="w", padx=18, pady=(0, 16))
        self._cards[mode] = card
        for w in (card, t, d):
            w.bind("<Button-1>", lambda _e, m=mode: self._select(m))

    def on_show(self) -> None:
        src = self.app.source
        if src:
            self.source_lbl.configure(text=f"Source: {src['name']}  ({src['type']})")
        default = self.app.scan_mode_default or (MODE_IMAGE if src and src.get("is_image") else MODE_DEEP)
        self._select(default)

    def _select(self, mode: str) -> None:
        self._selected = mode
        for m, card in self._cards.items():
            if m == mode:
                card.configure(border_color=theme.ACCENT, border_width=2)
            else:
                card.configure(border_color=theme.CARD_BORDER, border_width=1)
        self.continue_btn.configure(state="normal")
        src = self.app.source or {}
        if mode == MODE_IMAGE and not src.get("is_image"):
            self.warn.set_text("Disk Image Scan expects an image file. Use 'Open Disk Image' from the welcome screen.")
        elif src.get("is_ssd"):
            self.warn.set_text("This is an SSD. If TRIM cleared the data, recovery may be impossible.")
        else:
            self.warn.set_text("Tip: For failing drives, image the disk first, then scan the image.")

    def _start(self) -> None:
        if not self._selected:
            return
        self.app.start_scan(self._selected)
