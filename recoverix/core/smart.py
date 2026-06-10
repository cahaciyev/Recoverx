"""Low-level, direct SMART/health reader (Windows, no PowerShell).

Reads the *same* raw data professional tools (CrystalDiskInfo, smartmontools,
HD Sentinel) read, by talking to the device driver directly through the Win32
``DeviceIoControl`` API via :mod:`ctypes` — i.e. C-level system calls, not WMI.

Two transports are implemented:

* **ATA / SATA** drives - ``SMART_RCV_DRIVE_DATA`` (SMART READ DATA + READ
  THRESHOLDS) returns the 512-byte attribute table (id, value, worst, raw).
* **NVMe** drives - ``IOCTL_STORAGE_QUERY_PROPERTY`` returns the NVMe SMART /
  Health log (Percentage Used, Available Spare, media errors, temperature …),
  which WMI does not expose. This is why NVMe drives previously showed 100 %.

Everything is read-only and requires Administrator. Any failure returns ``None``
so callers can fall back to WMI / Windows HealthStatus.
"""
from __future__ import annotations

import ctypes
import json
import os
import subprocess
import sys
from ctypes import wintypes
from typing import List, Optional, Tuple

from .logging_setup import get_logger

log = get_logger("smart")

_CREATE_NO_WINDOW = 0x08000000

# -- Win32 plumbing --------------------------------------------------------
try:
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _AVAILABLE = True
except (AttributeError, OSError):   # non-Windows: feature simply unavailable
    _kernel32 = None
    _AVAILABLE = False

GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
OPEN_EXISTING = 3
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

SMART_RCV_DRIVE_DATA = 0x0007C088
IOCTL_STORAGE_QUERY_PROPERTY = 0x002D1400

SMART_READ_DATA = 0xD0
SMART_READ_THRESHOLDS = 0xD1

if _AVAILABLE:
    _CreateFileW = _kernel32.CreateFileW
    _CreateFileW.restype = wintypes.HANDLE
    _CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                             wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]

    _DeviceIoControl = _kernel32.DeviceIoControl
    _DeviceIoControl.restype = wintypes.BOOL
    _DeviceIoControl.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD,
                                 wintypes.LPVOID, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
                                 wintypes.LPVOID]

    _CloseHandle = _kernel32.CloseHandle
    _CloseHandle.argtypes = [wintypes.HANDLE]


def _open_drive(number: int) -> Optional[int]:
    path = f"\\\\.\\PhysicalDrive{number}"
    for access in (GENERIC_READ | GENERIC_WRITE, GENERIC_READ):
        h = _CreateFileW(path, access, FILE_SHARE_READ | FILE_SHARE_WRITE,
                         None, OPEN_EXISTING, 0, None)
        if h and h != INVALID_HANDLE_VALUE:
            return h
    return None


# -- ATA SMART structures --------------------------------------------------
class _IDEREGS(ctypes.Structure):
    _fields_ = [("bFeaturesReg", ctypes.c_ubyte), ("bSectorCountReg", ctypes.c_ubyte),
                ("bSectorNumberReg", ctypes.c_ubyte), ("bCylLowReg", ctypes.c_ubyte),
                ("bCylHighReg", ctypes.c_ubyte), ("bDriveHeadReg", ctypes.c_ubyte),
                ("bCommandReg", ctypes.c_ubyte), ("bReserved", ctypes.c_ubyte)]


class _SENDCMDINPARAMS(ctypes.Structure):
    _fields_ = [("cBufferSize", ctypes.c_ulong), ("irDriveRegs", _IDEREGS),
                ("bDriveNumber", ctypes.c_ubyte), ("bReserved", ctypes.c_ubyte * 3),
                ("dwReserved", ctypes.c_ulong * 4), ("bBuffer", ctypes.c_ubyte * 1)]


class _DRIVERSTATUS(ctypes.Structure):
    _fields_ = [("bDriverError", ctypes.c_ubyte), ("bIDEError", ctypes.c_ubyte),
                ("bReserved", ctypes.c_ubyte * 2), ("dwReserved", ctypes.c_ulong * 2)]


class _SENDCMDOUTPARAMS(ctypes.Structure):
    _fields_ = [("cBufferSize", ctypes.c_ulong), ("DriverStatus", _DRIVERSTATUS),
                ("bBuffer", ctypes.c_ubyte * 512)]


def _ata_command(handle: int, feature: int) -> Optional[bytes]:
    """Issue a SMART READ DATA / READ THRESHOLDS command; return the 512-byte buffer."""
    sci = _SENDCMDINPARAMS()
    sci.cBufferSize = 512
    sci.bDriveNumber = 0
    regs = sci.irDriveRegs
    regs.bFeaturesReg = feature
    regs.bSectorCountReg = 1
    regs.bSectorNumberReg = 1
    regs.bCylLowReg = 0x4F
    regs.bCylHighReg = 0xC2
    regs.bDriveHeadReg = 0xA0
    regs.bCommandReg = 0xB0     # SMART command
    out = _SENDCMDOUTPARAMS()
    returned = wintypes.DWORD(0)
    ok = _DeviceIoControl(handle, SMART_RCV_DRIVE_DATA,
                          ctypes.byref(sci), ctypes.sizeof(sci),
                          ctypes.byref(out), ctypes.sizeof(out),
                          ctypes.byref(returned), None)
    if not ok:
        return None
    return bytes(out.bBuffer)


def _read_ata(number: int) -> Optional[dict]:
    handle = _open_drive(number)
    if handle is None:
        return None
    try:
        data = _ata_command(handle, SMART_READ_DATA)
        if not data:
            return None
        thr = _ata_command(handle, SMART_READ_THRESHOLDS)
    finally:
        _CloseHandle(handle)

    thr_map = {}
    if thr:
        for i in range(2, len(thr) - 11, 12):
            aid = thr[i]
            if aid:
                thr_map[aid] = thr[i + 1]

    attrs: List[Tuple[int, int, int, int, int]] = []
    for i in range(2, len(data) - 11, 12):
        aid = data[i]
        if aid == 0:
            continue
        value = data[i + 3]
        worst = data[i + 4]
        raw = int.from_bytes(data[i + 5:i + 11], "little")
        threshold = thr_map.get(aid, -1)
        attrs.append((aid, value, worst, threshold, raw))
    if not attrs:
        return None
    return {"type": "ata", "attributes": attrs}


# -- NVMe health log -------------------------------------------------------
StorageDeviceProtocolSpecificProperty = 50
PropertyStandardQuery = 0
ProtocolTypeNvme = 3
NVMeDataTypeLogPage = 2


class _STORAGE_PROTOCOL_SPECIFIC_DATA(ctypes.Structure):
    _fields_ = [("ProtocolType", ctypes.c_int), ("DataType", ctypes.c_ulong),
                ("ProtocolDataRequestValue", ctypes.c_ulong),
                ("ProtocolDataRequestSubValue", ctypes.c_ulong),
                ("ProtocolDataOffset", ctypes.c_ulong), ("ProtocolDataLength", ctypes.c_ulong),
                ("FixedProtocolReturnData", ctypes.c_ulong),
                ("ProtocolDataRequestSubValue2", ctypes.c_ulong),
                ("ProtocolDataRequestSubValue3", ctypes.c_ulong),
                ("ProtocolDataRequestSubValue4", ctypes.c_ulong)]


class _STORAGE_PROPERTY_QUERY(ctypes.Structure):
    _fields_ = [("PropertyId", ctypes.c_int), ("QueryType", ctypes.c_int),
                ("ProtocolSpecific", _STORAGE_PROTOCOL_SPECIFIC_DATA)]


class _STORAGE_PROTOCOL_DATA_DESCRIPTOR(ctypes.Structure):
    _fields_ = [("Version", ctypes.c_ulong), ("Size", ctypes.c_ulong),
                ("ProtocolSpecificData", _STORAGE_PROTOCOL_SPECIFIC_DATA)]


def _read_nvme(number: int) -> Optional[dict]:
    handle = _open_drive(number)
    if handle is None:
        return None
    try:
        buf_size = 4096
        buf = (ctypes.c_ubyte * buf_size)()
        query = ctypes.cast(buf, ctypes.POINTER(_STORAGE_PROPERTY_QUERY)).contents
        query.PropertyId = StorageDeviceProtocolSpecificProperty
        query.QueryType = PropertyStandardQuery
        ps = query.ProtocolSpecific
        ps.ProtocolType = ProtocolTypeNvme
        ps.DataType = NVMeDataTypeLogPage
        ps.ProtocolDataRequestValue = 0x02          # SMART / Health Information log
        ps.ProtocolDataOffset = ctypes.sizeof(_STORAGE_PROTOCOL_SPECIFIC_DATA)
        ps.ProtocolDataLength = 512
        returned = wintypes.DWORD(0)
        ok = _DeviceIoControl(handle, IOCTL_STORAGE_QUERY_PROPERTY,
                              buf, buf_size, buf, buf_size, ctypes.byref(returned), None)
        if not ok:
            return None
        desc = ctypes.cast(buf, ctypes.POINTER(_STORAGE_PROTOCOL_DATA_DESCRIPTOR)).contents
        off = ctypes.sizeof(_STORAGE_PROTOCOL_DATA_DESCRIPTOR) - \
            ctypes.sizeof(_STORAGE_PROTOCOL_SPECIFIC_DATA) + desc.ProtocolSpecificData.ProtocolDataOffset
        data = bytes(buf[off:off + 512])
    finally:
        _CloseHandle(handle)
    if len(data) < 512 or not any(data):
        return None

    critical = data[0]
    temp_k = data[1] | (data[2] << 8)
    nvme = {
        "critical_warning": critical,
        "temperature_c": (temp_k - 273) if temp_k else -1,
        "available_spare": data[3],
        "available_spare_threshold": data[4],
        "percentage_used": data[5],
        "data_units_read": int.from_bytes(data[32:48], "little"),
        "data_units_written": int.from_bytes(data[48:64], "little"),
        "power_cycles": int.from_bytes(data[112:128], "little"),
        "power_on_hours": int.from_bytes(data[128:144], "little"),
        "unsafe_shutdowns": int.from_bytes(data[144:160], "little"),
        "media_errors": int.from_bytes(data[160:176], "little"),
    }
    return {"type": "nvme", "nvme": nvme}


# -- native C++ helper (preferred; widest coverage) -----------------------
def _helper_path() -> Optional[str]:
    """Locate the bundled smarthelper.exe in source or PyInstaller layouts."""
    candidates = []
    base = getattr(sys, "_MEIPASS", None)
    if base:
        candidates.append(os.path.join(base, "recoverix", "resources", "smarthelper.exe"))
        candidates.append(os.path.join(base, "resources", "smarthelper.exe"))
    here = os.path.dirname(os.path.abspath(__file__))   # recoverix/core
    candidates.append(os.path.join(here, "..", "resources", "smarthelper.exe"))
    for c in candidates:
        if os.path.isfile(c):
            return os.path.abspath(c)
    return None


def read_all_via_helper() -> dict:
    """Run the native smarthelper.exe and return ``{disk_number: result}``.

    Same result shape as :func:`read_physical_smart`. Returns ``{}`` if the
    helper is missing or fails (callers then fall back to the ctypes path).
    """
    exe = _helper_path()
    if not exe:
        return {}
    try:
        proc = subprocess.run([exe], capture_output=True, text=True, timeout=30,
                              creationflags=_CREATE_NO_WINDOW)
        out = (proc.stdout or "").strip()
        data = json.loads(out) if out else []
    except Exception as exc:  # noqa: BLE001
        log.debug("smarthelper.exe failed: %s", exc)
        return {}
    result: dict = {}
    for entry in data:
        num = entry.get("disk")
        if num is None:
            continue
        if entry.get("type") == "ata":
            attrs = [(a["id"], a["value"], a["worst"], a["threshold"], a["raw"])
                     for a in entry.get("attributes", [])]
            if attrs:
                result[int(num)] = {"type": "ata", "attributes": attrs}
        elif entry.get("type") == "nvme":
            nv = entry.get("nvme", {})
            result[int(num)] = {"type": "nvme", "nvme": {
                "critical_warning": nv.get("criticalWarning", 0),
                "temperature_c": nv.get("temperature", -1),
                "available_spare": nv.get("availableSpare", 100),
                "available_spare_threshold": nv.get("availableSpareThreshold", 0),
                "percentage_used": nv.get("percentageUsed", 0),
                "power_on_hours": nv.get("powerOnHours", -1),
                "media_errors": nv.get("mediaErrors", 0),
                "unsafe_shutdowns": nv.get("unsafeShutdowns", 0),
                "power_cycles": nv.get("powerCycles", 0),
                "data_units_read": nv.get("dataUnitsRead", 0),
                "data_units_written": nv.get("dataUnitsWritten", 0),
            }}
    return result


# -- public API ------------------------------------------------------------
def read_physical_smart(number: int, prefer_nvme: bool = False) -> Optional[dict]:
    """Read SMART/health for physical drive ``number`` directly via the OS driver.

    Returns a dict with ``type`` 'ata' or 'nvme' (see module docstring), or
    ``None`` if the drive exposes neither (e.g. some USB bridges).
    """
    if not _AVAILABLE:
        return None
    order = (_read_nvme, _read_ata) if prefer_nvme else (_read_ata, _read_nvme)
    for reader in order:
        try:
            result = reader(number)
        except Exception as exc:  # noqa: BLE001 - never break enumeration
            log.debug("SMART %s on drive %d failed: %s", reader.__name__, number, exc)
            result = None
        if result:
            return result
    return None
