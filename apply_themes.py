#!/usr/bin/env python3
"""Раздача тем и оформления донорам сети.

Двадцать сайтов на одной стоковой теме — готовый отпечаток сети: их
опознают по разметке с первого взгляда. Скрипт ставит каждому донору
тему из каталога wordpress.org и свой акцентный цвет со своей парой
шрифтов, чтобы сайты не выглядели роднёй.

Раздача детерминированная: тема, цвет и шрифт зависят только от имени
домена, поэтому повторный запуск ничего не переставит, а --only не
сдвигает круг. Тем семь, стилей обложек восемь, палитр десять — пары не
повторяются ни у одного из двадцати сайтов.

Что делает на каждом сайте:

1. ставит и включает тему (`wp theme install --activate`);
2. заводит меню из рубрик и вешает его в первую область темы — без
   этого классические темы показывают пустую шапку;
3. кладёт своё оформление в «Дополнительные стили» — это работает с
   любой темой, в отличие от настроек конкретной.

    python3 apply_themes.py --dry-run
    python3 apply_themes.py --only yellodigital.ru
    python3 apply_themes.py
"""
from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys

SERVER = "root@157.228.135.19"
SSH_KEY = "~/.ssh/pbn_recovery"
WWW = "/var/www"

# Все проверены на совместимость с WP 7.1 / PHP 8.2, рейтинг 94–100%,
# от 80 тысяч установок — на общем фоне не выделяются.
THEMES = ['astra', 'blocksy', 'generatepress', 'kadence', 'lightning', 'neve', 'sydney']

# Акцент и пара шрифтов. Стеки системные: без загрузки с чужих доменов,
# иначе получаем и лишний запрос, и ещё один общий признак сети.
ACCENTS = ['#1f6feb', '#b4413c', '#0f7b6c', '#8250df', '#bf5b04',
           '#0b6bcb', '#a4243b', '#2d6a4f', '#6d4aa8', '#c2410c']
FONTS = [
    ('Georgia, "Times New Roman", serif', 'system-ui, -apple-system, "Segoe UI", sans-serif'),
    ('"Segoe UI", system-ui, sans-serif', 'Georgia, "Times New Roman", serif'),
    ('"Helvetica Neue", Helvetica, Arial, sans-serif', 'system-ui, sans-serif'),
    ('Palatino, "Palatino Linotype", Georgia, serif', '"Segoe UI", system-ui, sans-serif'),
    ('Verdana, Geneva, sans-serif', 'Georgia, serif'),
    ('"Trebuchet MS", Tahoma, sans-serif', 'system-ui, -apple-system, sans-serif'),
]


def plan(domains: list[str]) -> dict[str, dict]:
    """Тема, цвет и шрифты по имени домена. Разные модули — разные пары."""
    out = {}
    for i, d in enumerate(sorted(domains)):
        head, body = FONTS[i % len(FONTS)]
        out[d] = {
            'theme': THEMES[i % len(THEMES)],
            'accent': ACCENTS[i % len(ACCENTS)],
            'head_font': head,
            'body_font': body,
        }
    return out


def css_for(spec: dict) -> str:
    """Оформление поверх темы. Намеренно скромное: цвет ссылок, шрифты и
    воздух вокруг обложек. Ничего, что могло бы развалить вёрстку."""
    return f""":root {{ --pbn-accent: {spec['accent']}; }}
.entry-content a, .wp-block-post-content a, .post-content a {{
  color: var(--pbn-accent);
  text-underline-offset: .15em;
}}
h1, h2, h3, .entry-title, .wp-block-post-title {{
  font-family: {spec['head_font']};
  letter-spacing: -.01em;
}}
body, .entry-content, .wp-block-post-content {{ font-family: {spec['body_font']}; }}
.wp-post-image, .post-thumbnail img, .wp-block-post-featured-image img {{
  border-radius: 10px;
}}
"""


def remote_script(domain: str, spec: dict) -> str:
    """Шаг для одного сайта. Идемпотентен: тема уже стоит — не переставляем,
    меню уже есть — не плодим второе."""
    path = f"{WWW}/{domain}"
    css = css_for(spec)
    return f"""
set -u
P={shlex.quote(path)}
THEME={shlex.quote(spec['theme'])}
w() {{ sudo -u www-data -H WP_CLI_CACHE_DIR=/tmp/wpcli wp "$@" --path="$P"; }}

echo "--- {domain}: тема $THEME ---"
if [ "$(w theme list --status=active --field=name 2>/dev/null)" = "$THEME" ]; then
  echo "  тема уже включена"
else
  w theme install "$THEME" --activate --quiet 2>&1 | tail -2 || {{ echo "  НЕ УСТАНОВЛЕНА"; exit 1; }}
  echo "  включена: $(w theme list --status=active --field=name 2>/dev/null)"
fi

# Меню из рубрик: у классических тем без него пустая шапка.
# menu location list не принимает --fields, только --format — берём первый столбец.
# Область выбираем не первую попавшуюся: у blocksy первой идёт footer, и меню
# уезжает в подвал вместо шапки. Сначала ищем что-то заголовочное.
LOCS=$(w menu location list --format=csv 2>/dev/null | tail -n +2 | cut -d, -f1)
LOC=""
for want in primary main menu_1 menu-1 header global-nav top-bar; do
  LOC=$(printf '%s\n' "$LOCS" | grep -xF "$want" | head -1) && [ -n "$LOC" ] && break
done
[ -n "$LOC" ] || LOC=$(printf '%s\n' "$LOCS" | head -1)
if [ -n "$LOC" ]; then
  # Меню с пунктами уже есть — берём его, а не плодим второе.
  MENU=$(w menu list --format=csv 2>/dev/null | awk -F, 'NR>1 && $NF+0>0 {{print $3; exit}}')
  if [ -z "$MENU" ]; then
    MENU=glavnoe
    w menu create "Главное" >/dev/null 2>&1 || true
    # Только рубрики с записями: пустые «Без рубрики» в шапке ни к чему.
    for C in $(w term list category --format=csv 2>/dev/null \
               | awk -F, 'NR>1 && $NF+0>0 {{print $1}}' | head -6); do
      w menu item add-term "$MENU" category "$C" >/dev/null 2>&1 || true
    done
  fi
  w menu location assign "$MENU" "$LOC" >/dev/null 2>&1 \
    && echo "  меню '$MENU' повешено в область '$LOC' ($(w menu list --format=csv 2>/dev/null | awk -F, -v m="$MENU" '$3==m {{print $NF}}') пунктов)" \
    || echo "  меню назначить не удалось"
else
  echo "  у темы нет областей меню (блочная) — пропускаем"
fi

cat > /tmp/pbn.css <<'CSSEOF'
{css}CSSEOF
w eval 'wp_update_custom_css_post(file_get_contents("/tmp/pbn.css"));' >/dev/null 2>&1 \
  && echo "  оформление применено (акцент {spec['accent']})" \
  || echo "  оформление применить не удалось"
rm -f /tmp/pbn.css
"""


def main():
    ap = argparse.ArgumentParser(description="Раздача тем и оформления донорам")
    ap.add_argument('--sites-file', default='reports/recovery/restored_sites.json')
    ap.add_argument('--only', default=None, help='домены через запятую')
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    domains = [s['domain'] for s in json.load(open(args.sites_file, encoding='utf-8'))]
    spec = plan(domains)
    if args.only:
        want = {d.strip() for d in args.only.split(',')}
        unknown = want - set(spec)
        if unknown:
            sys.exit(f"нет таких доменов: {', '.join(sorted(unknown))}")
        targets = sorted(want)
    else:
        targets = sorted(spec)

    print(f"{'домен':<32} {'тема':<15} {'акцент':<9} шрифт заголовков")
    print('-' * 88)
    for d in targets:
        s = spec[d]
        print(f"{d:<32} {s['theme']:<15} {s['accent']:<9} {s['head_font'][:34]}")
    print('-' * 88)

    if args.dry_run:
        print(f"\nРЕЖИМ ПРОСМОТРА: {len(targets)} сайтов, ничего не меняем.")
        return 0

    failed = []
    for d in targets:
        script = remote_script(d, spec[d])
        r = subprocess.run(
            ['ssh', '-i', SSH_KEY.replace('~', __import__('os').path.expanduser('~')),
             '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=20', SERVER, 'bash -s'],
            input=script, text=True, capture_output=True, timeout=300)
        print(r.stdout.rstrip())
        if r.returncode != 0:
            failed.append(d)
            print(f"  ОШИБКА ssh ({r.returncode}): {r.stderr.strip()[:200]}")

    print(f"\n{'=' * 60}")
    print(f"ТЕМЫ: обработано {len(targets) - len(failed)} из {len(targets)}"
          + (f", с ошибками: {', '.join(failed)}" if failed else ", ошибок нет"))
    print('=' * 60)
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
