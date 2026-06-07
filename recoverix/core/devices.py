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
    mediaType = if ($phys) { [string]$phys.MediaType } else { '' }
    health = if ($phys) { [string]$phys.HealthStatus } else { '' }
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
    media_type: str  # HDD / SSD / Unspecified / Image
    bus_type: str
    partition_style: str  # MBR / GPT / RAW
    health: str
    sector_size: int
    is_read_only: bool
    partitions: List[Partition] = field(default_factory=list)
    is_image: bool = False

    @property
    def is_ssd(self) -> bool:
        return "ssd" in (self.media_type or "").lower()

    @property
    def is_removable(self) -> bool:
        return (self.bus_type or "").upper() in ("USB", "SD", "MMC")


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
                partition_style=d.get("partitionStyle") or "",
                health=d.get("health") or "",
                sector_size=int(d.get("sectorSize") or 512),
                is_read_only=bool(d.get("isReadOnly")),
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
        partition_style="",
        health="",
        sector_size=512,
        is_read_only=True,
        partitions=[],
        is_image=True,
    )


def describe_size(num: int) -> str:
    return _human(num)
