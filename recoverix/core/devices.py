"""Disk, partition and disk-image detection (Windows).

Uses PowerShell Storage cmdlets (Get-Disk / Get-Partition / Get-Volume /
Get-PhysicalDisk) to enumerate physical drives and partitions, plus a helper to
treat a disk-image file as a virtual source. All access downstream is read-only.
"""
from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, field
from typing import List, Optional

from .logging_setup import get_logger

log = get_logger("devices")

_PS_SCRIPT = r"""
$ErrorActionPreference = 'SilentlyContinue'
$disks = Get-Disk | ForEach-Object {
  $d = $_
  $phys = Get-PhysicalDisk | Where-Object { $_.DeviceId -eq ([string]$d.Number) } | Select-Object -First 1
  $rel = $null
  if ($phys) { try { $rel = Get-StorageReliabilityCounter -PhysicalDisk $phys -ErrorAction Stop } catch {} }
  $parts = Get-Partition -DiskNumber $d.Number | ForEach-Object {
    $p = $_
    $vol = $null
    if ($p.DriveLetter) { $vol = Get-Volume -DriveLetter $p.DriveLetter }
    [pscustomobject]@{
      partitionNumber = [int]$p.PartitionNumber
      offset = [int64]$p.Offset
      size = [int64]$p.Size
      driveLetter = if ($p.DriveLetter) { [string]$p.DriveLetter } else { $null }
      type = [string]$p.Type
      fileSystem = if ($vol) { [string]$vol.FileSystem } else { $null }
      label = if ($vol) { [string]$vol.FileSystemLabel } else { $null }
      sizeRemaining = if ($vol) { [int64]$vol.SizeRemaining } else { $null }
    }
  }
  [pscustomobject]@{
    number = [int]$d.Number
    path = "\\.\PHYSICALDRIVE$($d.Number)"
    model = [string]$d.FriendlyName
    manufacturer = [string]$d.Manufacturer
    serial = [string]$d.SerialNumber
    size = [int64]$d.Size
    partitionStyle = [string]$d.PartitionStyle
    busType = [string]$d.BusType
    busTypePhys = if ($phys) { [string]$phys.BusType } else { '' }
    mediaType = if ($phys) { [string]$phys.MediaType } else { '' }
    health = if ($phys) { [string]$phys.HealthStatus } else { '' }
    firmware = if ($phys) { [string]$phys.FirmwareVersion } else { '' }
    allocatedSize = if ($phys -and $null -ne $phys.AllocatedSize) { [int64]$phys.AllocatedSize } else { -1 }
    spindleSpeed = if ($phys -and $null -ne $phys.SpindleSpeed) { [int64]$phys.SpindleSpeed } else { -1 }
    operationalStatus = if ($phys) { [string]($phys.OperationalStatus -join ', ') } else { '' }
    physicalSectorSize = if ($phys -and $null -ne $phys.PhysicalSectorSize) { [int]$phys.PhysicalSectorSize } else { -1 }
    wear = if ($rel -and $null -ne $rel.Wear) { [int]$rel.Wear } else { -1 }
    temperature = if ($rel -and $null -ne $rel.Temperature) { [int]$rel.Temperature } else { -1 }
    temperatureMax = if ($rel -and $null -ne $rel.TemperatureMax) { [int]$rel.TemperatureMax } else { -1 }
    powerOnHours = if ($rel -and $null -ne $rel.PowerOnHours) { [int64]$rel.PowerOnHours } else { -1 }
    readErrorsTotal = if ($rel -and $null -ne $rel.ReadErrorsTotal) { [int64]$rel.ReadErrorsTotal } else { -1 }
    writeErrorsTotal = if ($rel -and $null -ne $rel.WriteErrorsTotal) { [int64]$rel.WriteErrorsTotal } else { -1 }
    startStopCycles = if ($rel -and $null -ne $rel.StartStopCycleCount) { [int64]$rel.StartStopCycleCount } else { -1 }
    loadUnloadCycles = if ($rel -and $null -ne $rel.LoadUnloadCycleCount) { [int64]$rel.LoadUnloadCycleCount } else { -1 }
    manufactureDate = if ($rel -and $rel.ManufactureDate) { [string]$rel.ManufactureDate } else { '' }
    sectorSize = [int]$d.LogicalSectorSize
    isReadOnly = [bool]$d.IsReadOnly
    partitions = @($parts)
  }
}
@($disks) | ConvertTo-Json -Depth 6 -Compress
"""


@dataclass
class Partition:
    id: str
    path: Optional[str]
    number: int
    offset_bytes: int
    size_bytes: int
    file_system: Optional[str]
    label: Optional[str]
    drive_letter: Optional[str]
    free_bytes: Optional[int]
    type_name: str = ""


@dataclass
class Device:
    id: str
    path: str
    name: str
    manufacturer: str
    serial: str
    size_bytes: int
    media_type: str       # HDD / SSD / Unspecified / Image
    bus_type: str         # from Get-Disk (may show SCSI for NVMe)
    bus_type_phys: str    # from Get-PhysicalDisk (NVMe / SATA / USB / MMC …)
    partition_style: str  # MBR / GPT / RAW
    health: str           # Healthy / Warning / Unhealthy
    wear: int             # % endurance consumed (0=new, 100=end-of-life); -1=unknown
    temperature: int      # °C; -1=unknown
    power_on_hours: int   # -1=unknown
    sector_size: int
    is_read_only: bool
    firmware: str = ""
    allocated_bytes: int = -1       # space currently in use; -1=unknown
    spindle_speed: int = -1         # RPM (0 = SSD/no spindle); -1=unknown
    operational_status: str = ""    # OK / Lost Communication …
    physical_sector_size: int = -1  # -1=unknown
    temperature_max: int = -1       # highest recorded °C; -1=unknown
    read_errors_total: int = -1     # -1=unknown
    write_errors_total: int = -1    # -1=unknown
    start_stop_cycles: int = -1     # -1=unknown
    load_unload_cycles: int = -1    # -1=unknown
    manufacture_date: str = ""      # raw string from reliability counter
    partitions: List[Partition] = field(default_factory=list)
    is_image: bool = False

    @property
    def is_ssd(self) -> bool:
        return "ssd" in (self.media_type or "").lower()

    @property
    def is_removable(self) -> bool:
        bt = (self.bus_type_phys or self.bus_type or "").upper()
        return bt in ("USB", "SD", "MMC")

    @property
    def disk_type_label(self) -> str:
        """Human-readable disk type: HDD / SATA SSD / M.2 NVMe SSD / USB Drive …"""
        if self.is_image:
            return "Disk Image"
        bt = (self.bus_type_phys or "").upper()
        mt = (self.media_type or "").upper()
        if bt in ("USB",):
            return "USB Drive"
        if bt in ("SD", "MMC"):
            return "SD / MMC Card"
        if "SSD" in mt or mt == "SSD":
            if bt == "NVME":
                return "M.2 NVMe SSD"
            if bt == "SATA":
                return "SATA SSD"
            return "SSD"
        if "HDD" in mt or mt == "HDD":
            return "HDD"
        # fall back to media_type text if present
        if self.media_type and self.media_type.lower() not in ("unspecified", ""):
            return self.media_type
        return "Disk"

    @property
    def health_percent(self) -> Optional[int]:
        """Health as 0-100 %. None if not available."""
        if self.wear >= 0:
            return max(0, 100 - self.wear)
        if self.health:
            return {"healthy": 100, "warning": 50, "unhealthy": 10}.get(
                self.health.lower(), None
            )
        return None

    @property
    def health_color(self) -> str:
        pct = self.health_percent
        if pct is None:
            return "#6b7280"
        if pct >= 80:
            return "#16a34a"
        if pct >= 50:
            return "#d97706"
        return "#dc2626"

    @property
    def power_on_days(self) -> Optional[float]:
        """Total power-on time expressed in days. None if unknown."""
        if self.power_on_hours is None or self.power_on_hours < 0:
            return None
        return self.power_on_hours / 24.0

    @property
    def usage_text(self) -> str:
        """Human-readable lifetime usage, e.g. '521 days 8 hours' (in Azerbaijani)."""
        if self.power_on_hours is None or self.power_on_hours < 0:
            return "Naməlum"
        days = self.power_on_hours // 24
        hours = self.power_on_hours % 24
        if days >= 365:
            years = days // 365
            rem_days = days % 365
            return f"{years} il {rem_days} gün ({self.power_on_hours:,} saat)"
        if days > 0:
            return f"{days} gün {hours} saat ({self.power_on_hours:,} saat)"
        return f"{hours} saat"

    @property
    def is_spinning_disk(self) -> bool:
        return self.spindle_speed > 0


def _human(num: int) -> str:
    f = float(num)
    for unit in ("B", "KB", "MB", "GB", "TB", "PB"):
        if abs(f) < 1024.0:
            return f"{f:.1f} {unit}"
        f /= 1024.0
    return f"{f:.1f} EB"


def list_devices() -> List[Device]:
    """Enumerate physical disks and their partitions (read-only metadata)."""
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", _PS_SCRIPT],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        log.error("Device enumeration failed: %s", exc)
        return []

    out = (proc.stdout or "").strip()
    if not out:
        log.warning("No device data returned. stderr=%s", proc.stderr)
        return []

    try:
        data = json.loads(out)
    except json.JSONDecodeError as exc:
        log.error("Failed to parse device JSON: %s", exc)
        return []

    if isinstance(data, dict):
        data = [data]

    devices: List[Device] = []
    for d in data:
        parts: List[Partition] = []
        for p in d.get("partitions") or []:
            letter = p.get("driveLetter")
            parts.append(
                Partition(
                    id=f"disk{d.get('number')}p{p.get('partitionNumber')}",
                    path=f"\\\\.\\{letter}:" if letter else None,
                    number=int(p.get("partitionNumber") or 0),
                    offset_bytes=int(p.get("offset") or 0),
                    size_bytes=int(p.get("size") or 0),
                    file_system=p.get("fileSystem"),
                    label=p.get("label"),
                    drive_letter=letter,
                    free_bytes=p.get("sizeRemaining"),
                    type_name=p.get("type") or "",
                )
            )
        devices.append(
            Device(
                id=f"physicaldrive{d.get('number')}",
                path=d.get("path") or f"\\\\.\\PHYSICALDRIVE{d.get('number')}",
                name=(d.get("model") or "Unknown Disk").strip(),
                manufacturer=(d.get("manufacturer") or "").strip(),
                serial=(d.get("serial") or "").strip(),
                size_bytes=int(d.get("size") or 0),
                media_type=d.get("mediaType") or "",
                bus_type=d.get("busType") or "",
                bus_type_phys=d.get("busTypePhys") or "",
                partition_style=d.get("partitionStyle") or "",
                health=d.get("health") or "",
                wear=int(d.get("wear") if d.get("wear") is not None else -1),
                temperature=int(d.get("temperature") if d.get("temperature") is not None else -1),
                power_on_hours=int(d.get("powerOnHours") if d.get("powerOnHours") is not None else -1),
                sector_size=int(d.get("sectorSize") or 512),
                is_read_only=bool(d.get("isReadOnly")),
                firmware=(d.get("firmware") or "").strip(),
                allocated_bytes=int(d.get("allocatedSize") if d.get("allocatedSize") is not None else -1),
                spindle_speed=int(d.get("spindleSpeed") if d.get("spindleSpeed") is not None else -1),
                operational_status=(d.get("operationalStatus") or "").strip(),
                physical_sector_size=int(d.get("physicalSectorSize") if d.get("physicalSectorSize") is not None else -1),
                temperature_max=int(d.get("temperatureMax") if d.get("temperatureMax") is not None else -1),
                read_errors_total=int(d.get("readErrorsTotal") if d.get("readErrorsTotal") is not None else -1),
                write_errors_total=int(d.get("writeErrorsTotal") if d.get("writeErrorsTotal") is not None else -1),
                start_stop_cycles=int(d.get("startStopCycles") if d.get("startStopCycles") is not None else -1),
                load_unload_cycles=int(d.get("loadUnloadCycles") if d.get("loadUnloadCycles") is not None else -1),
                manufacture_date=(d.get("manufactureDate") or "").strip(),
                partitions=parts,
            )
        )
    log.info("Enumerated %d physical device(s)", len(devices))
    return devices


def device_from_image(path: str) -> Optional[Device]:
    """Wrap a disk-image file as a virtual, read-only Device."""
    if not os.path.isfile(path):
        return None
    size = os.path.getsize(path)
    name = os.path.basename(path)
    return Device(
        id=f"image:{path}",
        path=path,
        name=name,
        manufacturer="",
        serial="",
        size_bytes=size,
        media_type="Image",
        bus_type="FILE",
        bus_type_phys="",
        partition_style="",
        health="",
        wear=-1,
        temperature=-1,
        power_on_hours=-1,
        sector_size=512,
        is_read_only=True,
        partitions=[],
        is_image=True,
    )


def describe_size(num: int) -> str:
    return _human(num)
