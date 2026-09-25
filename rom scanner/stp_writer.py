"""DesignaKnit .STP writer.

Produces a structurally-valid .STP from a decoded Brother pattern (colour map +
stitch map). The header key fields and XOR key derivation replicate the known
format (see `../STP format/STP_FORMAT.md`), so files round-trip through
`d7_stp_decoder.py`.
"""
import struct

from lace_remap import LACE_REMAP_BLOB

KNIT = 0x21     # stitch-type value for plain knit (main dialect)

# Remap tables: (stitch-type value, kind byte) for remap index 1, 2, 3, ...
#  - MAIN_REMAP matches the non-lace sample library (21 05 22 01).
#  - LACE_REMAP matches the 930-940 lace library
#    (20 0b 2e 01 86 03 87 03 88 03 85 03 84 03 83 03 8a 01 89 01).
MAIN_REMAP = [(0x21, 5), (0x22, 1)]
LACE_REMAP = [(32, 11), (46, 1), (134, 3), (135, 3), (136, 3),
              (133, 3), (132, 3), (131, 3), (138, 1), (137, 1)]

# colour ID -> (STP colour index, n byte, r, g, b). Colour ID 0 = background.
DEFAULT_PALETTE = {
    0: (32, 0x50, 255, 255, 255),   # background white
    1: (49, 0x10, 0, 0, 0),         # black
    2: (50, 0x10, 200, 30, 30),     # red
    3: (51, 0x10, 30, 160, 30),     # green
    4: (52, 0x10, 30, 60, 200),     # blue
    5: (53, 0x10, 220, 180, 0),     # yellow
    6: (54, 0x10, 200, 0, 180),     # magenta
    7: (55, 0x10, 0, 180, 200),     # cyan
    8: (56, 0x10, 160, 90, 40),     # brown
    9: (57, 0x10, 90, 90, 90),      # grey
    10: (58, 0x10, 240, 140, 60),   # orange
}

# Lace dialect palette: single light-blue grid colour (index 49), plus the
# grey yarn (index 50) that the 930-940 lace library defines. The stitch
# symbols (knit dot / transfer cross) are drawn on top of the light grid.
LACE_PALETTE = {
    1: (49, 0x74, 188, 248, 254),   # light-blue grid (the single colour)
    2: (50, 0x30, 138, 138, 138),   # grey yarn (defined, unused)
}

_MAX_XOR = 21000


def _u16(x):
    return struct.pack('<H', x & 0xFFFF)


def _u32(x):
    return struct.pack('<I', x & 0xFFFFFFFF)


def _xor_key(header: bytes) -> bytes:
    u8 = lambda p: header[p] & 0xFF
    u16 = lambda p: u8(p) | (u8(p + 1) << 8)
    u32 = lambda p: (u8(p) | (u8(p + 1) << 8) | (u8(p + 2) << 16) | (u8(p + 3) << 24))
    pstr = lambda p: header[p + 1:p + 1 + u8(p)].decode('latin-1', 'replace')

    first = u32(0x35) // 2 + u16(0x3F) * 4 + u32(0x39) + u16(0x3D) + u8(0x20)
    key = (pstr(0x60) + pstr(0x41) + str(u16(0x3D)) + str(u8(0x20))
           + pstr(0x41) + str(u8(0x20)) + str(u16(0x3D)))
    salt1 = u16(0x39)
    salt2 = 1 if (u32(0x35) & 0xFFF) > 0 else 0
    n = first
    for i, ch in enumerate(key):
        b = ord(ch) // 2
        m = i % 3
        if m == 0:
            n += (b // 5) * u16(0x3F)
            n += (i + 1) * salt2
            n += b * 6
        elif m == 1:
            n += (i + 1) * salt1
            n += b * 4
        else:
            n += (i + 1) * b + (salt2 + b) // 7
    v = n
    keystr = f'{v * 3}{v}{v * 4}{v * 2}{v * 5}{v * 6}{v * 8}{v * 7}'
    out = bytearray(_MAX_XOR)
    for i in range(_MAX_XOR):
        out[i] = ord(keystr[(i + 1) % len(keystr)]) ^ ((v % (i + 1)) & 0xFF)
    return bytes(out)


def _header(width, height, lace=False):
    h = bytearray(0xF8)
    h[0:3] = b'D7c'
    for pos, val in ((0x03, width), (0x07, width), (0x11, width),
                     (0x05, height), (0x09, height), (0x15, height),
                     (0x19, max(0, height - 1))):
        h[pos:pos + 2] = _u16(val)
    if lace:
        # lace-dialect settings (from the 930-940 lace sample library)
        h[0x0B:0x0D] = _u16(2)
        h[0x0D:0x0F] = _u16(2)
        h[0x0F:0x11] = _u16(1)
        h[0x13:0x15] = _u16(1)
        h[0x17:0x19] = _u16(1)
        h[0x19:0x1B] = _u16(height)   # row extent (always >= height in samples)
        h[0x1D:0x1F] = _u16(8)        # lace stitch-type selector
        h[0x2C] = 0x0F
        h[0x2D] = 0xFF
        h[0x30] = 0x01
        h[0x31] = 0x07
        h[0x39:0x3D] = _u32(123)      # key salt (lace dialect)
        h[0x3F:0x41] = _u16(0)        # key salt (lace dialect)
        # fixed lace constants (identical across all 80 lace samples)
        h[0x9D:0xA6] = bytes([0x02, 0x05, 0x04, 0x01, 0x02, 0x03, 0x01, 0x00, 0x01])
        h[0xD8] = 0x12
        h[0xDE:0xE5] = bytes([0x3C, 0x1C, 0x46, 0x00, 0x3C, 0x1C, 0x46])
    else:
        h[0x0B:0x0D] = _u16(9)
        h[0x0D:0x0F] = _u16(9)
        h[0x0F:0x11] = _u16(1)
        h[0x13:0x15] = _u16(1)
        h[0x17:0x19] = _u16(1)
        h[0x39:0x3D] = _u32(999)
        h[0x3F:0x41] = _u16(99)
    # key fields common to both dialects (name char must be printable 32..60)
    h[0x1F] = 0x31                       # '1'
    h[0x20] = 0x46                       # 'F'
    h[0x21:0x24] = b'321'
    h[0x24] = 0x02
    h[0x25] = 0x02
    h[0x26] = 0x01
    h[0x28] = 0x01
    h[0x35:0x39] = _u32(10_000_000)
    h[0x3D:0x3F] = _u16(30882)
    # Pascal strings at 0x41 and 0x60 are empty (length byte 0 already)
    h[0xB1:0xB6] = b'Arial'
    return bytes(h)


def _rle(pixels):
    """RLE-encode one row: single value byte, or 0x80|len + value for runs."""
    out = bytearray()
    i = 0
    n = len(pixels)
    while i < n:
        v = pixels[i]
        j = i
        while j < n and pixels[j] == v and (j - i) < 127:
            j += 1
        run = j - i
        if run == 1 and v < 0x80:
            out.append(v)
        else:
            out.append(0x80 | run)
            out.append(v)
        i = j
    return out


def _block(height, rle, key):
    enc = bytearray(rle)
    for i in range(len(enc)):
        enc[i] ^= key[i]
    return _u16(height) + _u16(len(enc)) + bytes(enc)


def _palette(entries):
    p = bytearray(71 * 25)
    for _cid, (index, n, r, g, b) in entries.items():
        o = index * 25
        p[o] = n
        p[o + 6] = r
        p[o + 7] = g
        p[o + 8] = b
    return bytes(p)


def build_stp(width, height, colour_ids, stitch_values=None, remap=None,
              lace=False, palette=None):
    """colour_ids: W*H list of colour IDs (0 = background, 1..N = colours).
       stitch_values: optional W*H list of stitch-type values (default knit).
       remap: list of (value, kind) pairs; remap index 1 -> remap[0], etc.
       lace: True to use the lace header + full lace remap table.
       palette: {colour_id: (index, r, g, b)}; defaults to DEFAULT_PALETTE.
       Returns the .STP file bytes."""
    palette = palette or (LACE_PALETTE if lace else DEFAULT_PALETTE)
    if lace:
        remap = LACE_REMAP
        header = _header(width, height, lace=True)
        remap_blob = LACE_REMAP_BLOB
    else:
        remap = remap or MAIN_REMAP
        header = _header(width, height, lace=False)
        remap_blob = bytes(b for v, k in remap for b in (v, k))
    key = _xor_key(header)

    # colour map: one palette index per stitch
    cmap = bytearray(width * height)
    for i, cid in enumerate(colour_ids):
        cmap[i] = palette[cid][0]

    # stitch map: raw remap index (1-based) resolved from the stitch value
    value_to_index = {v: i + 1 for i, (v, _k) in enumerate(remap)}
    smap = bytearray(width * height)
    if stitch_values is None:
        smap[:] = bytes([value_to_index.get(KNIT, 1)]) * len(smap)
    else:
        for i, v in enumerate(stitch_values):
            smap[i] = value_to_index.get(v, 1)

    color_rle = b''.join(_rle(cmap[r * width:(r + 1) * width]) for r in range(height))
    stitch_rle = b''.join(_rle(smap[r * width:(r + 1) * width]) for r in range(height))

    out = bytearray()
    out += header
    out += _block(height, color_rle, key)
    out += _block(height, stitch_rle, key)
    out += _palette(palette)
    out += remap_blob
    return bytes(out)
