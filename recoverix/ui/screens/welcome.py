"""Welcome screen."""
from __future__ import annotations

from tkinter import filedialog

import customtkinter as ctk

from .. import theme
from ..base import Screen
from ..widgets import Banner, Card, Heading, ghost_button, primary_button
from ...core.devices import device_from_image
from ... import __version__


class WelcomeScreen(Screen):
    name = "welcome"

    def build(self) -> None:
        wrap = ctk.CTkFrame(self, fg_color="transparent")
        wrap.pack(fill="both", expand=True, padx=40, pady=30)

        ctk.CTkLabel(wrap, text="Recoverix", font=theme.font(40, "bold")).pack(anchor="w")
        ctk.CTkLabel(
            wrap,
            text="Professional data recovery for HDD, SSD, USB drives, memory cards and disk images.",
            font=theme.font(15), text_color=theme.MUTED,
        ).pack(anchor="w", pady=(4, 2))
        ctk.CTkLabel(wrap, text=f"Version {__version__}  -  100% offline  -  read-only scanning",
                     font=theme.font(11), text_color=theme.MUTED).pack(anchor="w")

        card = Card(wrap)
        card.pack(fill="x", pady=24)
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=24, pady=24)

        Heading(inner, "Get started",
                "Choose a physical disk to scan, or open an existing disk image file.").pack(
            anchor="w", fill="x")

        btns = ctk.CTkFrame(inner, fg_color="transparent")
        btns.pack(anchor="w", pady=(18, 4))
        primary_button(btns, "Start Recovery", self._start, width=200).pack(side="left", padx=(0, 12))
        ghost_button(btns, "Open Disk Image...", self._open_image, width=200).pack(side="left")

        feats = ctk.CTkFrame(wrap, fg_color="transparent")
        feats.pack(fill="x", pady=(4, 16))
        for title, desc in [
            ("Deep Scan + Carving", "Recover JPG, PNG, PDF, Office, ZIP, MP4 and more by signature."),
            ("Safe by design", "Sources are opened read-only. Nothing is written back to them."),
            ("Preview before recovery", "Inspect images and text before restoring to a safe folder."),
        ]:
            c = Card(feats)
            c.pack(side="left", fill="both", expand=True, padx=(0, 12))
            ctk.CTkLabel(c, text=title, font=theme.font(14, "bold")).pack(anchor="w", padx=16, pady=(14, 2))
            ctk.CTkLabel(c, text=desc, font=theme.font(12), text_color=theme.MUTED,
                         wraplength=240, justify="left").pack(anchor="w", padx=16, pady=(0, 16))

        Banner(
            wrap,
            "Safety: Never recover files back onto the same disk you are scanning. "
            "For failing drives, create a disk image first. Recovery is never guaranteed.",
            kind="warning",
        ).pack(fill="x")

    def _start(self) -> None:
        self.app.show("device_select")

    def _open_image(self) -> None:
        self.app.focus_force()
        path = filedialog.askopenfilename(
            title="Open disk image",
            filetypes=[("Disk images", "*.img *.dd *.raw *.iso *.bin"), ("All files", "*.*")],
            parent=self.app,
        )
        if not path:
            return
        dev = device_from_image(path)
        if dev is None:
            return
        self.app.set_source(device=dev, partition=None)
        self.app.scan_mode_default = "image"
        self.app.show("scan_mode")
