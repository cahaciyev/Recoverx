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
from . import smart
from . import nativedisk

log = get_logger("devices")

_CREATE_NO_WINDOW = 0x08000000


def _powershell_exe() -> str:
    """Absolute path to powershell.exe (robust on machines with an odd PATH)."""
    root = os.environ.get("SystemRoot") or r"C:\Windows"
    p = os.path.join(root, "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
    return p if os.path.isfile(p) else "powershell"


def _run_powershell(script: str, timeout: int = 60):
    """Run a PowerShell script hidden (no console window) and capture stdout.

    Uses CREATE_NO_WINDOW so no console flashes in the --windowed app, redirects
    stdin (the GUI build has no valid stdin handle, which otherwise makes the
    child hang/fail), and bypasses execution policy for locked-down machines.
    """
    try:
        return subprocess.run(
            [_powershell_exe(), "-NoProfile", "-NonInteractive",
             "-ExecutionPolicy", "Bypass", "-Command", script],
            capture_output=True, text=True, timeout=timeout,
            stdin=subprocess.DEVNULL, creationflags=_CREATE_NO_WINDOW)
    except (OSError, subprocess.TimeoutExpired) as exc:
        log.error("PowerShell call failed: %s", exc)
        return None

# -- SMART attribute knowledge --------------------------------------------
# Names of the SMART attributes we surface / use for the health estimate.
_SMART_NAMES = {
    1: "Read Error Rate", 2: "Throughput Performance", 3: "Spin-Up Time",
    4: "Start/Stop Count", 5: "Reallocated Sectors Count", 7: "Seek Error Rate",
    8: "Seek Time Performance", 9: "Power-On Hours", 10: "Spin Retry Count",
    11: "Recalibration Retries", 12: "Power Cycle Count",
    170: "Available Reserved Space", 171: "SSD Program Fail Count",
    172: "SSD Erase Fail Count", 173: "SSD Wear Leveling Count",
    174: "Unexpected Power Loss", 175: "Power Loss Protection Failure",
    177: "Wear Range Delta", 179: "Used Reserved Block Count",
    180: "Unused Reserved Block Count", 181: "Program Fail Count",
    182: "Erase Fail Count", 183: "SATA Downshift Error Count",
    184: "End-to-End Error", 187: "Reported Uncorrectable Errors",
    188: "Command Timeout", 189: "High Fly Writes", 190: "Airflow Temperature",
    191: "G-Sense Error Rate", 192: "Power-Off Retract Count",
    193: "Load/Unload Cycle Count", 194: "Temperature", 195: "Hardware ECC Recovered",
    196: "Reallocation Event Count", 197: "Current Pending Sector Count",
    198: "Uncorrectable Sector Count", 199: "UltraDMA CRC Error Count",
    200: "Multi-Zone Error Rate", 201: "Soft Read Error Rate",
    202: "Data Address Mark Errors", 231: "SSD Life Left", 233: "Media Wearout Indicator",
    241: "Total LBAs Written", 242: "Total LBAs Read",
}

# Attributes whose normalized value approaching its threshold means end-of-life.
_CRITICAL_IDS = {1, 5, 10, 184, 187, 188, 196, 197, 198, 201}
# Attributes whose RAW count being > 0 indicates real, data-threatening damage.
_PROBLEM_RAW_IDS = {5, 196, 197, 198}
# SSD endurance indicators: the normalized VALUE is the remaining life % (100 = new).
# This is what HD Sentinel uses for SSDs (e.g. #231 "SSD Wear Indicator").
_SSD_LIFE_IDS = {169, 173, 177, 202, 231, 233}


def compute_smart_health(attributes: "List[SmartAttribute]", predict_failure: bool,
                         is_ssd: bool = False) -> Optional[int]:
    """Estimate drive health (0-100 %) from raw SMART attributes.

    Mirrors how dedicated tools (e.g. HD Sentinel) weight health: pending and
    uncorrectable sectors (data at immediate risk) hurt the most, reallocated
    sectors indicate wear, and any normalized value reaching its manufacturer
    threshold means that attribute has failed. Returns ``None`` if no SMART
    attributes are available.
    """
    if not attributes:
        return None
    by_id = {a.id: a for a in attributes}

    def raw(i: int) -> int:
        a = by_id.get(i)
        return a.raw if a else 0

    health = 100.0
    pending = raw(197)
    uncorrectable = raw(198)
    reallocated = raw(5)
    realloc_events = raw(196)

    risk = pending + uncorrectable          # currently unreadable / unstable sectors
    if risk > 0:
        health -= min(85.0, 8.0 + risk * 1.5)
    if reallocated > 0:                      # already remapped -> wear
        health -= min(55.0, 3.0 + reallocated * 0.1)
    if realloc_events > 0:
        health -= min(15.0, realloc_events * 0.2)

    # Manufacturer view: normalized value vs its failure threshold.
    for a in attributes:
        if (a.id not in _CRITICAL_IDS or a.threshold is None
                or a.threshold <= 0 or a.value <= 0):
            continue
        if a.value <= a.threshold:
            health = min(health, 1.0)        # attribute has reached end-of-life
        else:
            init = 200.0 if a.value > 100 else 100.0
            pct = (a.value - a.threshold) / max(1.0, init - a.threshold) * 100.0
            health = min(health, pct)

    # SSD wear/life indicators: the normalized value is the remaining life %.
    if is_ssd:
        temp_val = next((a.value for a in attributes if a.id == 194), None)
        for a in attributes:
            if a.id in _SSD_LIFE_IDS and 0 < a.value <= 100:
                # guard against drives that report temperature on the same id
                if temp_val is not None and abs(a.value - temp_val) <= 2:
                    continue
                health = min(health, float(a.value))

    if predict_failure:
        health = min(health, 10.0)
    return int(max(0, min(100, round(health))))


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

# Reads the raw ATA SMART attribute table via WMI (root\wmi). No third-party
# tools required; needs Administrator. Maps each disk's data to its disk number
# through Win32_DiskDrive.PNPDeviceID so health can be computed per drive.
_SMART_SCRIPT = r"""
$ErrorActionPreference = 'SilentlyContinue'
$drives = @(Get-CimInstance -ClassName Win32_DiskDrive | Select-Object Index, PNPDeviceID)
$data = @(Get-CimInstance -Namespace root\wmi -ClassName MSStorageDriver_FailurePredictData)
$thrs = @(Get-CimInstance -Namespace root\wmi -ClassName MSStorageDriver_FailurePredictThresholds)
$stat = @(Get-CimInstance -Namespace root\wmi -ClassName MSStorageDriver_FailurePredictStatus)
function Norm($s) { if ($s) { ($s -replace '_0$','').ToUpper() } else { '' } }
$out = @()
foreach ($d in $data) {
  $inst = Norm $d.InstanceName
  $drive = $null
  foreach ($dr in $drives) { if ((Norm $dr.PNPDeviceID) -eq $inst) { $drive = $dr; break } }
  if (-not $drive) { continue }
  $vs = $d.VendorSpecific
  if (-not $vs) { continue }
  $tvs = $null
  foreach ($t in $thrs) { if ((Norm $t.InstanceName) -eq $inst) { $tvs = $t.VendorSpecific; break } }
  $pf = $false; $rs = 0
  foreach ($s in $stat) { if ((Norm $s.InstanceName) -eq $inst) { $pf = [bool]$s.PredictFailure; $rs = [int]$s.Reason; break } }
  $thrMap = @{}
  if ($tvs) { for ($i = 2; ($i + 1) -lt $tvs.Count; $i += 12) { $id = [int]$tvs[$i]; if ($id -ne 0) { $thrMap[$id] = [int]$tvs[$i + 1] } } }
  $attrs = @()
  for ($i = 2; ($i + 11) -lt $vs.Count; $i += 12) {
    $id = [int]$vs[$i]; if ($id -eq 0) { continue }
    $value = [int]$vs[$i + 3]; $worst = [int]$vs[$i + 4]
    $raw = [int64]0
    for ($b = 0; $b -lt 6; $b++) { $raw = $raw -bor ([int64]$vs[$i + 5 + $b] -shl (8 * $b)) }
    $t = -1; if ($thrMap.ContainsKey($id)) { $t = [int]$thrMap[$id] }
    $attrs += [pscustomobject]@{ id = $id; value = $value; worst = $worst; threshold = $t; raw = $raw }
  }
  $out += [pscustomobject]@{ diskNumber = [int]$drive.Index; predictFailure = $pf; reason = $rs; attributes = @($attrs) }
}
@($out) | ConvertTo-Json -Depth 6 -Compress
"""


@dataclass
class SmartAttribute:
    id: int
    name: str
    value: int          # normalized current value (higher = healthier)
    worst: int
    threshold: int      # -1 if unknown
    raw: int            # vendor raw value (e.g. sector count)

    @property
    def is_problem(self) -> bool:
        if self.id in _PROBLEM_RAW_IDS and self.raw > 0:
            return True
        return self.threshold > 0 and 0 < self.value <= self.threshold

    @property
    def display_raw(self) -> int:
        # Temperature attributes pack current/min/max into the raw field; the
        # actual °C is the low byte.
        if self.id in (190, 194):
            return self.raw & 0xFF
        return self.raw


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
    smart_attributes: List[SmartAttribute] = field(default_factory=list)
    smart_health: Optional[int] = None   # 0-100 from raw SMART; None=unavailable
    predict_failure: bool = False        # drive's own imminent-failure flag
    predict_reason: int = 0
    host_writes_bytes: int = -1          # lifetime data written; -1=unknown
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
        """Health as 0-100 %. None if not available.

        Uses the worst of the available indicators: real SMART attributes
        (reallocated / pending / uncorrectable sectors) for HDDs and SATA SSDs,
        and reported endurance (wear) for SSDs. Falls back to the coarse Windows
        HealthStatus only when no SMART data is available.
        """
        candidates = []
        if self.smart_health is not None:
            candidates.append(self.smart_health)
        if self.wear >= 0:
            candidates.append(max(0, 100 - self.wear))
        if candidates:
            return min(candidates)
        if self.health:
            return {"healthy": 100, "warning": 50, "unhealthy": 10}.get(
                self.health.lower(), None
            )
        return None

    @property
    def smart_problems(self) -> "List[SmartAttribute]":
        """SMART attributes that indicate damage (bad sectors / past threshold)."""
        return [a for a in self.smart_attributes if a.is_problem]

    @property
    def power_on_hours_effective(self) -> int:
        if self.power_on_hours is not None and self.power_on_hours >= 0:
            return self.power_on_hours
        for a in self.smart_attributes:
            if a.id == 9:
                return a.raw
        return -1

    @property
    def host_writes_text(self) -> str:
        if self.host_writes_bytes is not None and self.host_writes_bytes > 0:
            return describe_size(self.host_writes_bytes)
        return ""

    @property
    def health_rating(self) -> tuple[str, str]:
        """Return ``(word, colour)`` like HD Sentinel (Excellent/Good/…)."""
        pct = self.health_percent
        if pct is None:
            return "Unknown", "#6b7280"
        if pct >= 80:
            return "Excellent", "#16a34a"
        if pct >= 60:
            return "Good", "#22c55e"
        if pct >= 40:
            return "Fair", "#d97706"
        if pct >= 20:
            return "Poor", "#ea580c"
        return "Critical", "#dc2626"

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
        poh = self.power_on_hours_effective
        if poh is None or poh < 0:
            return "Naməlum"
        days = poh // 24
        hours = poh % 24
        if days >= 365:
            years = days // 365
            rem_days = days % 365
            return f"{years} il {rem_days} gün ({poh:,} saat)"
        if days > 0:
            return f"{days} gün {hours} saat ({poh:,} saat)"
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


def _nvme_health(nvme: dict) -> int:
    """Health (0-100 %) from an NVMe SMART/health log."""
    used = nvme.get("percentage_used", 0)
    spare = nvme.get("available_spare", 100)
    spare_thr = nvme.get("available_spare_threshold", 0)
    crit = nvme.get("critical_warning", 0)
    health = 100 - min(int(used), 100)        # endurance consumed
    if spare_thr and spare < spare_thr:        # running out of spare blocks
        health = min(health, max(int(spare), 1))
    if crit:                                   # any critical warning bit set
        health = min(health, 10)
    return int(max(0, min(100, health)))


def _nvme_attributes(nvme: dict) -> List[SmartAttribute]:
    """Synthesize display rows from the NVMe health log."""
    used = int(nvme.get("percentage_used", 0))
    spare = int(nvme.get("available_spare", 100))
    spare_thr = int(nvme.get("available_spare_threshold", 0))
    temp = int(nvme.get("temperature_c", -1))
    return [
        SmartAttribute(902, "Percentage Used (life consumed)", max(0, 100 - used),
                       max(0, 100 - used), 10, used),
        SmartAttribute(901, "Available Spare", spare, spare, spare_thr, spare),
        SmartAttribute(900, "Critical Warning", 100, 100, -1, int(nvme.get("critical_warning", 0))),
        SmartAttribute(903, "Media/Data Integrity Errors", 100, 100, -1,
                       int(nvme.get("media_errors", 0))),
        SmartAttribute(904, "Unsafe Shutdowns", 100, 100, -1, int(nvme.get("unsafe_shutdowns", 0))),
        SmartAttribute(194, "Temperature", temp if temp >= 0 else 0, 0, 0, max(temp, 0)),
        SmartAttribute(9, "Power-On Hours", 100, 100, 0, int(nvme.get("power_on_hours", -1))),
    ]


def _smart_result_to_fields(result: dict, is_ssd: bool = False):
    """Convert a raw SMART result dict to ``(attributes, health, predict_failure)``."""
    if result.get("type") == "ata":
        attrs = [SmartAttribute(a[0], _SMART_NAMES.get(a[0], f"Attribute {a[0]}"),
                                a[1], a[2], a[3], a[4]) for a in result["attributes"]]
        predict = any(a.id in _CRITICAL_IDS and a.threshold > 0 and 0 < a.value <= a.threshold
                      for a in attrs)
        return attrs, compute_smart_health(attrs, predict, is_ssd), predict
    if result.get("type") == "nvme":
        nv = result["nvme"]
        predict = (bool(nv.get("critical_warning"))
                   or (nv.get("available_spare", 100) < nv.get("available_spare_threshold", 0))
                   or int(nv.get("percentage_used", 0)) >= 100)
        return _nvme_attributes(nv), _nvme_health(nv), predict
    return [], None, False


def _direct_smart(number, bus_phys: str, is_ssd: bool = False):
    """Read SMART directly from the device via ctypes (no PowerShell). Returns
    ``(attributes, health, predict_failure)`` or ``None``."""
    if number is None:
        return None
    try:
        result = smart.read_physical_smart(
            int(number), prefer_nvme="NVME" in (bus_phys or "").upper())
    except Exception as exc:  # noqa: BLE001
        log.debug("Direct SMART read failed for disk %s: %s", number, exc)
        return None
    if not result:
        return None
    return _smart_result_to_fields(result, is_ssd)


def _smart_by_disk() -> dict:
    """Return ``{disk_number: (attributes, predict_failure, reason)}`` from WMI SMART."""
    proc = _run_powershell(_SMART_SCRIPT)
    out = (proc.stdout or "").strip() if proc else ""
    if not out:
        return {}
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        log.warning("Could not parse SMART JSON")
        return {}
    if isinstance(data, dict):
        data = [data]
    result: dict = {}
    for entry in data:
        num = entry.get("diskNumber")
        if num is None:
            continue
        attrs: List[SmartAttribute] = []
        for a in entry.get("attributes") or []:
            try:
                aid = int(a.get("id"))
            except (TypeError, ValueError):
                continue
            attrs.append(SmartAttribute(
                id=aid,
                name=_SMART_NAMES.get(aid, f"Attribute {aid}"),
                value=int(a.get("value", 0)),
                worst=int(a.get("worst", 0)),
                threshold=int(a.get("threshold", -1)),
                raw=int(a.get("raw", 0)),
            ))
        result[int(num)] = (attrs, bool(entry.get("predictFailure")), int(entry.get("reason") or 0))
    if result:
        log.info("Read SMART data for %d disk(s)", len(result))
    return result


def list_devices() -> List[Device]:
    """Enumerate physical disks and their partitions (read-only metadata).

    PowerShell (Storage cmdlets) is tried first for the richest data; if it is
    unavailable, blocked or returns nothing, a native Win32 enumeration is used
    so disks are still detected on any machine (and without Administrator).
    """
    data = []
    proc = _run_powershell(_PS_SCRIPT)
    out = (proc.stdout or "").strip() if proc else ""
    if out:
        try:
            data = json.loads(out)
        except json.JSONDecodeError as exc:
            log.error("Failed to parse device JSON: %s", exc)
            data = []
    if isinstance(data, dict):
        data = [data]
    if not data:
        log.warning("PowerShell returned no disks; using native enumeration.")
        data = nativedisk.enumerate_disks()

    # Preferred: native smarthelper.exe (ATA + ATA pass-through + NVMe).
    helper_map = smart.read_all_via_helper()

    devices: List[Device] = []
    fallback_needed: List[tuple] = []   # (device, disk_number) when direct read failed
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
        disk_num = d.get("number")
        bus_phys = d.get("busTypePhys") or d.get("busType") or ""
        bus_up = bus_phys.upper()
        removable = bus_up in ("USB", "SD", "MMC")
        predict_reason = 0
        host_writes = -1
        is_ssd_disk = "SSD" in (d.get("mediaType") or "").upper()
        # Native helper first, then ctypes direct read.
        result = helper_map.get(int(disk_num)) if disk_num is not None else None
        if result is None and disk_num is not None:
            try:
                result = smart.read_physical_smart(
                    int(disk_num), prefer_nvme="NVME" in bus_up)
            except Exception:  # noqa: BLE001
                result = None
        if result:
            smart_attrs, smart_health, predict_fail = _smart_result_to_fields(result, is_ssd_disk)
            if result.get("type") == "nvme":
                duw = result["nvme"].get("data_units_written", 0)
                if duw:
                    host_writes = duw * 512000      # NVMe data unit = 512000 bytes
        else:
            smart_attrs, smart_health, predict_fail = [], None, False

        # Temperature: prefer the reliability counter, else fall back to SMART.
        temp_c = int(d.get("temperature") if d.get("temperature") is not None else -1)
        if temp_c < 0:
            for a in smart_attrs:
                if a.id in (194, 190) and a.display_raw > 0:
                    temp_c = a.display_raw
                    break
        dev = Device(
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
                temperature=temp_c,
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
                smart_attributes=smart_attrs,
                smart_health=smart_health,
                predict_failure=predict_fail,
                predict_reason=predict_reason,
                host_writes_bytes=host_writes,
                partitions=parts,
        )
        devices.append(dev)
        if result is None and not removable and disk_num is not None:
            fallback_needed.append((dev, int(disk_num)))

    # Only touch WMI (PowerShell) for fixed disks where the direct read failed.
    if fallback_needed:
        wmi_map = _smart_by_disk()
        for dev, num in fallback_needed:
            attrs, predict_fail, reason = wmi_map.get(num, ([], False, 0))
            if attrs:
                dev.smart_attributes = attrs
                dev.smart_health = compute_smart_health(attrs, predict_fail, dev.is_ssd)
                dev.predict_failure = predict_fail
                dev.predict_reason = reason

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
