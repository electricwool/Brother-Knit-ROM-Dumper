"""Extract Brother KH-930 / KH-970 built-in stitch patterns to DesignaKnit .STP.

Usage:
    python extract_rom.py <rom.bin>

Creates two subfolders next to the ROM named after it:
  * `<name>/`     — one `<index>.STP` per pattern, plus `report.txt`
  * `<name>-bmp/` — one `<index>.bmp` per pattern (16-colour preview)
"""
import sys
from pathlib import Path

import brother
import stp_writer
import bmp_writer


def render_ascii(width, height, bitmap):
    lines = []
    for r in range(height):
        row = bitmap[r * width:(r + 1) * width]
        lines.append(''.join('#' if b else '.' for b in row))
    return '\n'.join(lines)


def bmp_preview(p):
    """Return (colour_ids, palette) for a 16-colour BMP preview of a pattern.

    Non-lace patterns use their colour map directly. Lace patterns are a
    single colour (the grid), so the stitch map is rendered instead: knit /
    return pass = light grid, lace transfer = navy, fine-lace = dark red.
    """
    if p.is_lace and p.stitch_values:
        ids = [bmp_writer.LACE_KNIT] * (p.width * p.height)
        for i, v in enumerate(p.stitch_values):
            if v == brother.LACE_TRANSFER:
                ids[i] = bmp_writer.LACE_TRANSFER
            elif v == brother.FINE_LACE_TRANSFER:
                ids[i] = bmp_writer.LACE_FINE
        return ids, bmp_writer.make_palette(bmp_writer.LACE_BMP)
    return list(p.colours), bmp_writer.make_palette(bmp_writer.MAIN_BMP)


def main(path):
    rom = Path(path)
    if not rom.exists():
        print(f'File not found: {rom}')
        return 1
    data = rom.read_bytes()
    fmt, patterns = brother.detect_and_parse(data)
    if not patterns:
        print(f'No recognised Brother pattern table in {rom.name}')
        return 1

    out_dir = rom.with_suffix('')
    out_dir.mkdir(exist_ok=True)
    bmp_dir = Path(str(rom.with_suffix('')) + '-bmp')
    bmp_dir.mkdir(exist_ok=True)

    report = [f'Source ROM : {rom.name}',
              f'Format     : {fmt}',
              f'Patterns   : {len(patterns)}',
              f'Output     : {out_dir}',
              f'Preview    : {bmp_dir}',
              '']
    n = 0
    for p in patterns:
        stp = stp_writer.build_stp(p.width, p.height, p.colours,
                                   p.stitch_values, lace=p.is_lace)
        fname = out_dir / f'{p.index:03d}.STP'
        fname.write_bytes(stp)

        ids, palette = bmp_preview(p)
        (bmp_dir / f'{p.index:03d}.bmp').write_bytes(
            bmp_writer.build_bmp(p.width, p.height, ids, palette))
        n += 1

        rc = p.row_codes
        rc_summary = 'all-zero' if not any(rc) else ''.join(f'{v:x}' for v in rc)
        planes = '' if p.planes == 1 else f'  planes={p.planes}'
        lace = '  lace' if p.is_lace else ''
        report.append(
            f'#{p.index:03d}  {p.width}x{p.height}  type={p.typ:#04x}  '
            f'colours={p.num_colours}{planes}{lace}  offset=0x{p.offset:X}  '
            f'row-codes({rc_summary})')

    (out_dir / 'report.txt').write_text('\n'.join(report), encoding='utf-8')
    print(f'{fmt}: wrote {n} patterns to {out_dir} and {bmp_dir}')
    return 0


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(__doc__)
        # keep the window open when double-clicked / run without a file
        try:
            input('Drag a .bin file onto this program (or type a path), then press Enter...')
        except (EOFError, OSError):
            pass
        sys.exit(2)

    rc = 0
    for p in sys.argv[1:]:
        try:
            rc |= main(p)
        except Exception as e:  # noqa: BLE001 - report and continue on bad files
            print(f'ERROR processing {p}: {e}')
            rc = 1
        print()

    # pause so the console stays open when launched from Explorer / drag-and-drop
    if getattr(sys, 'frozen', False):
        try:
            input('Done. Press Enter to exit...')
        except (EOFError, OSError):
            pass
    sys.exit(rc)
