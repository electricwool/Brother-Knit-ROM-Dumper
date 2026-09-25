import pathlib
import sys
from collections import Counter

DATA_START = 0xF8


def u8(b, p):
    return b[p] & 0xFF


def u16(b, p):
    return u8(b, p) | (u8(b, p + 1) << 8)


def u32(b, p):
    return u8(b, p) | (u8(b, p + 1) << 8) | (u8(b, p + 2) << 16) | (u8(b, p + 3) << 24)


def pstr(b, p):
    n = u8(b, p)
    return bytes(b[p + 1:p + 1 + n])


def scan(folder):
    files = sorted(pathlib.Path(folder).glob('*.STP')) + sorted(pathlib.Path(folder).glob('*.stp'))
    print(f'{len(files)} sample files')
    stats = {}
    dims = []

    def add(name, val):
        stats.setdefault(name, Counter())[val] += 1

    pal_n = Counter()
    pal_sym = Counter()
    remap_sizes = Counter()
    remap_head = Counter()
    fonts = Counter()

    for f in files:
        d = f.read_bytes()
        w = u16(d, 3)
        h = u16(d, 5)
        dims.append((w, h))
        add('0x07', u16(d, 0x07))
        add('0x09', u16(d, 0x09))
        add('0x0B', u16(d, 0x0B))
        add('0x0D', u16(d, 0x0D))
        add('0x0F', u16(d, 0x0F))
        add('0x11', u16(d, 0x11))
        add('0x13', u16(d, 0x13))
        add('0x15', u16(d, 0x15))
        add('0x17', u16(d, 0x17))
        add('0x19', u16(d, 0x19))
        add('0x1B', u16(d, 0x1B))
        add('0x1D', u16(d, 0x1D))
        add('0x1F', u8(d, 0x1F))
        add('0x20', u8(d, 0x20))
        add('0x21', u8(d, 0x21))
        add('0x22', u8(d, 0x22))
        add('0x23', u8(d, 0x23))
        add('0x24', u8(d, 0x24))
        add('0x25', u8(d, 0x25))
        add('0x26', u8(d, 0x26))
        add('0x27', u8(d, 0x27))
        add('0x28', u8(d, 0x28))
        add('0x29', u8(d, 0x29))
        add('0x2A', u8(d, 0x2A))
        add('0x2B', u8(d, 0x2B))
        add('0x2C', u8(d, 0x2C))
        add('0x2D', u8(d, 0x2D))
        add('0x2E', u8(d, 0x2E))
        add('0x2F', u8(d, 0x2F))
        add('u32(0x35)', u32(d, 0x35))
        add('u32(0x39)', u32(d, 0x39))
        add('u16(0x3D)', u16(d, 0x3D))
        add('u16(0x3F)', u16(d, 0x3F))
        add('pstr(0x41)', pstr(d, 0x41))
        add('pstr(0x60)', pstr(d, 0x60))
        add('font(0xB1)', d[0xB1:0xB6])
        # walk blocks to find palette start
        pos = DATA_START
        while True:
            bh = u16(d, pos)
            bn = u16(d, pos + 2)
            pos += bn + 4
            if bh == h:
                break
            if pos + 4 > len(d):
                break
        while True:
            bh = u16(d, pos)
            bn = u16(d, pos + 2)
            pos += bn + 4
            if bh == h:
                break
            if pos + 4 > len(d):
                break
        ps = pos
        # palette entries
        for i in range(0, 71):
            o = ps + i * 25
            if o + 25 > len(d):
                break
            nb = d[o]
            if nb & 0x10:
                pal_n[nb] += 1
                pal_sym[d[o + 1]] += 1
        rem = d[ps + 1775:]
        remap_sizes[len(rem)] += 1
        remap_head[rem[:4].hex(' ')] += 1

    print()
    print('=== header field value distributions (u16 fields) ===')
    for name in ['0x07', '0x09', '0x0B', '0x0D', '0x0F', '0x11', '0x13', '0x15', '0x17', '0x19', '0x1B', '0x1D']:
        c = stats[name]
        print(f'  {name:>5}: min={min(c)} max={max(c)} values={dict(sorted(c.items()))}')

    print()
    print('=== header byte fields ===')
    for name in ['0x1F', '0x20', '0x21', '0x22', '0x23', '0x24', '0x25', '0x26', '0x27', '0x28', '0x29', '0x2A', '0x2B', '0x2C', '0x2D', '0x2E', '0x2F']:
        c = stats[name]
        print(f'  {name:>5}: {dict(sorted(c.items()))}')

    print()
    print('=== key fields ===')
    for name in ['u32(0x35)', 'u32(0x39)', 'u16(0x3D)', 'u16(0x3F)']:
        c = stats[name]
        print(f'  {name:>10}: {dict(sorted(c.items()))}')

    print()
    print('=== pascal strings / font ===')
    print(f'  pstr(0x41): {dict(sorted(stats["pstr(0x41)"].items()))}')
    print(f'  pstr(0x60): {dict(sorted(stats["pstr(0x60)"].items()))}')
    print(f'  font(0xB1): {dict(sorted(stats["font(0xB1)"].items()))}')

    print()
    print('=== dimensions ===')
    ws = [w for w, h in dims]
    hs = [h for w, h in dims]
    print(f'  width  min={min(ws)} max={max(ws)}')
    print(f'  height min={min(hs)} max={max(hs)}')

    print()
    print('=== palette used-entry n bytes ===')
    print(f'  {dict(sorted(pal_n.items()))}')
    print('=== palette used-entry symbol bytes ===')
    print(f'  {dict(sorted(pal_sym.items()))}')
    print()
    print('=== remap table sizes ===')
    print(f'  {dict(sorted(remap_sizes.items()))}')
    print('=== remap table first 4 bytes ===')
    print(f'  {dict(sorted(remap_head.items()))}')


if __name__ == '__main__':
    scan(sys.argv[1] if len(sys.argv) > 1 else 'sample stp')
