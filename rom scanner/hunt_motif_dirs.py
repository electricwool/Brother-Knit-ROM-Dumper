"""Hunt for in-ROM motif directories in the PPD/cartridge firmware.

The verified alphabet directory (cart II `$FB1D`) uses 7-byte records:
  [0..1] pattern No (BCD, LE)
  [2]    width (px)
  [3..4] height field (LE)
  [5..6] bitmap ptr (BE, CPU address)

This sweeps the ROM for *runs* of that record shape whose pointers land inside
the ROM (as a CPU address) and whose keys are sequential-ish, i.e. other motif
libraries (the main built-in set).
"""
import sys
from pathlib import Path


def analyze(data, base, name):
    n = len(data)
    print(f'=== {name} (ROM {n} B, CPU base {base:#06x}) ===')

    hits = []
    for pos in range(n - 7):
        key = (data[pos + 1] << 8) | data[pos]          # BCD LE
        w = data[pos + 2]
        h16 = (data[pos + 4] << 8) | data[pos + 3]      # LE
        ptr = (data[pos + 5] << 8) | data[pos + 6]      # BE
        # key plausible BCD
        if not (((key >> 12) <= 9 and ((key >> 8) & 0xF) <= 9 and
                 ((key >> 4) & 0xF) <= 9 and (key & 0xF) <= 9)):
            continue
        if not (1 <= w <= 64):
            continue
        # pointer resolves into the ROM as a CPU address
        rom_ptr = ptr - base
        if not (0 <= rom_ptr < n):
            continue
        # height field: low byte BCD or small
        if not (1 <= h16 <= 0x0FFF):
            continue
        hits.append((pos, key, w, h16, ptr, rom_ptr))

    # group consecutive (stride 7) hits with increasing keys
    runs = []
    for h in hits:
        if runs and h[0] == runs[-1][-1][0] + 7 and h[1] > runs[-1][-1][1]:
            runs[-1].append(h)
        else:
            runs.append([h])

    print(f'candidate records: {len(hits)}, runs (len>=4):')
    for r in runs:
        if len(r) >= 4:
            k0 = r[0][1]
            k1 = r[-1][1]
            print(f'  dir @ {r[0][0]:#06x} (CPU {base + r[0][0]:#06x}): '
                  f'{len(r)} recs, keys {k0:04X}..{k1:04X}, '
                  f'W {r[0][2]}, ptr {r[0][4]:#06x}')


if __name__ == '__main__':
    for fn, base in [
        ('UPD27C256A@DIP28_STITCH_PATTERN_CARTRIDGE.II.ENG.PAL.BIN', 0x8000),
        ('UPD27C256A@DIP28_PPD310JPY.BIN', 0x8000),
        ('AM27C512@DIP28.STITCH_PATTERN_CARTRIDGE.III.ENG.PAL.BIN', 0x0000),
    ]:
        d = (Path(r'c:\esp32\brother rom dumper\roms') / fn).read_bytes()
        analyze(d, base, fn)
        print()
