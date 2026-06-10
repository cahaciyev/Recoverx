"""Native (Win32 / ctypes) physical-disk and volume enumeration.

A robust, dependency-free fallback for device detection: it talks to the OS
directly through ``DeviceIoControl`` and the volume APIs instead of PowerShell,
so it works on locked-down machines where PowerShell is blocked/slow and even
*without* Administrator (the metadata IOCTLs open the drive with zero access).

``enumerate_disks()`` returns the same list-of-dicts schema the PowerShell
enumerator produces, so :mod:`devices` can consume either transparently.
"""
from __future__ import annotations

import ctypes
import string
from ctypes import wintypes
from typing import List, Optional

from .logging_setup import get_logger

log = get_logger("nativedisk")

try:
    _k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _AVAILABLE = True
except (AttributeError, OSError):
    _k32 = None
    _AVAILABLE = False

GENERIC_READ = 0x80000000
FILE_SHARE_READ = 0x01
FILE_SHARE_WRITE = 0x02
OPEN_EXISTING = 3
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

IOCTL_DISK_GET_LENGTH_INFO = 0x0007405C
IOCTL_DISK_GET_DRIVE_GEOMETRY = 0x00070000
IOCTL_DISK_GET_DRIVE_GEOMETRY_EX = 0x000700A0
IOCTL_DISK_GET_DRIVE_LAYOUT_EX = 0x00070050
IOCTL_STORAGE_QUERY_PROPERTY = 0x002D1400
IOCTL_VOLUME_GET_VOLUME_DISK_EXTENTS = 0x00560000

StorageDeviceProperty = 0
StorageDeviceSeekPenaltyProperty = 7
PropertyStandardQuery = 0

_BUS = {1: "SCSI", 2: "ATAPI", 3: "ATA", 4: "1394", 5: "SSA", 6: "Fibre", 7: "USB",
        8: "RAID", 9: "iSCSI", 10: "SAS", 11: "SATA", 12: "SD", 13: "MMC", 14: "Virtual",
        15: "FileBackedVirtual", 16: "StorageSpaces", 17: "NVMe", 18: "SCM", 19: "UFS"}


def _setup():
    _k32.CreateFileW.restype = wintypes.HANDLE
    _k32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                 wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    _k32.DeviceIoControl.restype = wintypes.BOOL
    _k32.DeviceIoControl.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD,
                                     wintypes.LPVOID, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
                                     wintypes.LPVOID]
    _k32.CloseHandle.argtypes = [wintypes.HANDLE]
    _k32.GetLogicalDrives.restype = wintypes.DWORD
    _k32.GetDriveTypeW.restype = wintypes.UINT
    _k32.GetDriveTypeW.argtypes = [wintypes.LPCWSTR]
    _k32.GetVolumeInformationW.restype = wintypes.BOOL
    _k32.GetVolumeInformationW.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD,
                                           wintypes.LPVOID, wintypes.LPVOID, wintypes.LPVOID,
                                           wintypes.LPWSTR, wintypes.DWORD]
    _k32.GetDiskFreeSpaceExW.restype = wintypes.BOOL
    _k32.GetDiskFreeSpaceExW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_ulonglong),
                                         ctypes.POINTER(ctypes.c_ulonglong),
                                         ctypes.POINTER(ctypes.c_ulonglong)]


if _AVAILABLE:
    _setup()


# -- structures ------------------------------------------------------------
class _STORAGE_PROPERTY_QUERY(ctypes.Structure):
    _fields_ = [("PropertyId", ctypes.c_int), ("QueryType", ctypes.c_int),
                ("AdditionalParameters", ctypes.c_ubyte * 1)]


class _STORAGE_DEVICE_DESCRIPTOR(ctypes.Structure):
    _fields_ = [("Version", ctypes.c_ulong), ("Size", ctypes.c_ulong),
                ("DeviceType", ctypes.c_ubyte), ("DeviceTypeModifier", ctypes.c_ubyte),
                ("RemovableMedia", ctypes.c_ubyte), ("CommandQueueing", ctypes.c_ubyte),
                ("VendorIdOffset", ctypes.c_ulong), ("ProductIdOffset", ctypes.c_ulong),
                ("ProductRevisionOffset", ctypes.c_ulong), ("SerialNumberOffset", ctypes.c_ulong),
                ("BusType", ctypes.c_int), ("RawPropertiesLength", ctypes.c_ulong),
                ("RawDeviceProperties", ctypes.c_ubyte * 1)]


class _DEVICE_SEEK_PENALTY_DESCRIPTOR(ctypes.Structure):
    _fields_ = [("Version", ctypes.c_ulong), ("Size", ctypes.c_ulong),
                ("IncursSeekPenalty", ctypes.c_ubyte)]


class _DISK_GEOMETRY(ctypes.Structure):
    _fields_ = [("Cylinders", ctypes.c_longlong), ("MediaType", ctypes.c_int),
                ("TracksPerCylinder", ctypes.c_ulong), ("SectorsPerTrack", ctypes.c_ulong),
                ("BytesPerSector", ctypes.c_ulong)]


class _DISK_GEOMETRY_EX(ctypes.Structure):
    _fields_ = [("Geometry", _DISK_GEOMETRY), ("DiskSize", ctypes.c_longlong),
                ("Data", ctypes.c_ubyte * 512)]


class _DISK_EXTENT(ctypes.Structure):
    _fields_ = [("DiskNumber", ctypes.c_ulong), ("StartingOffset", ctypes.c_longlong),
                ("ExtentLength", ctypes.c_longlong)]


class _VOLUME_DISK_EXTENTS(ctypes.Structure):
    _fields_ = [("NumberOfDiskExtents", ctypes.c_ulong), ("Extents", _DISK_EXTENT * 16)]


def _open(path: str, access: int = 0) -> Optional[int]:
    h = _k32.CreateFileW(path, access, FILE_SHARE_READ | FILE_SHARE_WRITE, None,
                         OPEN_EXISTING, 0, None)
    if h == INVALID_HANDLE_VALUE or not h:
        return None
    return h


def _ioctl(handle: int, code: int, in_buf, out_buf) -> bool:
    returned = wintypes.DWORD(0)
    in_ref = ctypes.byref(in_buf) if in_buf is not None else None
    in_len = ctypes.sizeof(in_buf) if in_buf is not None else 0
    ok = _k32.DeviceIoControl(handle, code, in_ref, in_len,
                              ctypes.byref(out_buf), ctypes.sizeof(out_buf),
                              ctypes.byref(returned), None)
    return bool(ok)


def _ascii_at(buf: bytes, offset: int) -> str:
    if offset <= 0 or offset >= len(buf):
        return ""
    end = buf.find(b"\x00", offset)
    if end == -1:
        end = len(buf)
    return buf[offset:end].decode("ascii", "ignore").strip()


def _disk_info(number: int) -> Optional[dict]:
    h = _open(f"\\\\.\\PhysicalDrive{number}")
    if h is None:
        return None
    try:
        # size + sector via GEOMETRY_EX (works with a zero-access handle)
        size = 0
        sector = 512
        gex = _DISK_GEOMETRY_EX()
        if _ioctl(h, IOCTL_DISK_GET_DRIVE_GEOMETRY_EX, None, gex):
            size = int(gex.DiskSize)
            if gex.Geometry.BytesPerSector:
                sector = int(gex.Geometry.BytesPerSector)
        if size == 0:                       # fallback (needs read access)
            length = ctypes.c_longlong(0)
            if _ioctl(h, IOCTL_DISK_GET_LENGTH_INFO, None, length):
                size = int(length.value)
        # model / serial / bus / removable
        model = serial = ""
        bus = 0
        removable = False
        query = _STORAGE_PROPERTY_QUERY()
        query.PropertyId = StorageDeviceProperty
        query.QueryType = PropertyStandardQuery
        out = (ctypes.c_ubyte * 1024)()
        returned = wintypes.DWORD(0)
        if _k32.DeviceIoControl(h, IOCTL_STORAGE_QUERY_PROPERTY, ctypes.byref(query),
                                ctypes.sizeof(query), out, ctypes.sizeof(out),
                                ctypes.byref(returned), None):
            raw = bytes(out)
            desc = ctypes.cast(out, ctypes.POINTER(_STORAGE_DEVICE_DESCRIPTOR)).contents
            bus = int(desc.BusType)
            removable = bool(desc.RemovableMedia)
            vendor = _ascii_at(raw, desc.VendorIdOffset)
            product = _ascii_at(raw, desc.ProductIdOffset)
            serial = _ascii_at(raw, desc.SerialNumberOffset)
            model = (f"{vendor} {product}".strip() or product or "Unknown Disk")
        # SSD vs HDD via seek penalty
        media = ""
        q2 = _STORAGE_PROPERTY_QUERY()
        q2.PropertyId = StorageDeviceSeekPenaltyProperty
        q2.QueryType = PropertyStandardQuery
        sp = _DEVICE_SEEK_PENALTY_DESCRIPTOR()
        if _ioctl(h, IOCTL_STORAGE_QUERY_PROPERTY, q2, sp):
            media = "HDD" if sp.IncursSeekPenalty else "SSD"
        # partition style (first DWORD of DRIVE_LAYOUT_INFORMATION_EX)
        pstyle = ""
        layout = (ctypes.c_ubyte * 4096)()
        if _k32.DeviceIoControl(h, IOCTL_DISK_GET_DRIVE_LAYOUT_EX, None, 0,
                                layout, ctypes.sizeof(layout), ctypes.byref(returned), None):
            style = int.from_bytes(bytes(layout)[0:4], "little")
            pstyle = {0: "MBR", 1: "GPT", 2: "RAW"}.get(style, "")
    finally:
        _k32.CloseHandle(h)

    bus_name = _BUS.get(bus, "")
    return {
        "number": number,
        "path": f"\\\\.\\PHYSICALDRIVE{number}",
        "model": model or "Unknown Disk",
        "manufacturer": "",
        "serial": serial,
        "size": size,
        "partitionStyle": pstyle,
        "busType": bus_name,
        "busTypePhys": bus_name,
        "mediaType": media,
        "health": "",
        "firmware": "",
        "allocatedSize": -1,
        "spindleSpeed": -1,
        "operationalStatus": "",
        "physicalSectorSize": -1,
        "wear": -1, "temperature": -1, "temperatureMax": -1, "powerOnHours": -1,
        "readErrorsTotal": -1, "writeErrorsTotal": -1, "startStopCycles": -1,
        "loadUnloadCycles": -1, "manufactureDate": "",
        "sectorSize": sector,
        "isReadOnly": False,
        "_removable": removable,
        "partitions": [],
    }


def _volume_partitions() -> dict:
    """Map disk number -> list of partition dicts, built from mounted volumes."""
    by_disk: dict = {}
    try:
        bitmask = _k32.GetLogicalDrives()
    except Exception:  # noqa: BLE001
        return by_disk
    for i in range(26):
        if not (bitmask >> i) & 1:
            continue
        letter = string.ascii_uppercase[i]
        root = f"{letter}:\\"
        if _k32.GetDriveTypeW(root) not in (2, 3):   # 2=removable, 3=fixed
            continue
        # filesystem + label
        label_buf = ctypes.create_unicode_buffer(261)
        fs_buf = ctypes.create_unicode_buffer(261)
        _k32.GetVolumeInformationW(root, label_buf, 261, None, None, None, fs_buf, 261)
        # free / total
        free = ctypes.c_ulonglong(0)
        total = ctypes.c_ulonglong(0)
        _k32.GetDiskFreeSpaceExW(root, ctypes.byref(free), ctypes.byref(total), None)
        # which disk(s) back this volume
        h = _open(f"\\\\.\\{letter}:")
        if h is None:
            continue
        try:
            ext = _VOLUME_DISK_EXTENTS()
            returned = wintypes.DWORD(0)
            ok = _k32.DeviceIoControl(h, IOCTL_VOLUME_GET_VOLUME_DISK_EXTENTS, None, 0,
                                      ctypes.byref(ext), ctypes.sizeof(ext),
                                      ctypes.byref(returned), None)
        finally:
            _k32.CloseHandle(h)
        if not ok:
            continue
        for j in range(min(ext.NumberOfDiskExtents, 16)):
            e = ext.Extents[j]
            lst = by_disk.setdefault(int(e.DiskNumber), [])
            lst.append({
                "partitionNumber": len(lst) + 1,
                "offset": int(e.StartingOffset),
                "size": int(e.ExtentLength),
                "driveLetter": letter,
                "type": "",
                "fileSystem": fs_buf.value or None,
                "label": label_buf.value or None,
                "sizeRemaining": int(free.value),
            })
    return by_disk


def enumerate_disks() -> List[dict]:
    """Return physical disks (with mounted partitions) using only Win32 APIs."""
    if not _AVAILABLE:
        return []
    parts = _volume_partitions()
    disks: List[dict] = []
    misses = 0
    for number in range(64):
        info = _disk_info(number)
        if info is None:
            misses += 1
            if misses >= 4 and not disks:
                break          # no disks at the start -> stop early
            if misses >= 8:
                break          # gap past the last disk
            continue
        misses = 0
        info["partitions"] = parts.get(number, [])
        disks.append(info)
    if disks:
        log.info("Native enumeration found %d disk(s)", len(disks))
    return disks
