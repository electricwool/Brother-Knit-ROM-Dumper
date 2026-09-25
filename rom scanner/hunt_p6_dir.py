"""Search the cartridge ROM dumps for the P6 built-in pattern directory.

P6 record decode ($9D16), 7 bytes, all little-endian except rows nibble:
  [0..1] geometry / width   (LE)
  [2..3] pattern number     (LE, BCD)
  [4]    rows  (>>4)
  [5..6] data pointer       (LE, P6 address)

Run over every byte offset and report runs of consecutive (stride 7) records
with sequential-ish BCD pattern numbers and data pointers that land in-file.
"""
from pathlib import Path


def bcd_ok(b):
    return (b >> 4) <= 9 and (b & 0xF) <= 9


def bcd16(lo, hi):
    return ((lo >> 4) & 0xF) * 10 + (lo & 0xF) + 100 * (((hi >> 4) & 0xF) * 10 + (hi & 0xF))


def analyze(data, base, name):
    n = len(data)
    print(f'=== {name} ({n} B, CPU base {base:#06x}) ===')
    hits = []
    for pos in range(n - 7):
        geo_lo, geo_hi = data[pos], data[pos + 1]
        no_lo, no_hi = data[pos + 2], data[pos + 3]
        rows = data[pos + 4] >> 4
        ptr_lo, ptr_hi = data[pos + 5], data[pos + 6]
        if not (bcd_ok(no_lo) and bcd_ok(no_hi)):
            continue
        pno = bcd16(no_lo, no_hi)
        if not (1 <= pno <= 900):
            continue
        if not (1 <= rows <= 200):
            continue
        ptr = ptr_lo | (ptr_hi << 8)
        # data pointer must be a P6 address; try mapping to ROM offset via base
        rom = ptr - base
        if not (0 <= rom < n):
            continue
        w = geo_lo | (geo_hi << 8)
        if not (1 <= w <= 256):
            continue
        hits.append((pos, pno, w, rows, ptr, rom))

    runs = []
    for h in hits:
        if runs and h[0] == runs[-1][-1][0] + 7 and h[1] > runs[-1][-1][1]:
            runs[-1].append(h)
        else:
            runs.append([h])

    print(f'candidate records: {len(hits)}, runs len>=4:')
    for r in runs:
        if len(r) >= 4:
            print(f'  dir @ {r[0][0]:#06x} (CPU {base + r[0][0]:#06x}): '
                  f'{len(r)} recs, pno {r[0][1]}..{r[-1][1]}, '
                  f'W {r[0][2]}, rows {r[0][3]}, ptr {r[0][4]:#06x}')


if __name__ == '__main__':
    for fn, base in [
        ('UPD27C256A@DIP28_STITCH_PATTERN_CARTRIDGE.II.ENG.PAL.BIN', 0x8000),
        ('UPD27C256A@DIP28_PPD310JPY.BIN', 0x8000),
        ('AM27C512@DIP28.STITCH_PATTERN_CARTRIDGE.III.ENG.PAL.BIN', 0x0000),
    ]:
        d = (Path(r'c:\esp32\brother rom dumper\roms') / fn).read_bytes()
        analyze(d, base, fn)
        print()
