"""Sweep a ROM for Brother descriptor records (KH-930 7-byte and KH-970
12-byte layouts) to locate pattern tables and understand each ROM's format.

This is an analysis helper for the 'rom scanner' project. It reports candidate
descriptor-table regions: consecutive records whose BCD fields are in range and
whose data offset points at an in-file bitmap of exactly the right size.
"""
import sys
from pathlib import Path


def bcd_ok(b):
    return (b >> 4) <= 9 and (b & 0x0F) <= 9


def bcd_val(b):
    return ((b >> 4) & 0x0F) * 10 + (b & 0x0F)


def analyze(data):
    n = len(data)
    print(f'size={n:#x}')

    # ---- KH-930 style: 7-byte records ----
    # [0]BCD-index [1]type [2]BCD-width [3]height-units(<<4) [4]BCD-height-tens [5..6]offset(LE)
    hits930 = []
    for pos in range(0, n - 7):
        idx, typ, wid = data[pos], data[pos+1], data[pos+2]
        h_un, h_ten = data[pos+3], data[pos+4]
        off = data[pos+5] | (data[pos+6] << 8)
        if not (bcd_ok(idx) and bcd_ok(wid)):
            continue
        if not (0 <= typ <= 5):
            continue
        if not (bcd_ok(h_ten)):
            continue
        w = bcd_val(wid)
        h = bcd_val(h_ten) * 10 + (h_un >> 4)
        if not (1 <= w <= 200 and 1 <= h <= 400):
            continue
        stride = (w + 7) // 8
        # row-code nibbles (optional) + bitmap must fit
        need = ((h + 1) // 2) + stride * h
        if off + need <= n:
            hits930.append((pos, idx, typ, w, h, off))

    # ---- KH-970 style: 12-byte records ----
    # [0]type [1]0 [2..3]BCD-catalog [4..5]BCD-width [6..7]BCD-height [8]0 [9]bank [10..11]offset
    hits970 = []
    for pos in range(0, n - 12):
        typ = data[pos]
        if typ not in (0x02, 0x03) or data[pos+1] != 0 or data[pos+8] != 0:
            continue
        if not (bcd_ok(data[pos+2]) and bcd_ok(data[pos+3])):
            continue
        if not (bcd_ok(data[pos+4]) and bcd_ok(data[pos+5])):
            continue
        if not (bcd_ok(data[pos+6]) and bcd_ok(data[pos+7])):
            continue
        bank = data[pos+9]
        off = data[pos+10] | (data[pos+11] << 8)
        w = bcd_val(data[pos+4]) * 100 + bcd_val(data[pos+5])
        h = bcd_val(data[pos+6]) * 100 + bcd_val(data[pos+7])
        if not (1 <= w <= 200 and 1 <= h <= 400):
            continue
        if bank not in (5, 6, 7):
            continue
        abs_off = bank * 0x10000 + off
        stride = (w + 7) // 8
        need = ((h + 1) // 2) + stride * h
        if abs_off + need <= n:
            hits970.append((pos, typ, w, h, bank, off, abs_off))

    # ---- group consecutive hits ----
    def group(hits, recsize):
        out = []
        for h in hits:
            if out and h[0] == out[-1][-1][0] + recsize:
                out[-1].append(h)
            else:
                out.append([h])
        return out

    print(f'KH-930-style 7-byte candidate records: {len(hits930)}')
    for run in group(hits930, 7):
        if len(run) >= 3:
            pos = run[0][0]
            print(f'  table @ {pos:#06x}: {len(run)} records, first: '
                  f'idx={run[0][1]} type={run[0][2]} W={run[0][3]} H={run[0][4]} '
                  f'off={run[0][5]:#06x}')

    print(f'KH-970-style 12-byte candidate records: {len(hits970)}')
    for run in group(hits970, 12):
        if len(run) >= 3:
            pos = run[0][0]
            print(f'  table @ {pos:#06x}: {len(run)} records, first: '
                  f'type={run[0][1]:#04x} W={run[0][2]} H={run[0][3]} '
                  f'bank={run[0][4]} off={run[0][5]:#06x} abs={run[0][6]:#07x}')


if __name__ == '__main__':
    p = Path(sys.argv[1])
    print(f'=== {p.name} ===')
    analyze(p.read_bytes())
    print()
