"""Detailed disk information window (read-only SMART / reliability data)."""
from __future__ import annotations

import customtkinter as ctk

from . import theme
from .widgets import Banner, Card
from ..core.devices import Device, describe_size


def _fmt_errors(n: int) -> str:
    if n < 0:
        return "Naməlum"
    return f"{n:,}"


class DiskDetailsWindow(ctk.CTkToplevel):
    """A modal-ish top-level window showing full details for one disk."""

    def __init__(self, master, dev: Device):
        super().__init__(master)
        self.dev = dev
        self.title(f"Disk məlumatı - {dev.name or dev.id}")
        self.geometry("680x720")
        self.minsize(560, 560)
        self.configure(fg_color=theme.SURFACE)

        # Bring to front above the (possibly elevated) main window.
        self.transient(master)
        self.after(50, self._raise)

        body = ctk.CTkScrollableFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=18, pady=18)

        self._header(body)
        self._usage_section(body)
        self._health_section(body)
        self._hardware_section(body)
        self._errors_section(body)
        self._partitions_section(body)

        ctk.CTkButton(self, text="Bağla", command=self.destroy,
                      fg_color=theme.ACCENT, hover_color=theme.ACCENT_HOVER,
                      height=38, width=140).pack(pady=(0, 14))

    def _raise(self) -> None:
        try:
            self.lift()
            self.focus_force()
            self.attributes("-topmost", True)
            self.after(300, lambda: self.attributes("-topmost", False))
        except Exception:  # noqa: BLE001
            pass

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
                     justify="left", wraplength=420).grid(row=r, column=1, sticky="w", pady=3)

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

    def _usage_section(self, parent) -> None:
        d = self.dev
        inner = self._section(parent, "İstifadə müddəti (ömür boyu)")
        self._row(inner, "İşləmə vaxtı:", d.usage_text)
        if d.power_on_days is not None:
            self._row(inner, "Təxmini gün:", f"{d.power_on_days:.1f} gün")
        if d.start_stop_cycles >= 0:
            self._row(inner, "Start/Stop dövrü:", f"{d.start_stop_cycles:,}")
        if d.load_unload_cycles >= 0:
            self._row(inner, "Load/Unload dövrü:", f"{d.load_unload_cycles:,}")
        if d.manufacture_date:
            self._row(inner, "İstehsal tarixi:", d.manufacture_date)
        ctk.CTkLabel(
            parent,
            text="Qeyd: Windows daxili disklər üçün \"bu kompüterə nə vaxt qoşulub\" "
                 "məlumatını vermir. Göstərilən vaxt diskin ümumi ömür boyu işləmə "
                 "saatıdır (Power-On Hours).",
            font=theme.font(10), text_color=theme.MUTED, justify="left",
            wraplength=600).pack(anchor="w", pady=(0, 12))

    def _health_section(self, parent) -> None:
        d = self.dev
        inner = self._section(parent, "Sağlamlıq və temperatur")
        pct = d.health_percent
        if pct is not None:
            self._row(inner, "Sağlamlıq:", f"{pct}%", value_color=d.health_color)
        if d.health:
            self._row(inner, "Status:", d.health)
        if d.wear >= 0:
            self._row(inner, "Aşınma (wear):", f"{d.wear}%")
        if d.temperature > 0:
            self._row(inner, "Temperatur:", f"{d.temperature} °C")
        if d.temperature_max > 0:
            self._row(inner, "Maks. temperatur:", f"{d.temperature_max} °C")
        if d.operational_status:
            self._row(inner, "Əməliyyat statusu:", d.operational_status)

    def _hardware_section(self, parent) -> None:
        d = self.dev
        inner = self._section(parent, "Avadanlıq məlumatı")
        self._row(inner, "Ölçü:", describe_size(d.size_bytes))
        if d.allocated_bytes >= 0:
            self._row(inner, "İstifadə olunan:", describe_size(d.allocated_bytes))
        if d.manufacturer:
            self._row(inner, "İstehsalçı:", d.manufacturer)
        if d.serial:
            self._row(inner, "Seriya nömrəsi:", d.serial)
        if d.firmware:
            self._row(inner, "Firmware:", d.firmware)
        if d.bus_type_phys or d.bus_type:
            self._row(inner, "Bus tipi:", d.bus_type_phys or d.bus_type)
        if d.is_spinning_disk:
            self._row(inner, "Fırlanma sürəti:", f"{d.spindle_speed:,} RPM")
        if d.partition_style:
            self._row(inner, "Bölmə stili:", d.partition_style)
        self._row(inner, "Sektor ölçüsü:", f"{d.sector_size} bayt (məntiqi)")
        if d.physical_sector_size > 0:
            self._row(inner, "Fiziki sektor:", f"{d.physical_sector_size} bayt")
        self._row(inner, "Yol:", d.path)

    def _errors_section(self, parent) -> None:
        d = self.dev
        if d.read_errors_total < 0 and d.write_errors_total < 0:
            return
        inner = self._section(parent, "Xəta sayğacları")
        total = max(d.read_errors_total, 0) + max(d.write_errors_total, 0)
        err_color = theme.DANGER if total > 0 else theme.SUCCESS
        self._row(inner, "Oxuma xətaları:", _fmt_errors(d.read_errors_total),
                  value_color=err_color if d.read_errors_total > 0 else None)
        self._row(inner, "Yazma xətaları:", _fmt_errors(d.write_errors_total),
                  value_color=err_color if d.write_errors_total > 0 else None)
        if total > 0:
            Banner(parent, "Bu diskdə xətalar aşkarlandı. Vacib məlumatları dərhal "
                           "başqa bir diskə kopyalayın.", kind="danger").pack(
                fill="x", pady=(0, 12))

    def _partitions_section(self, parent) -> None:
        d = self.dev
        if not d.partitions:
            return
        inner = self._section(parent, f"Bölmələr ({len(d.partitions)})")
        for p in d.partitions:
            letter = f"{p.drive_letter}:  " if p.drive_letter else ""
            label = f"{letter}{p.label or 'Adsız'}"
            fs = p.file_system or "Naməlum FS"
            val = f"{fs}  -  {describe_size(p.size_bytes)}"
            if p.free_bytes is not None:
                val += f"  ({describe_size(p.free_bytes)} boş)"
            self._row(inner, label, val)
