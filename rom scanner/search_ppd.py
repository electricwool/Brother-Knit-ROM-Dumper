"""Search cartridge ROMs for BCD stitch-pattern descriptors and pointer tables.

Looks for three structures:
  (A) KH-930-style 7-byte records  [BCD-index][type][BCD-W][h-units][h-tens][off LE]
  (B) font-table-style records     [ptr BE][code][h][w][?][?]  (found at PPD310 0x7D00)
  (C) BCD (W,H) pairs followed by a plausible in-file bitmap
"""
import sys
from pathlib import Path


def bcd_ok(b):
    return (b >> 4) <= 9 and (b & 0x0F) <= 9


def bcd_val(b):
    return ((b >> 4) & 0x0F) * 10 + (b & 0x0F)


def analyze(data, name):
    n = len(data)
    print(f'=== {name} ({n} bytes) ===')

    # (A) KH-930-style 7-byte
    a = []
    for pos in range(n - 7):
        idx, typ, wid = data[pos], data[pos + 1], data[pos + 2]
        h_un, h_ten = data[pos + 3], data[pos + 4]
        off = data[pos + 5] | (data[pos + 6] << 8)
        if not (bcd_ok(idx) and bcd_ok(wid) and 0 <= typ <= 9 and bcd_ok(h_ten)):
            continue
        w = bcd_val(wid)
        h = bcd_val(h_ten) * 10 + (h_un >> 4)
        if 1 <= w <= 200 and 1 <= h <= 400 and off + ((w + 7) // 8) * h <= n:
            a.append((pos, bcd_val(idx), typ, w, h, off))
    # group 7-byte-aligned runs
    runs = []
    for h in a:
        if runs and h[0] == runs[-1][-1][0] + 7:
            runs[-1].append(h)
        else:
            runs.append([h])
    print(f'(A) KH-930-style runs>=4: {sum(1 for r in runs if len(r)>=4)}')
    for r in runs:
        if len(r) >= 4:
            print(f'    @ {r[0][0]:#06x}: {len(r)} recs, first idx={r[0][1]} type={r[0][2]} W={r[0][3]} H={r[0][4]} off={r[0][5]:#06x}')

    # (B) font-table-style records: [ptr BE][code][h][w][?][?] where ptr points in-file
    b_hits = []
    for pos in range(n - 7):
        ptr = (data[pos] << 8) | data[pos + 1]
        code, hh, ww = data[pos + 2], data[pos + 3], data[pos + 4]
        if ptr < n and 0x20 <= code <= 0x7E and 1 <= hh <= 32 and 1 <= ww <= 64:
            b_hits.append((pos, ptr, code, hh, ww))
    runs = []
    for h in b_hits:
        if runs and h[0] == runs[-1][-1][0] + 7:
            runs[-1].append(h)
        else:
            runs.append([h])
    print(f'(B) font-table-style runs>=4: {sum(1 for r in runs if len(r)>=4)}')
    for r in runs:
        if len(r) >= 4:
            print(f'    @ {r[0][0]:#06x}: {len(r)} recs, first ptr={r[0][1]:#06x} code={chr(r[0][2])!r} h={r[0][3]} w={r[0][4]}')

    # (C) BCD (W,H) pairs followed by bitmap
    c_hits = []
    for pos in range(n - 2):
        w, h = data[pos], data[pos + 1]
        if not (bcd_ok(w) and bcd_ok(h)):
            continue
        wv, hv = bcd_val(w), bcd_val(h)
        if not (1 <= wv <= 99 and 1 <= hv <= 99):
            continue
        need = ((wv + 7) // 8) * hv
        # bitmap must follow within 4 bytes and fit in file
        if pos + 2 + need <= n:
            c_hits.append((pos, wv, hv))
    # density: report any region with many such hits
    print(f'(C) BCD (W,H)+bitmap candidates: {len(c_hits)}')
    # cluster
    clusters = []
    for h in c_hits:
        if clusters and h[0] - clusters[-1][-1][0] <= 8:
            clusters[-1].append(h)
        else:
            clusters.append([h])
    for cl in clusters:
        if len(cl) >= 6:
            print(f'    cluster @ {cl[0][0]:#06x}: {len(cl)} (W,H) pairs, first W={cl[0][1]} H={cl[0][2]}')


if __name__ == '__main__':
    for fn in ['UPD27C256A@DIP28_PPD310JPY.BIN',
               'UPD27C256A@DIP28_STITCH_PATTERN_CARTRIDGE.II.ENG.PAL.BIN',
               'AM27C512@DIP28.STITCH_PATTERN_CARTRIDGE.III.ENG.PAL.BIN']:
        p = Path(r'c:\esp32\brother rom dumper\roms') / fn
        analyze(p.read_bytes(), fn)
        print()
