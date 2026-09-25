"""16-colour (4bpp) BMP writer for pattern previews.

Writes a standard uncompressed 4-bit BMP (BITMAPFILEHEADER +
BITMAPINFOHEADER + 16-entry palette + bottom-up nibble-packed pixels) so
each decoded pattern can be eyeballed without opening DesignaKnit.

Colour IDs are palette indices 0..15. For non-lace patterns they are the
pattern's own colour map (see stp_writer.DEFAULT_PALETTE); for lace patterns
the single-colour grid would be blank, so the stitch map is rendered instead
(knit = light grid, transfer cross = navy, fine-lace transfer = dark red).
"""
import struct

# Non-lace colour ID -> (r, g, b); mirrors stp_writer.DEFAULT_PALETTE.
MAIN_BMP = {
    0: (255, 255, 255),   # background white
    1: (0, 0, 0),         # black
    2: (200, 30, 30),     # red
    3: (30, 160, 30),     # green
    4: (30, 60, 200),     # blue
    5: (220, 180, 0),     # yellow
    6: (200, 0, 180),     # magenta
    7: (0, 180, 200),     # cyan
    8: (160, 90, 40),     # brown
    9: (90, 90, 90),      # grey
    10: (240, 140, 60),   # orange
}

# Lace preview colour IDs (stitch map -> palette index).
LACE_KNIT = 1        # plain knit / blank / return pass (the light grid)
LACE_TRANSFER = 2    # lace transfer cross (0x86)
LACE_FINE = 3        # fine-lace transfer (0x84)

LACE_BMP = {
    0: (0, 0, 0),           # unused
    LACE_KNIT: (188, 248, 254),   # light-blue grid (matches the STP grid)
    LACE_TRANSFER: (20, 40, 120),  # navy transfer cross
    LACE_FINE: (170, 20, 40),      # dark-red fine-lace transfer
}


def make_palette(rgb_map, n=16):
    """Expand a {colour_id: (r,g,b)} map into an n-entry (r,g,b) list."""
    out = [(0, 0, 0)] * n
    for k, v in rgb_map.items():
        if 0 <= k < n:
            out[k] = v
    return out


def build_bmp(width, height, colour_ids, palette):
    """Build a complete 4bpp BMP.

    colour_ids: width*height list of palette indices (0..15), row-major.
    palette: list of exactly 16 (r, g, b) tuples (BGR order in the file).
    """
    assert len(palette) == 16, 'palette must have 16 entries'

    # 4bpp: 2 pixels per byte, high nibble = leftmost pixel of the pair.
    stride = (width + 1) // 2
    stride = (stride + 3) & ~3        # rows are DWORD-aligned
    pixel_data = bytearray()
    for row in range(height):               # BMP rows are bottom-up; flip vertically
        rowbytes = bytearray(stride)
        base = row * width
        for x in range(width):
            idx = colour_ids[base + x] & 0x0F
            if x % 2 == 0:
                rowbytes[x // 2] = idx << 4
            else:
                rowbytes[x // 2] |= idx
        pixel_data += rowbytes

    palette_bytes = bytearray()
    for r, g, b in palette:
        palette_bytes += bytes((b, g, r, 0))

    off_bits = 14 + 40 + len(palette_bytes)   # 118
    file_size = off_bits + len(pixel_data)

    header = struct.pack('<2sIHHI', b'BM', file_size, 0, 0, off_bits)
    info = struct.pack('<IiiHHIIiiII', 40, width, height, 1, 4,
                       0, len(pixel_data), 0, 0, 16, 0)
    return header + info + bytes(palette_bytes) + bytes(pixel_data)
