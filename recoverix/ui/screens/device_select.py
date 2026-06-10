"""Device selection - a sidebar of disks with an inline details panel.

Disks are listed in a left sidebar (name, type, health bar, temperature). Click
a disk to see its full health details on the right and choose what to scan
(the whole disk or a specific partition).
"""
from __future__ import annotations

import threading

import customtkinter as ctk

from .. import theme
from ..base import Screen
from ..i18n import t
from ..widgets import Banner, Card, Heading, ghost_button, primary_button
from ..disk_details import DiskDetailsView, GradientBar
from ...core.devices import Device, describe_size, list_devices


class DeviceSelectScreen(Screen):
    name = "device_select"

    def build(self) -> None:
        self._devices: list[Device] = []
        self._selected = None            # (device, partition|None) chosen to scan
        self._current_disk: Device | None = None
        self._disk_rows: list[tuple] = []
        self._target_rows: list[tuple] = []

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=24, pady=(18, 6))
        Heading(top, t("Select a device"),
                t("Choose a disk or partition to scan. All access is read-only.")).pack(
            side="left", anchor="w")
        ghost_button(top, t("Refresh"), self.refresh, width=110).pack(side="right")

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=24, pady=4)
        body.grid_columnconfigure(0, weight=0, minsize=300)
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)

        # left: disk sidebar
        side = ctk.CTkFrame(body, fg_color=theme.SURFACE, corner_radius=12, width=300)
        side.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        side.grid_propagate(False)
        side.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(side, text=t("Disks"), font=theme.font(13, "bold")).grid(
            row=0, column=0, sticky="w", padx=14, pady=(12, 4))
        self.sidebar = ctk.CTkScrollableFrame(side, fg_color="transparent")
        self.sidebar.grid(row=1, column=0, sticky="nsew", padx=4, pady=(0, 6))
        side.grid_columnconfigure(0, weight=1)

        # right: details + scan target
        self.detail = ctk.CTkScrollableFrame(body, fg_color=theme.SURFACE, corner_radius=12)
        self.detail.grid(row=0, column=1, sticky="nsew")

        self.status = ctk.CTkLabel(self, text="", font=theme.font(12), text_color=theme.MUTED)
        self.status.pack(anchor="w", padx=24, pady=(2, 0))

        nav = ctk.CTkFrame(self, fg_color="transparent")
        nav.pack(fill="x", padx=24, pady=(6, 12))
        ghost_button(nav, f"< {t('Back')}", lambda: self.app.show("welcome"), width=120).pack(side="left")
        self.continue_btn = primary_button(nav, f"{t('Continue')} >", self._continue,
                                            width=160, state="disabled")
        self.continue_btn.pack(side="right")

    def on_show(self) -> None:
        if not self._devices:
            self.refresh()

    # -- data --------------------------------------------------------------
    def refresh(self) -> None:
        self.status.configure(text=t("Scanning for devices..."))
        for w in self.sidebar.winfo_children():
            w.destroy()
        for w in self.detail.winfo_children():
            w.destroy()

        def worker():
            devs = list_devices()
            self.after(0, lambda: self._on_devices(devs))

        threading.Thread(target=worker, daemon=True).start()

    def _on_devices(self, devs: list[Device]) -> None:
        self._devices = devs
        self._selected = None
        self.continue_btn.configure(state="disabled")
        if not devs:
            self.status.configure(
                text=t("No devices found. Run as Administrator to access physical disks, "
                       "or use 'Open Disk Image' from the welcome screen."))
        else:
            self.status.configure(text=t("{n} device(s) detected.", n=len(devs)))
        self._render_sidebar()
        if devs:
            self._show_disk(devs[0])

    # -- sidebar -----------------------------------------------------------
    def _render_sidebar(self) -> None:
        for w in self.sidebar.winfo_children():
            w.destroy()
        self._disk_rows = []
        for dev in self._devices:
            self._render_disk_row(dev)

    def _render_disk_row(self, dev: Device) -> None:
        row = ctk.CTkFrame(self.sidebar, fg_color=theme.CARD, corner_radius=10,
                           border_width=0, border_color=theme.ACCENT)
        row.pack(fill="x", padx=6, pady=5)
        inner = ctk.CTkFrame(row, fg_color="transparent")
        inner.pack(fill="x", padx=12, pady=10)
        name = ctk.CTkLabel(inner, text=dev.name or dev.id, font=theme.font(13, "bold"), anchor="w")
        name.pack(anchor="w", fill="x")
        sub = ctk.CTkLabel(inner, text=f"{dev.disk_type_label}  ·  {describe_size(dev.size_bytes)}",
                           font=theme.font(10), text_color=theme.MUTED, anchor="w")
        sub.pack(anchor="w")

        widgets = [row, inner, name, sub]
        pct = dev.health_percent
        if pct is not None:
            hrow = ctk.CTkFrame(inner, fg_color="transparent")
            hrow.pack(fill="x", pady=(6, 0))
            GradientBar(hrow, pct, width=150, height=14).pack(side="left")
            word, color = dev.health_rating
            ctk.CTkLabel(hrow, text=f" {t(word)}", font=theme.font(10, "bold"),
                         text_color=color).pack(side="left")
            if dev.temperature > 0:
                ctk.CTkLabel(hrow, text=f"{dev.temperature} °C", font=theme.font(10),
                             text_color=theme.MUTED).pack(side="right")
            widgets.append(hrow)

        for w in widgets:
            w.bind("<Button-1>", lambda _e, d=dev: self._show_disk(d))
        self._disk_rows.append((dev, row))

    # -- details + scan target --------------------------------------------
    def _show_disk(self, dev: Device) -> None:
        self._current_disk = dev
        for d, row in self._disk_rows:
            row.configure(border_width=2 if d is dev else 0)
        for w in self.detail.winfo_children():
            w.destroy()
        self._selected = None
        self.continue_btn.configure(state="disabled")

        # what-to-scan selector
        self._target_rows = []
        sel_card = Card(self.detail)
        sel_card.pack(fill="x", padx=4, pady=(4, 12))
        ctk.CTkLabel(sel_card, text=t("Choose what to scan"), font=theme.font(14, "bold")).pack(
            anchor="w", padx=16, pady=(12, 6))
        holder = ctk.CTkFrame(sel_card, fg_color="transparent")
        holder.pack(fill="x", padx=12, pady=(0, 12))
        self._add_target(holder, dev, None,
                         t("Entire disk  ({size})", size=describe_size(dev.size_bytes)),
                         t("Raw scan across the whole device - best for lost partitions"))
        for p in dev.partitions:
            label = f"{p.drive_letter + ':  ' if p.drive_letter else ''}{p.label or t('No label')}"
            fs = p.file_system or t("Unknown FS")
            sub = f"{fs}   |   {describe_size(p.size_bytes)}"
            if p.free_bytes is not None:
                sub += "   |   " + t("{size} free", size=describe_size(p.free_bytes))
            self._add_target(holder, dev, p, label, sub)

        if dev.is_ssd:
            Banner(self.detail,
                   t("SSD detected: if TRIM has erased deleted data, recovery may be impossible."),
                   kind="warning").pack(fill="x", padx=4, pady=(0, 12))

        # full health details
        DiskDetailsView(self.detail, dev).pack(fill="both", expand=True, padx=4)

    def _add_target(self, parent, dev: Device, part, title: str, subtitle: str) -> None:
        row = ctk.CTkFrame(parent, fg_color=theme.SURFACE, corner_radius=8)
        row.pack(fill="x", pady=4)
        inner = ctk.CTkFrame(row, fg_color="transparent")
        inner.pack(fill="x", padx=12, pady=8)
        ti = ctk.CTkLabel(inner, text=title, font=theme.font(13, "bold"), anchor="w")
        ti.pack(anchor="w")
        si = ctk.CTkLabel(inner, text=subtitle, font=theme.font(11), text_color=theme.MUTED, anchor="w")
        si.pack(anchor="w")
        key = (dev, part)

        def select(_e=None):
            self._selected = key
            for _k, r in self._target_rows:
                r.configure(fg_color=theme.SURFACE, border_width=0)
            row.configure(fg_color=("#dbeafe", "#1e293b"), border_width=2, border_color=theme.ACCENT)
            self.continue_btn.configure(state="normal")

        for w in (row, inner, ti, si):
            w.bind("<Button-1>", select)
        self._target_rows.append((key, row))

    def _continue(self) -> None:
        if not self._selected:
            return
        dev, part = self._selected
        self.app.set_source(device=dev, partition=part)
        self.app.scan_mode_default = None
        self.app.show("scan_mode")
