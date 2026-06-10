// smarthelper.exe - native low-level SMART / NVMe health reader for Recoverix.
//
// Reads drive health the same way professional tools do: by issuing device
// commands directly through the Win32 DeviceIoControl API. Three methods are
// tried per drive so the widest range of hardware is covered:
//
//   1. NVMe SMART/Health log   (IOCTL_STORAGE_QUERY_PROPERTY)
//   2. ATA SMART READ DATA     (SMART_RCV_DRIVE_DATA)        - most SATA drives
//   3. ATA pass-through        (IOCTL_ATA_PASS_THROUGH)      - USB/AHCI bridges
//
// Output: a JSON array on stdout, one object per drive that exposed health
// data, keyed by physical-drive number. Read-only; requires Administrator.
//
// Build (x64):
//   call vcvars64.bat
//   cl /EHsc /O2 /nologo native\smarthelper.cpp /Fe:recoverix\resources\smarthelper.exe

#include <windows.h>
#include <cstdio>
#include <cstdint>

#define IOCTL_SMART_RCV_DRIVE_DATA       0x0007C088
#define IOCTL_ATA_PASS_THROUGH           0x0004D02C
#define IOCTL_STORAGE_QUERY_PROPERTY_X   0x002D1400

// ---- ATA SMART (SMART_RCV_DRIVE_DATA) -----------------------------------
struct IDEREGS_ { BYTE f, sc, sn, cl, ch, dh, cmd, rsv; };
struct SENDCMDINPARAMS_ {
    DWORD cBufferSize; IDEREGS_ ir; BYTE bDriveNumber; BYTE rsv[3]; DWORD dwRsv[4]; BYTE bBuffer[1];
};
struct DRIVERSTATUS_ { BYTE e1, e2; BYTE r[2]; DWORD dr[2]; };
struct SENDCMDOUTPARAMS_ { DWORD cBufferSize; DRIVERSTATUS_ ds; BYTE bBuffer[512]; };

// ---- ATA pass-through ----------------------------------------------------
struct ATA_PT_EX {
    USHORT Length; USHORT AtaFlags; UCHAR PathId, TargetId, Lun, Rsv;
    ULONG DataTransferLength; ULONG TimeOutValue; ULONG RsvUlong;
    ULONG_PTR DataBufferOffset; UCHAR Prev[8]; UCHAR Cur[8];
};

// ---- NVMe protocol-specific query ---------------------------------------
struct SPSD {
    int ProtocolType; ULONG DataType; ULONG ReqValue; ULONG ReqSub;
    ULONG DataOffset; ULONG DataLength; ULONG Fixed; ULONG s2, s3, s4;
};
struct SPQ { int PropertyId; int QueryType; SPSD ps; };
struct SPDD { ULONG Version; ULONG Size; SPSD ps; };

static uint64_t le(const BYTE* b, int n) {
    uint64_t v = 0;
    for (int i = 0; i < n; i++) v |= (uint64_t)b[i] << (8 * i);
    return v;
}

static HANDLE openDrive(int n) {
    wchar_t path[64];
    wsprintfW(path, L"\\\\.\\PhysicalDrive%d", n);
    HANDLE h = CreateFileW(path, GENERIC_READ | GENERIC_WRITE,
                           FILE_SHARE_READ | FILE_SHARE_WRITE, NULL, OPEN_EXISTING, 0, NULL);
    if (h == INVALID_HANDLE_VALUE)
        h = CreateFileW(path, GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE,
                        NULL, OPEN_EXISTING, 0, NULL);
    return h;
}

static bool smartIoctl(HANDLE h, BYTE feature, BYTE out[512]) {
    SENDCMDINPARAMS_ in; ZeroMemory(&in, sizeof(in));
    in.cBufferSize = 512; in.bDriveNumber = 0;
    in.ir.f = feature; in.ir.sc = 1; in.ir.sn = 1;
    in.ir.cl = 0x4F; in.ir.ch = 0xC2; in.ir.dh = 0xA0; in.ir.cmd = 0xB0;
    SENDCMDOUTPARAMS_ o; ZeroMemory(&o, sizeof(o));
    DWORD ret = 0;
    if (!DeviceIoControl(h, IOCTL_SMART_RCV_DRIVE_DATA, &in, sizeof(in), &o, sizeof(o), &ret, NULL))
        return false;
    memcpy(out, o.bBuffer, 512);
    return true;
}

static bool ataPassThrough(HANDLE h, BYTE feature, BYTE out[512]) {
    const int BUFSZ = sizeof(ATA_PT_EX) + 512;
    BYTE buf[sizeof(ATA_PT_EX) + 512]; ZeroMemory(buf, BUFSZ);
    ATA_PT_EX* p = (ATA_PT_EX*)buf;
    p->Length = sizeof(ATA_PT_EX);
    p->AtaFlags = 0x02 | 0x01;               // DATA_IN | DRDY_REQUIRED
    p->DataTransferLength = 512;
    p->TimeOutValue = 10;
    p->DataBufferOffset = sizeof(ATA_PT_EX);
    p->Cur[0] = feature; p->Cur[1] = 1; p->Cur[2] = 1;
    p->Cur[3] = 0x4F; p->Cur[4] = 0xC2; p->Cur[5] = 0xA0; p->Cur[6] = 0xB0;
    DWORD ret = 0;
    if (!DeviceIoControl(h, IOCTL_ATA_PASS_THROUGH, buf, BUFSZ, buf, BUFSZ, &ret, NULL))
        return false;
    memcpy(out, buf + sizeof(ATA_PT_EX), 512);
    return true;
}

static bool nvmeHealth(HANDLE h, BYTE out[512]) {
    const int BUFSZ = sizeof(SPQ) + 512;
    BYTE buf[sizeof(SPQ) + 512]; ZeroMemory(buf, BUFSZ);
    SPQ* q = (SPQ*)buf;
    q->PropertyId = 50;          // StorageDeviceProtocolSpecificProperty
    q->QueryType = 0;            // PropertyStandardQuery
    q->ps.ProtocolType = 3;      // NVMe
    q->ps.DataType = 2;          // LogPage
    q->ps.ReqValue = 0x02;       // SMART / Health Information
    q->ps.DataOffset = sizeof(SPSD);
    q->ps.DataLength = 512;
    DWORD ret = 0;
    if (!DeviceIoControl(h, IOCTL_STORAGE_QUERY_PROPERTY_X, buf, BUFSZ, buf, BUFSZ, &ret, NULL))
        return false;
    SPDD* d = (SPDD*)buf;
    ULONG off = (ULONG)((BYTE*)&d->ps - buf) + d->ps.DataOffset;
    if (off + 512 > (ULONG)BUFSZ) return false;
    memcpy(out, buf + off, 512);
    return true;
}

int main() {
    printf("[");
    bool first = true;
    for (int n = 0; n < 16; n++) {
        HANDLE h = openDrive(n);
        if (h == INVALID_HANDLE_VALUE) continue;
        BYTE data[512], thr[512], nv[512];
        bool isNvme = false, isAta = false;
        if (nvmeHealth(h, nv)) {
            isNvme = true;
        } else if (smartIoctl(h, 0xD0, data)) {
            isAta = true;
            if (!smartIoctl(h, 0xD1, thr)) ZeroMemory(thr, 512);
        } else if (ataPassThrough(h, 0xD0, data)) {
            isAta = true;
            if (!ataPassThrough(h, 0xD1, thr)) ZeroMemory(thr, 512);
        }
        CloseHandle(h);
        if (!isNvme && !isAta) continue;
        if (!first) printf(",");
        first = false;

        if (isNvme) {
            int crit = nv[0];
            int tempK = nv[1] | (nv[2] << 8);
            int tc = tempK ? tempK - 273 : -1;
            printf("{\"disk\":%d,\"type\":\"nvme\",\"nvme\":{"
                   "\"criticalWarning\":%d,\"temperature\":%d,\"availableSpare\":%d,"
                   "\"availableSpareThreshold\":%d,\"percentageUsed\":%d,"
                   "\"powerOnHours\":%llu,\"mediaErrors\":%llu,\"unsafeShutdowns\":%llu,"
                   "\"powerCycles\":%llu,\"dataUnitsRead\":%llu,\"dataUnitsWritten\":%llu}}",
                   n, crit, tc, nv[3], nv[4], nv[5],
                   (unsigned long long)le(nv + 128, 8), (unsigned long long)le(nv + 160, 8),
                   (unsigned long long)le(nv + 144, 8), (unsigned long long)le(nv + 112, 8),
                   (unsigned long long)le(nv + 32, 8), (unsigned long long)le(nv + 48, 8));
        } else {
            int tmap[256]; bool thas[256];
            for (int i = 0; i < 256; i++) { tmap[i] = 0; thas[i] = false; }
            for (int i = 2; i + 11 < 512; i += 12) {
                int id = thr[i];
                if (id) { tmap[id] = thr[i + 1]; thas[id] = true; }
            }
            printf("{\"disk\":%d,\"type\":\"ata\",\"attributes\":[", n);
            bool af = true;
            for (int i = 2; i + 11 < 512; i += 12) {
                int id = data[i];
                if (id == 0) continue;
                int value = data[i + 3], worst = data[i + 4];
                uint64_t raw = le(data + i + 5, 6);
                int t = thas[id] ? tmap[id] : -1;
                if (!af) printf(",");
                af = false;
                printf("{\"id\":%d,\"value\":%d,\"worst\":%d,\"threshold\":%d,\"raw\":%llu}",
                       id, value, worst, t, (unsigned long long)raw);
            }
            printf("]}");
        }
    }
    printf("]");
    return 0;
}
