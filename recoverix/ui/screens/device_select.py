"""Device / partition selection screen."""
from __future__ import annotations

import threading

import customtkinter as ctk

from .. import theme
from ..base import Screen
from ..widgets import Banner, Card, Heading, ghost_button, primary_button
from ...core.devices import Device, Partition, describe_size, list_devices


class DeviceSelectScreen(Screen):
    name = "device_select"

    def build(self) -> None:
        self._devices: list[Device] = []
        self._selected = None  # (device, partition|None)
        self._row_widgets: list[tuple[object, ctk.CTkFrame]] = []

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=30, pady=(24, 8))
        Heading(top, "Select a device",
                "Choose a disk or partition to scan. All access is read-only.").pack(
            side="left", anchor="w")
        ghost_button(top, "Refresh", self.refresh, width=110).pack(side="right")

        search_row = ctk.CTkFrame(self, fg_color="transparent")
        search_row.pack(fill="x", padx=30, pady=(0, 8))
        self.search = ctk.CTkEntry(search_row, placeholder_text="Filter by name, type or filesystem...",
                                   height=36)
        self.search.pack(fill="x")
        self.search.bind("<KeyRelease>", lambda _e: self._render())

        self.list = ctk.CTkScrollableFrame(self, fg_color=theme.SURFACE, corner_radius=12)
        self.list.pack(fill="both", expand=True, padx=30, pady=8)

        self.status = ctk.CTkLabel(self, text="", font=theme.font(12), text_color=theme.MUTED)
        self.status.pack(anchor="w", padx=30)

        nav = ctk.CTkFrame(self, fg_color="transparent")
        nav.pack(fill="x", padx=30, pady=(8, 20))
        ghost_button(nav, "< Back", lambda: self.app.show("welcome"), width=120).pack(side="left")
        self.continue_btn = primary_button(nav, "Continue >", self._continue, width=160, state="disabled")
        self.continue_btn.pack(side="right")

    def on_show(self) -> None:
        if not self._devices:
            self.refresh()

    # -- data --------------------------------------------------------------
    def refresh(self) -> None:
        self.status.configure(text="Scanning for devices...")
        for w in self.list.winfo_children():
            w.destroy()

        def worker():
            devs = list_devices()
            self.after(0, lambda: self._on_devices(devs))

        threading.Thread(target=worker, daemon=True).start()

    def _on_devices(self, devs: list[Device]) -> None:
        self._devices = devs
        if not devs:
            self.status.configure(
                text="No devices found. Run as Administrator to access physical disks, "
                     "or use 'Open Disk Image' from the welcome screen.")
        else:
            self.status.configure(text=f"{len(devs)} device(s) detected.")
        self._render()

    # -- rendering ---------------------------------------------------------
    def _render(self) -> None:
        for w in self.list.winfo_children():
            w.destroy()
        self._row_widgets = []
        q = self.search.get().strip().lower()

        for dev in self._devices:
            if q and q not in (dev.name + dev.media_type + dev.bus_type).lower() and not any(
                q in ((p.file_system or "") + (p.label or "")).lower() for p in dev.partitions
            ):
                continue
            self._render_device(dev)

    def _render_device(self, dev: Device) -> None:
        card = Card(self.list)
        card.pack(fill="x", padx=8, pady=8)

        head = ctk.CTkFrame(card, fg_color="transparent")
        head.pack(fill="x", padx=16, pady=(14, 6))
        title = dev.name or dev.id
        ctk.CTkLabel(head, text=title, font=theme.font(15, "bold")).pack(side="left")
        tags = []
        if dev.media_type:
            tags.append(dev.media_type)
        if dev.bus_type:
            tags.append(dev.bus_type)
        if dev.partition_style:
            tags.append(dev.partition_style)
        ctk.CTkLabel(head, text="   ".join(tags), font=theme.font(11),
                     text_color=theme.MUTED).pack(side="right")

        meta = []
        meta.append(describe_size(dev.size_bytes))
        if dev.serial:
            meta.append(f"S/N {dev.serial[:24]}")
        if dev.health:
            meta.append(f"Health: {dev.health}")
        ctk.CTkLabel(card, text="   |   ".join(meta), font=theme.font(11),
                     text_color=theme.MUTED).pack(anchor="w", padx=16)

        if dev.is_ssd:
            Banner(card, "SSD detected: if TRIM has erased deleted data, recovery may be impossible.",
                   kind="warning").pack(fill="x", padx=16, pady=(8, 4))

        # whole-disk row
        self._row(card, dev, None,
                  f"Entire disk  ({describe_size(dev.size_bytes)})",
                  "Raw scan across the whole device - best for lost partitions")
        # partitions
        for p in dev.partitions:
            label = f"{p.drive_letter + ':  ' if p.drive_letter else ''}{p.label or 'No label'}"
            fs = p.file_system or "Unknown FS"
            sub = f"{fs}   |   {describe_size(p.size_bytes)}"
            if p.free_bytes is not None:
                sub += f"   |   {describe_size(p.free_bytes)} free"
            self._row(card, dev, p, label, sub)

    def _row(self, parent, dev: Device, part, title: str, subtitle: str) -> None:
        row = ctk.CTkFrame(parent, fg_color=theme.SURFACE, corner_radius=8)
        row.pack(fill="x", padx=16, pady=4)
        key = (dev, part)

        def select(_e=None):
            self._select(key, row)

        inner = ctk.CTkFrame(row, fg_color="transparent")
        inner.pack(fill="x", padx=12, pady=8)
        t = ctk.CTkLabel(inner, text=title, font=theme.font(13, "bold"), anchor="w")
        t.pack(anchor="w")
        s = ctk.CTkLabel(inner, text=subtitle, font=theme.font(11), text_color=theme.MUTED, anchor="w")
        s.pack(anchor="w")
        for widget in (row, inner, t, s):
            widget.bind("<Button-1>", select)
        self._row_widgets.append((key, row))

    def _select(self, key, row) -> None:
        self._selected = key
        for k, w in self._row_widgets:
            w.configure(fg_color=theme.SURFACE, border_width=0)
        row.configure(fg_color=("#dbeafe", "#1e293b"), border_width=2, border_color=theme.ACCENT)
        self.continue_btn.configure(state="normal")

    def _continue(self) -> None:
        if not self._selected:
            return
        dev, part = self._selected
        self.app.set_source(device=dev, partition=part)
        self.app.scan_mode_default = None
        self.app.show("scan_mode")
