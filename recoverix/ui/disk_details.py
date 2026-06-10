"""Detailed disk information window - a modern, HD Sentinel-style health overview.

Shows a red->green gradient health bar with a rating word, a colour-coded status
box, lifetime usage stats and the raw SMART attributes that drove the result.
All data is read directly from the device (see core.smart / core.devices).
"""
from __future__ import annotations

import tkinter as tk

import customtkinter as ctk

from . import theme
from .i18n import t
from .widgets import Banner, Card
from ..core.devices import Device, describe_size


def _c(color):
    if isinstance(color, (tuple, list)):
        return color[1] if ctk.get_appearance_mode() == "Dark" else color[0]
    return color


def _fmt_errors(n: int) -> str:
    return t("Unknown") if n < 0 else f"{n:,}"


def _usage_text(dev) -> str:
    """Power-on time with translated units (year/day/hour)."""
    poh = dev.power_on_hours_effective
    if poh is None or poh < 0:
        return t("Unknown")
    days, hours = poh // 24, poh % 24
    if days >= 365:
        return t("{y} yr {d} d ({total} h)", y=days // 365, d=days % 365, total=f"{poh:,}")
    if days > 0:
        return t("{d} d {h} h ({total} h)", d=days, h=hours, total=f"{poh:,}")
    return t("{h} h", h=hours)


class GradientBar(tk.Canvas):
    """A red -> amber -> green gradient bar with the percentage marked on it."""

    def __init__(self, master, percent, width=360, height=28):
        super().__init__(master, width=width, height=height, highlightthickness=1,
                         highlightbackground=_c(theme.CARD_BORDER), bg=_c(theme.CARD), bd=0)
        self._pct = percent if percent is not None else -1
        self._wd, self._ht = width, height
        self.bind("<Configure>", lambda _e: self._draw())
        self.after(16, self._draw)

    def _draw(self):
        self.delete("all")
        w = self.winfo_width() or self._wd
        h = self._ht
        if self._pct < 0:
            self.create_rectangle(0, 0, w, h, fill=_c(theme.SURFACE), outline="")
            self.create_text(w // 2, h // 2, text="?", font=("Segoe UI", 11, "bold"),
                             fill=_c(theme.MUTED))
            return
        for x in range(w):
            t = x / max(1, w - 1)
            if t < 0.5:
                tt = t / 0.5
                r = int(220 + (234 - 220) * tt); g = int(38 + (179 - 38) * tt); b = int(38 + (8 - 38) * tt)
            else:
                tt = (t - 0.5) / 0.5
                r = int(234 + (22 - 234) * tt); g = int(179 + (163 - 179) * tt); b = int(8 + (74 - 8) * tt)
            self.create_line(x, 0, x, h, fill=f"#{r:02x}{g:02x}{b:02x}")
        mx = int(self._pct / 100.0 * (w - 1))
        self.create_line(mx, 0, mx, h, fill="#111827", width=3)
        self.create_line(mx, 0, mx, h, fill="#ffffff", width=1)
        txt = f"{self._pct} %"
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            self.create_text(w // 2 + dx, h // 2 + dy, text=txt, font=("Segoe UI", 12, "bold"),
                             fill="#000000")
        self.create_text(w // 2, h // 2, text=txt, font=("Segoe UI", 12, "bold"), fill="#ffffff")


class DiskDetailsWindow(ctk.CTkToplevel):
    """Top-level window showing full health details for one disk."""

    def __init__(self, master, dev: Device):
        super().__init__(master)
        self.dev = dev
        self.title(f"{t('Disk info')} - {dev.name or dev.id}")
        self.geometry("720x780")
        self.minsize(600, 580)
        self.configure(fg_color=theme.SURFACE)
        self.transient(master)
        self.after(50, self._raise)

        body = ctk.CTkScrollableFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=18, pady=18)
        DiskDetailsView(body, dev).pack(fill="both", expand=True)

        ctk.CTkButton(self, text=t("Close"), command=self.destroy,
                      fg_color=theme.ACCENT, hover_color=theme.ACCENT_HOVER,
                      height=38, width=140).pack(pady=(0, 14))

    def _raise(self) -> None:
        try:
            self.lift(); self.focus_force()
            self.attributes("-topmost", True)
            self.after(300, lambda: self.attributes("-topmost", False))
        except Exception:  # noqa: BLE001
            pass


class DiskDetailsView(ctk.CTkFrame):
    """Reusable disk-details panel (used by the popup window and the sidebar)."""

    def __init__(self, master, dev: Device):
        super().__init__(master, fg_color="transparent")
        self.dev = dev
        self._header(self)
        self._overview_section(self)
        self._stats_section(self)
        self._smart_section(self)
        self._hardware_section(self)
        self._errors_section(self)
        self._partitions_section(self)

    # -- building blocks ---------------------------------------------------
    def _section(self, parent, title: str) -> ctk.CTkFrame:
        card = Card(parent)
        card.pack(fill="x", pady=(0, 12))
        ctk.CTkLabel(card, text=title, font=theme.font(14, "bold")).pack(
            anchor="w", padx=16, pady=(12, 6))
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=16, pady=(0, 12))
        inner.grid_columnconfigure(1, weight=1)
        return inner

    def _row(self, parent, label: str, value: str, value_color=None) -> None:
        r = parent.grid_size()[1]
        ctk.CTkLabel(parent, text=label, font=theme.font(12), text_color=theme.MUTED,
                     anchor="w").grid(row=r, column=0, sticky="w", padx=(0, 14), pady=3)
        ctk.CTkLabel(parent, text=value, font=theme.font(12, "bold"), anchor="w",
                     text_color=value_color or ("#111827", "#f3f4f6"),
                     justify="left", wraplength=440).grid(row=r, column=1, sticky="w", pady=3)

    # -- sections ----------------------------------------------------------
    def _header(self, parent) -> None:
        d = self.dev
        head = ctk.CTkFrame(parent, fg_color="transparent")
        head.pack(fill="x", pady=(0, 12))
        ctk.CTkLabel(head, text=d.name or d.id, font=theme.font(20, "bold")).pack(
            side="left", anchor="w")
        dtype = d.disk_type_label
        dtype_color = {"HDD": "#3b82f6", "SATA SSD": "#8b5cf6",
                       "M.2 NVMe SSD": "#6366f1", "SSD": "#8b5cf6",
                       "USB Drive": "#0891b2", "Disk Image": "#6b7280"}.get(dtype, "#6b7280")
        ctk.CTkLabel(head, text=f"  {dtype}  ", font=theme.font(12, "bold"),
                     fg_color=dtype_color, text_color="#ffffff",
                     corner_radius=6).pack(side="right")

    def _overview_section(self, parent) -> None:
        d = self.dev
        card = Card(parent)
        card.pack(fill="x", pady=(0, 12))
        ctk.CTkLabel(card, text=t("Health (Health)"), font=theme.font(14, "bold")).pack(
            anchor="w", padx=16, pady=(12, 6))

        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=(0, 8))
        GradientBar(row, d.health_percent).pack(side="left")
        word, color = d.health_rating
        ctk.CTkLabel(row, text=t(word), font=theme.font(16, "bold"), text_color=color).pack(
            side="left", padx=14)

        kind, msg = self._status_message()
        bg = {"good": ("#dcfce7", "#13331f"), "warn": theme.WARN_BG,
              "bad": theme.DANGER_BG}[kind]
        fg = {"good": ("#14532d", "#bbf7d0"), "warn": ("#7c5e10", "#fcd9a3"),
              "bad": ("#7f1d1d", "#fecaca")}[kind]
        box = ctk.CTkFrame(card, fg_color=bg, corner_radius=8)
        box.pack(fill="x", padx=16, pady=(4, 12))
        ctk.CTkLabel(box, text=msg, font=theme.font(12), justify="left", wraplength=600,
                     text_color=fg, anchor="w").pack(anchor="w", padx=12, pady=10)

    def _status_message(self):
        d = self.dev
        pct = d.health_percent
        probs = d.smart_problems
        basis = self._health_basis()
        if d.predict_failure or (pct is not None and pct < 20):
            return "bad", t("health_status_bad") + basis
        if probs or (pct is not None and pct < 50):
            return "warn", t("health_status_warn") + basis
        return "good", t("health_status_good") + basis

    def _health_basis(self) -> str:
        """Explain which attribute drove the health figure (HD Sentinel style)."""
        d = self.dev
        if d.smart_health is None:
            return ""
        if d.disk_type_label.startswith("M.2") or "NVMe" in d.disk_type_label:
            return t("basis_nvme")
        for a in d.smart_attributes:
            if a.id == 231 and 0 < a.value <= 100:
                return t("basis_231")
        if d.smart_problems:
            return t("basis_problem")
        return t("basis_smart")

    def _stats_section(self, parent) -> None:
        d = self.dev
        inner = self._section(parent, t("Usage & lifetime"))
        self._row(inner, t("Power-On time:"), _usage_text(d))
        if d.temperature > 0:
            tmax = t("  (max {n} °C)", n=d.temperature_max) if d.temperature_max > 0 else ""
            self._row(inner, t("Temperature:"), f"{d.temperature} °C{tmax}")
        if d.host_writes_text:
            self._row(inner, t("Lifetime writes:"), d.host_writes_text)
        for a in d.smart_attributes:
            if a.id in (231, 902) and 0 < a.value <= 100:
                self._row(inner, t("SSD life left:"), f"{a.value}%")
                break
        if d.start_stop_cycles >= 0:
            self._row(inner, t("Start/Stop cycles:"), f"{d.start_stop_cycles:,}")
        if d.manufacture_date:
            self._row(inner, t("Manufacture date:"), d.manufacture_date)

    def _smart_section(self, parent) -> None:
        d = self.dev
        if d.predict_failure:
            Banner(parent, t("WARNING: The disk reports it will fail soon (failure predicted). "
                             "Copy your data immediately."),
                   kind="danger").pack(fill="x", pady=(0, 12))
        if not d.smart_attributes:
            if not d.is_image:
                ctk.CTkLabel(
                    parent, text=t("Note: raw SMART could not be read for this disk "
                                   "(not possible on some USB bridges)."),
                    font=theme.font(10), text_color=theme.MUTED, justify="left",
                    wraplength=600).pack(anchor="w", pady=(0, 12))
            return

        inner = self._section(parent, t("SMART attributes"))
        if d.smart_problems:
            self._row(inner, t("Problem attributes:"), t("{n} item(s)", n=len(d.smart_problems)),
                      value_color=theme.DANGER)
        key_ids = [5, 197, 198, 196, 187, 184, 199, 188, 10, 231, 233, 902, 901, 903, 9]
        ordered = list(d.smart_problems)
        for a in d.smart_attributes:
            if a.id in key_ids and a.id not in [x.id for x in ordered]:
                ordered.append(a)
        seen = set()
        for a in ordered:
            if a.id in seen:
                continue
            seen.add(a.id)
            val = f"{a.display_raw:,}"
            if a.threshold > 0:
                val += "   " + t("value {v} / threshold {thr}", v=a.value, thr=a.threshold)
            self._row(inner, f"[{a.id}] {a.name}:", val,
                      value_color=theme.DANGER if a.is_problem else None)

    def _hardware_section(self, parent) -> None:
        d = self.dev
        inner = self._section(parent, t("Hardware information"))
        self._row(inner, t("Capacity:"), describe_size(d.size_bytes))
        if d.allocated_bytes >= 0:
            self._row(inner, t("Used:"), describe_size(d.allocated_bytes))
        if d.manufacturer:
            self._row(inner, t("Manufacturer:"), d.manufacturer)
        if d.serial:
            self._row(inner, t("Serial number:"), d.serial)
        if d.firmware:
            self._row(inner, t("Firmware:"), d.firmware)
        if d.bus_type_phys or d.bus_type:
            self._row(inner, t("Bus type:"), d.bus_type_phys or d.bus_type)
        if d.is_spinning_disk:
            self._row(inner, t("Spindle speed:"), f"{d.spindle_speed:,} RPM")
        if d.partition_style:
            self._row(inner, t("Partition style:"), d.partition_style)
        self._row(inner, t("Sector size:"), t("{n} bytes (logical)", n=d.sector_size))
        self._row(inner, t("Path:"), d.path)

    def _errors_section(self, parent) -> None:
        d = self.dev
        if d.read_errors_total < 0 and d.write_errors_total < 0:
            return
        inner = self._section(parent, t("Error counters"))
        total = max(d.read_errors_total, 0) + max(d.write_errors_total, 0)
        err_color = theme.DANGER if total > 0 else theme.SUCCESS
        self._row(inner, t("Read errors:"), _fmt_errors(d.read_errors_total),
                  value_color=err_color if d.read_errors_total > 0 else None)
        self._row(inner, t("Write errors:"), _fmt_errors(d.write_errors_total),
                  value_color=err_color if d.write_errors_total > 0 else None)
        if total > 0:
            Banner(parent, t("Errors were detected on this disk. Copy important data to "
                             "another disk immediately."), kind="danger").pack(
                fill="x", pady=(0, 12))

    def _partitions_section(self, parent) -> None:
        d = self.dev
        if not d.partitions:
            return
        inner = self._section(parent, t("Partitions ({n})", n=len(d.partitions)))
        for p in d.partitions:
            letter = f"{p.drive_letter}:  " if p.drive_letter else ""
            label = f"{letter}{p.label or t('Unnamed')}"
            fs = p.file_system or t("Unknown FS")
            val = f"{fs}  -  {describe_size(p.size_bytes)}"
            if p.free_bytes is not None:
                val += "  (" + t("{size} free", size=describe_size(p.free_bytes)) + ")"
            self._row(inner, label, val)
