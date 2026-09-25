"""Brother KH-930 / KH-970 built-in stitch-pattern ROM parser.

Decodes the two verified descriptor-table formats into a list of
:class:`Pattern` objects (dimensions, row codes, and 1bpp bitmap).

See `ROM_INVENTORY.md` for the format documentation.
"""
from dataclasses import dataclass, field


def bcd_ok(b: int) -> bool:
    return (b >> 4) <= 9 and (b & 0xF) <= 9


def bcd(b: int) -> int:
    """Interpret one byte as packed BCD (tens in high nibble, units in low)."""
    return ((b >> 4) & 0xF) * 10 + (b & 0xF)


def bcd16(lo: int, hi: int) -> int:
    """Interpret a little-endian 2-byte field as BCD (lo = tens+units, hi = hundreds)."""
    return bcd(lo) + 100 * bcd(hi)


@dataclass
class Pattern:
    index: int            # catalogue / pattern number
    typ: int              # type field (KH-930 category, or KH-970 0x02/0x03)
    width: int            # display stitches
    height: int           # display rows (H/3 for type 0x03 3-plane patterns)
    offset: int           # ROM offset of the pattern data
    row_codes: list       # one nibble per raw row (0 = plain knit)
    bitmap: list          # raw W*H list of bits (0/1), row-major, bit 0 = leftmost
    colours: list         # W*height list of colour IDs (0 = background, 1..N)
    num_colours: int      # number of distinct colour IDs (incl. background 0)
    planes: int = 1       # 1 = normal, 3 = three stacked 1bpp planes
    stitch_values: list = None   # W*height list of stitch-type values
    is_lace: bool = False        # True for lace / fine-lace patterns


def _extract_bitmap(data, offset, width, height, has_row_codes):
    stride = (width + 7) // 8
    pos = offset
    row_codes = []
    if has_row_codes:
        rc_len = (height + 1) // 2
        for i in range(rc_len):
            b = data[pos + i]
            row_codes.append(b & 0x0F)
            if i * 2 + 1 < height:
                row_codes.append(b >> 4)
        row_codes = row_codes[:height]
        pos += rc_len
    bitmap = []
    for r in range(height):
        for c in range(width):
            byte = data[pos + r * stride + c // 8]
            bit = (byte >> (c % 8)) & 1  # bit 0 = leftmost
            bitmap.append(bit)
    return row_codes, bitmap


def _colour_policy(machine, typ, cat, row_codes):
    """Return a colour policy for a pattern:
      - a `{row_code: colour_id}` dict (explicit mapping),
      - `'distinct'` (each distinct row code -> its own colour),
      - `'planes'` (KH-970 type 0x03, 3 stacked planes), or
      - `None` (plain 2-colour bitmap: bit=1 -> colour 1, bit=0 -> bg)."""
    if machine == 'KH-970':
        if typ == 0x03:
            return 'planes'
        if cat >= 499:                              # bank-7 extras: by signature
            if set(row_codes) & {1, 3, 4}:          # multicolor / tuck variants
                return 'distinct'
            return None
        if 67 <= cat <= 92:                         # multicolor (2-colour)
            return {0: 1, 2: 2, 3: 2, 4: 2}
        if 260 <= cat <= 275:                       # mc tuck
            return 'distinct'
        if 320 <= cat <= 342:                       # mc skip
            return 'distinct'
        if 385 <= cat <= 420:                       # weaving
            return 'distinct'
        if 484 <= cat <= 498:                       # mc fairisle 3c
            return 'distinct'
        return None
    # KH-930: colour is carried in the row-code nibble only for the
    # multicolor categories (colour-change rows). Every other category is a
    # plain 2-colour bitmap (bit=1 -> colour 1, bit=0 -> background), and the
    # row codes are stitch operations, not colours. Category ranges follow
    # the corrected atlas (roms/kh930-LH531212-4bit-patterns_atlas.txt).
    if (43 <= cat <= 84 or        # multicolor (colour change rows)
            293 <= cat <= 312 or  # multicolor tuck stitch
            368 <= cat <= 394 or  # multicolor skip stitch
            422 <= cat <= 466 or  # weaving
            512 <= cat <= 531):   # multicolor
        return 'distinct'
    return None


def _colours_2col(bitmap):
    return [1 if b else 0 for b in bitmap]


def _colours_distinct(width, height, bitmap, row_codes):
    codes = sorted(set(row_codes)) or [0]   # no row codes -> plain knit rows
    mapping = {code: i + 1 for i, code in enumerate(codes)}
    out = []
    for r in range(height):
        rc = row_codes[r] if r < len(row_codes) else 0
        cid = mapping.get(rc, 0)
        base = r * width
        for c in range(width):
            out.append(cid if bitmap[base + c] else 0)
    return out


def _colours_rowcode(width, height, bitmap, row_codes, policy):
    out = []
    for r in range(height):
        rc = row_codes[r] if r < len(row_codes) else 0
        cid = policy.get(rc, 0)
        base = r * width
        for c in range(width):
            out.append(cid if bitmap[base + c] else 0)
    return out


def _build_colours(width, height, bitmap, row_codes, policy):
    if policy == 'distinct':
        return _colours_distinct(width, height, bitmap, row_codes)
    if policy:
        return _colours_rowcode(width, height, bitmap, row_codes, policy)
    return _colours_2col(bitmap)


def _colours_planes(width, height, bitmap):
    """Type 0x03: three stacked 1bpp planes, display height = height // 3."""
    dh = height // 3
    out = []
    for r in range(dh):
        p1 = r * width
        p2 = (dh + r) * width
        p3 = (2 * dh + r) * width
        for c in range(width):
            if bitmap[p1 + c]:
                out.append(1)
            elif bitmap[p2 + c]:
                out.append(2)
            elif bitmap[p3 + c]:
                out.append(3)
            else:
                out.append(0)
    return out


# Stitch-type values (DesignaKnit dialects).
KNIT_MAIN = 0x21          # plain knit, "main" dialect (non-lace samples)
KNIT_LACE = 32            # knit / blank / return pass, "lace" dialect (930-940 lace)
LACE_TRANSFER = 134       # 0x86 lace transfer (marked stitch in a lace row)
FINE_LACE_TRANSFER = 132  # 0x84 fine-lace transfer (marked stitch in a fine-lace row)


def _is_lace(machine, typ, cat):
    """True for lace / fine-lace categories (row codes are lace operations)."""
    if machine == 'KH-930':
        return 103 <= cat <= 222             # lace (103-182) + fine lace (183-222)
    return 108 <= cat <= 205                 # KH-970 lace (108-177) + fine lace (178-205)


def _build_stitch_values(width, height, bitmap, row_codes, is_lace):
    """W*height list of stitch-type values (lace dialect for lace, else knit)."""
    if not is_lace:
        return [KNIT_MAIN] * (width * height)
    out = []
    for r in range(height):
        rc = row_codes[r] if r < len(row_codes) else 0
        if rc in (10, 11):
            mark = FINE_LACE_TRANSFER
        elif rc in (0, 1):
            mark = LACE_TRANSFER
        else:
            mark = KNIT_LACE          # knit carriage / knit variants (2, 4, 6, 8)
        base = r * width
        for c in range(width):
            out.append(mark if bitmap[base + c] else KNIT_LACE)
    return out


def parse_kh930(data: bytes):
    """KH-930: 7-byte BCD descriptor table at 0x0000, 615 records."""
    n = len(data)
    recs = []
    pos = 0
    while pos + 7 <= n:
        idx, typ, wid = data[pos], data[pos + 1], data[pos + 2]
        h_un, h_ten = data[pos + 3], data[pos + 4]
        off = data[pos + 5] | (data[pos + 6] << 8)
        if not (bcd_ok(idx) and bcd_ok(wid) and bcd_ok(h_ten)):
            break
        if not (0 <= typ <= 9):
            break
        w = bcd(wid)
        h = bcd(h_ten) * 10 + (h_un >> 4)
        if not (1 <= w <= 200 and 1 <= h <= 400):
            break
        recs.append((typ * 100 + bcd(idx), typ, w, h, off))
        pos += 7
    if len(recs) < 50:
        return []
    patterns = []
    for i, (index, typ, w, h, off) in enumerate(recs):
        # KH-930 row codes are optional; the data size (= gap to the next
        # record's offset) tells us which layout is in force. Exact match:
        #   bitmap only, normal width:  ceil(w/8)*h
        #   row codes + bitmap:        (h+1)//2 + ceil(w/8)*h
        #   bitmap only, BYTE width:   w*h      (wide logo/text; w = bytes/row)
        #   row codes + BYTE width:    (h+1)//2 + w*h
        next_off = recs[i + 1][4] if i + 1 < len(recs) else 0xF702
        size = next_off - off
        stride = (w + 7) // 8
        rc_len = (h + 1) // 2
        if size == stride * h:
            has_rc, width = False, w
        elif size == rc_len + stride * h:
            has_rc, width = True, w
        elif size == w * h:
            has_rc, width = False, w * 8
        elif size == rc_len + w * h:
            has_rc, width = True, w * 8
        else:
            # fallback: assume no row codes, normal width
            has_rc, width = False, w
        rc, bm = _extract_bitmap(data, off, width, h, has_rc)
        is_lace = _is_lace('KH-930', typ, index)
        if is_lace:
            # lace is a single-colour texture: one yarn, two carriages
            colours = [1] * (width * h)
        else:
            policy = _colour_policy('KH-930', typ, index, rc)
            colours = _build_colours(width, h, bm, rc, policy)
        num_colours = len(set(colours))
        stitch_values = _build_stitch_values(width, h, bm, rc, is_lace)
        patterns.append(Pattern(index, typ, width, h, off, rc, bm,
                                colours, num_colours, 1, stitch_values, is_lace))
    return patterns


def parse_kh970(data: bytes):
    """KH-970: 12-byte BCD descriptors in window 0x50000..0x51FFC, byte-granular scan."""
    n = len(data)
    if n < 0x52000:
        return []
    found = {}
    for pos in range(0x50000, 0x51FFD):
        typ = data[pos]
        if typ not in (0x02, 0x03):
            continue
        if data[pos + 1] != 0 or data[pos + 8] != 0:
            continue
        c1, c2 = data[pos + 2], data[pos + 3]
        w1, w2 = data[pos + 4], data[pos + 5]
        h1, h2 = data[pos + 6], data[pos + 7]
        if not all(bcd_ok(x) for x in (c1, c2, w1, w2, h1, h2)):
            continue
        bank = data[pos + 9]
        off = data[pos + 10] | (data[pos + 11] << 8)
        index = bcd16(c1, c2)
        w = bcd16(w1, w2)
        h = bcd16(h1, h2)
        if not (1 <= w <= 999 and 1 <= h <= 999 and 1 <= index <= 999):
            continue
        if bank not in (5, 6, 7):
            continue
        abs_off = bank * 0x10000 + off
        if abs_off + ((h + 1) // 2) + ((w + 7) // 8) * h > n:
            continue
        found[index] = (index, typ, w, h, bank, abs_off)
    if len(found) < 100:
        return []
    patterns = []
    for index in sorted(found):
        index, typ, w, h, bank, abs_off = found[index]
        # KH-970 row-code nibbles are always present (ceil(H/2) bytes).
        rc, bm = _extract_bitmap(data, abs_off, w, h, True)
        is_lace = _is_lace('KH-970', typ, index)
        if is_lace:
            # lace is a single-colour texture: one yarn, two carriages
            dh, planes = h, 1
            colours = [1] * (w * dh)
        else:
            policy = _colour_policy('KH-970', typ, index, rc)
            if policy == 'planes':
                colours = _colours_planes(w, h, bm)
                dh, planes = h // 3, 3
            else:
                dh, planes = h, 1
                colours = _build_colours(w, h, bm, rc, policy)
        num_colours = len(set(colours))
        stitch_values = _build_stitch_values(w, dh, bm, rc, is_lace)
        patterns.append(Pattern(index, typ, w, dh, abs_off, rc, bm,
                                colours, num_colours, planes,
                                stitch_values, is_lace))
    return patterns


def detect_and_parse(data: bytes):
    """Return (format_name, patterns) for the first format that parses."""
    p = parse_kh970(data)
    if p:
        return 'KH-970', p
    p = parse_kh930(data)
    if p:
        return 'KH-930', p
    return None, []
