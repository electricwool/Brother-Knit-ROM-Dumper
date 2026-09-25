"""Verify the KH-930 and KH-970 descriptor-table parse against the
decoded pattern atlases (ground truth). This answers: is the record layout
right, and does the scan recover exactly the patterns the atlas lists?

Run:  python verify_scan.py
"""
import re
from pathlib import Path

ROMS = Path(r'c:\esp32\brother rom dumper\roms')
SCANNER = Path(r'c:\esp32\brother rom dumper\rom scanner')


def bcd(b):
    return ((b >> 4) & 0xF) * 10 + (b & 0xF)


def parse_kh930(data):
    recs = []
    pos = 0
    n = len(data)
    while pos + 7 <= n:
        idx, typ, wid = data[pos], data[pos + 1], data[pos + 2]
        h_un, h_ten = data[pos + 3], data[pos + 4]
        off = data[pos + 5] | (data[pos + 6] << 8)
        if not ((idx >> 4) <= 9 and (idx & 0xF) <= 9):
            break
        if not (0 <= typ <= 9):
            break
        if not ((wid >> 4) <= 9 and (wid & 0xF) <= 9):
            break
        if not ((h_ten >> 4) <= 9 and (h_ten & 0xF) <= 9):
            break
        w = bcd(wid)
        h = bcd(h_ten) * 10 + (h_un >> 4)
        cat = typ * 100 + bcd(idx)
        recs.append((cat, typ, w, h, off))
        pos += 7
    return recs


def parse_kh970(data):
    """Scan the whole descriptor window (0x50000..0x51FFC) byte-granular and
    keep every valid 12-byte record. The table is not a single contiguous
    sorted array: bank-7 (and some bank-6 '3c') records are stored at the end
    of the window out of catalogue order, and the 'mc fairisle 3c' records have
    widths/heights above 400 (e.g. 140x570, 60x864)."""
    recs = {}
    n = len(data)
    for pos in range(0x50000, min(n - 12, 0x52000)):
        typ = data[pos]
        if typ not in (0x02, 0x03):
            continue
        if data[pos + 1] != 0 or data[pos + 8] != 0:
            continue
        c1, c2 = data[pos + 2], data[pos + 3]
        w1, w2 = data[pos + 4], data[pos + 5]
        h1, h2 = data[pos + 6], data[pos + 7]
        bank = data[pos + 9]
        off = data[pos + 10] | (data[pos + 11] << 8)
        if not all((x >> 4) <= 9 and (x & 0xF) <= 9 for x in (c1, c2, w1, w2, h1, h2)):
            continue
        cat = bcd(c1) + 100 * bcd(c2)
        w = bcd(w1) + 100 * bcd(w2)
        h = bcd(h1) + 100 * bcd(h2)
        if not (1 <= w <= 999 and 1 <= h <= 999 and 1 <= cat <= 999):
            continue
        if bank not in (5, 6, 7):
            continue
        if bank * 0x10000 + off + ((h + 1) // 2) + ((w + 7) // 8) * h > n:
            continue
        recs[cat] = (cat, typ, w, h, bank, off)
    return [recs[c] for c in sorted(recs)], 0


def parse_atlas_kh930(text):
    out = {}
    for line in text.splitlines():
        m = re.match(r'\s*#(\d+)\s+(\d+)x(\d+)\s+offset\s+(0x[0-9a-fA-F]+)', line)
        if m:
            out[int(m.group(1))] = (int(m.group(2)), int(m.group(3)), int(m.group(4), 16))
    return out


def parse_atlas_kh970(text):
    out = {}
    for line in text.splitlines():
        m = re.match(
            r'\s*#(\d+)\s+(\d+)x(\d+)\s+bank\s+(\d+)\s+type\s+(0x[0-9a-fA-F]+)\s+'
            r'offset\s+(0x[0-9a-fA-F]+)', line)
        if m:
            out[int(m.group(1))] = (
                int(m.group(2)), int(m.group(3)), int(m.group(4)),
                int(m.group(5), 16), int(m.group(6), 16))
    return out


def main():
    # KH-930
    d = (ROMS / 'kh930-LH531212-4bit.bin').read_bytes()
    recs = parse_kh930(d)
    atlas = parse_atlas_kh930((ROMS / 'kh930-LH531212-4bit-patterns_atlas.txt').read_text(encoding='cp1252'))
    print(f'KH-930: parsed {len(recs)} records, atlas lists {len(atlas)} patterns')
    mism = []
    for cat, typ, w, h, off in recs:
        if cat in atlas:
            aw, ah, aoff = atlas[cat]
            if (w, h, off) != (aw, ah, aoff):
                mism.append((cat, (w, h, off), (aw, ah, aoff)))
        else:
            mism.append((cat, (w, h, off), 'NOT-IN-ATLAS'))
    print(f'  records with offset/dims mismatch vs atlas: {len(mism)}')
    for m in mism[:20]:
        print('   ', m)
    # missing atlas patterns
    missing = [c for c in sorted(atlas) if c not in {r[0] for r in recs}]
    print(f'  atlas patterns NOT recovered by scan: {len(missing)} -> {missing[:20]}')

    # KH-970
    d = (ROMS / 'kh970CB1v1.0-AM27C040@DIP32.bin').read_bytes()
    recs, endpos = parse_kh970(d)
    atlas = parse_atlas_kh970((ROMS / 'kh970CB1v1.0-AM27C040@DIP32-patterns_atlas.txt').read_text(encoding='cp1252'))
    print(f'\nKH-970: parsed {len(recs)} records (table end {endpos:#x}), atlas lists {len(atlas)} patterns')
    mism = []
    for cat, typ, w, h, bank, off in recs:
        if cat in atlas:
            aw, ah, abank, atyp, aoff = atlas[cat]
            if (w, h, bank, typ, off) != (aw, ah, abank, atyp, aoff):
                mism.append((cat, (w, h, bank, typ, off), (aw, ah, abank, atyp, aoff)))
        else:
            mism.append((cat, (w, h, bank, typ, off), 'NOT-IN-ATLAS'))
    print(f'  records mismatched vs atlas: {len(mism)}')
    for m in mism[:20]:
        print('   ', m)
    missing = [c for c in sorted(atlas) if c not in {r[0] for r in recs}]
    print(f'  atlas patterns NOT recovered: {len(missing)} -> {missing[:40]}')


if __name__ == '__main__':
    main()
