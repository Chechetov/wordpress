#!/usr/bin/env python3
"""Пережатие картинок под порог российского origin.

Cloudflare не может забрать с российского origin ответ крупнее ~24 КБ:
замер 23.09.2026 на ledpnz.ru — 24 190 байт доезжают за 0.4 с, 35 906 уже
обрываются. Порог считается на каждый ответ, а не на соединение. Поэтому
картинки (WebP, JPEG, PNG) пережимаются не больше --limit байт под тем же
именем, в том же формате и с теми же размерами: в базе WordPress ничего
менять не нужно. PNG ужимается сокращением палитры, прозрачность сохраняется.

Нарезку WordPress (cover-122-1024x683.webp) скрипт делает заново из
оригинала (cover-122.webp), если пропорции совпадают: пережимать уже
сжатую копию — значит терять качество дважды. Кадрированные размеры
(150x150 и т. п.) пережимаются из самих себя.

Если файл не влезает даже при минимальном качестве, он уменьшается по
ширине до тех пор, пока не влезет. Таких мало — в основном полноразмерные
оригиналы 1536 px, которые темы показывают только в лайтбоксе.

Скрипт работает с локальной копией uploads, по серверу не ходит:

    ssh root@ORIGIN 'cd /var/www && find */wp-content/uploads -size +21k \\( -iname "*.webp" -o -iname "*.jpg" -o -iname "*.png" \\) \\
        | tar cf - -T -' | tar xf - -C src/
    python3 shrink_uploads.py src/ out/
    # out/ повторяет структуру src/, но содержит только пережатые файлы;
    # manifest.csv — что было и что стало.
"""

import argparse
import csv
import re
import sys
from concurrent.futures import ProcessPoolExecutor
from io import BytesIO
from pathlib import Path

from PIL import Image

SIZE_SUFFIX = re.compile(r'^(?P<base>.+)-(?P<w>\d+)x(?P<h>\d+)$')
MIN_QUALITY = 30
MAX_QUALITY = 85


# Формат файла не меняется: расширение зашито в базу WordPress. Для PNG
# «качество» — число цветов палитры, для JPEG и WebP — обычное качество.
FORMATS = {'.webp': 'WEBP', '.jpg': 'JPEG', '.jpeg': 'JPEG', '.png': 'PNG'}
PNG_COLORS = [16, 32, 64, 128, 256]

# --webp-payload: внутрь .png и .jpg кладётся WebP под прежним именем. Браузеры
# распознают формат картинки по содержимому, а не по расширению, а качество при
# 22 КБ несравнимо лучше: PNG с урезанной палитрой превращается в постер.


def levels(fmt):
    return PNG_COLORS if fmt == 'PNG' else list(range(MIN_QUALITY, MAX_QUALITY + 1))


def encode(img, level, fmt):
    buf = BytesIO()
    if fmt == 'WEBP':
        img.save(buf, 'WEBP', quality=level, method=6)
    elif fmt == 'JPEG':
        img.convert('RGB').save(buf, 'JPEG', quality=level, optimize=True, progressive=True)
    else:
        img.quantize(colors=level, method=Image.FASTOCTREE, dither=Image.FLOYDSTEINBERG) \
           .save(buf, 'PNG', optimize=True)
    return buf.getvalue()


def best_fit(img, limit, fmt):
    """Наибольший уровень качества, при котором файл влезает в limit, или None."""
    ls = levels(fmt)
    lo, hi, best = 0, len(ls) - 1, None
    while lo <= hi:
        mid = (lo + hi) // 2
        data = encode(img, ls[mid], fmt)
        if len(data) <= limit:
            best, lo = (ls[mid], data), mid + 1
        else:
            hi = mid - 1
    return best


def source_for(path):
    """Оригинал, из которого WordPress нарезал этот размер, если пропорции те же."""
    m = SIZE_SUFFIX.match(path.stem)
    if not m:
        return None
    parent = path.with_name(m['base'] + path.suffix)
    if not parent.exists():
        return None
    w, h = int(m['w']), int(m['h'])
    with Image.open(parent) as p:
        pw, ph = p.size
    if abs(pw / ph - w / h) > 0.01:
        return None
    return parent


def shrink(args):
    path, rel, out_root, limit, webp_payload = args
    try:
        return _shrink(path, rel, out_root, limit, webp_payload)
    except Exception as e:  # битый или экзотический файл не должен ронять прогон
        return [str(rel), path.stat().st_size, '', '', '', '', f'error: {e}']


def _shrink(path, rel, out_root, limit, webp_payload):
    old = path.stat().st_size
    with Image.open(path) as im:
        size = im.size
    fmt = 'WEBP' if webp_payload else FORMATS[path.suffix.lower()]
    parent = source_for(path)
    with Image.open(parent or path) as src:
        src = src.convert('RGBA' if src.mode in ('RGBA', 'LA', 'P') else 'RGB')
        img = src.resize(size, Image.LANCZOS) if src.size != size else src

        fit, scaled = best_fit(img, limit, fmt), size
        while fit is None:
            scaled = (int(scaled[0] * 0.9), int(scaled[1] * 0.9))
            fit = best_fit(img.resize(scaled, Image.LANCZOS), limit, fmt)

    quality, data = fit
    dest = out_root / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    return [str(rel), old, len(data), quality, f'{size[0]}x{size[1]}',
            f'{scaled[0]}x{scaled[1]}', 'parent' if parent else 'self']


def main():
    ap = argparse.ArgumentParser(description='Пережатие картинок под порог origin')
    ap.add_argument('src', type=Path, help='локальная копия, корень с каталогами доменов')
    ap.add_argument('out', type=Path, help='куда класть пережатые файлы')
    ap.add_argument('--limit', type=int, default=22000,
                    help='предел размера в байтах (по умолчанию 22000, порог ~24 КБ)')
    ap.add_argument('--workers', type=int, default=8)
    ap.add_argument('--webp-payload', action='store_true',
                    help='кодировать любой файл в WebP, сохраняя имя и расширение')
    ap.add_argument('--only-ext', default='',
                    help='через запятую: обработать только эти расширения, например png,jpg')
    args = ap.parse_args()
    only = {'.' + e.strip().lower() for e in args.only_ext.split(',') if e.strip()}

    jobs = [(p, p.relative_to(args.src), args.out, args.limit, args.webp_payload)
            for p in sorted(args.src.rglob('*'))
            if p.is_file() and p.suffix.lower() in FORMATS
            and (not only or p.suffix.lower() in only)
            if p.stat().st_size > args.limit]
    print(f'к пережатию: {len(jobs)} файлов', file=sys.stderr)

    args.out.mkdir(parents=True, exist_ok=True)
    with ProcessPoolExecutor(args.workers) as ex, \
            open(args.out / 'manifest.csv', 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['path', 'old_bytes', 'new_bytes', 'quality', 'size', 'encoded_size', 'source'])
        for i, row in enumerate(ex.map(shrink, jobs, chunksize=8), 1):
            w.writerow(row)
            if i % 200 == 0:
                print(f'  {i}/{len(jobs)}', file=sys.stderr)


if __name__ == '__main__':
    main()
