#!/usr/bin/env python3
"""CSV по клиентским анкорным статьям — с постоянными ЧПУ-URL.

Для отложенных статей WordPress отдаёт временный адрес вида ?p=N.
Здесь он заменяется на постоянный ЧПУ-адрес /<рубрика-slug>/<post-slug>/,
который станет рабочим после авто-публикации статьи. Структура ЧПУ
проверяется на уже опубликованных статьях каждого сайта.
"""

import os
import json
import csv
import glob
import base64
import argparse
import requests
from urllib.parse import urlparse
from dotenv import load_dotenv

load_dotenv()

ap = argparse.ArgumentParser()
ap.add_argument('--sites-file', default='campaign2_sites.json')
ap.add_argument('--plan', default='content_plan.csv')
ap.add_argument('--reports', nargs='+', default=None,
                help='Отчёты publish_all_*.json / republish_*.json. '
                     'По умолчанию — все из reports/.')
ap.add_argument('--out', default='reports/campaign2_anchors.csv')
args = ap.parse_args()

proxies = {}
if os.getenv('PROXY_HTTP'):
    proxies['http'] = os.getenv('PROXY_HTTP')
if os.getenv('PROXY_HTTPS'):
    proxies['https'] = os.getenv('PROXY_HTTPS')

sites = {s['domain']: s for s in json.load(open(args.sites_file, encoding='utf-8'))}
site_by_id = {s['id']: s for s in sites.values()}

# анкорные статьи из контент-плана
anchors = []
for row in csv.DictReader(open(args.plan, encoding='utf-8'), delimiter=';'):
    if row['Тип'] == 'анкор клиента':
        anchors.append((int(row['Сайт']), row['Тема статьи'],
                        row['Анкор'], row['Ссылка']))
anchors.sort()

# post_id по (домен, тема) из указанных отчётов
post_id_by = {}
report_paths = args.reports
if not report_paths:
    report_paths = (glob.glob('reports/publish_all_*.json')
                    + glob.glob('reports/republish_*.json'))
for path in report_paths:
    for r in json.load(open(path, encoding='utf-8')):
        if (r.get('status') == 'success' and r.get('post_id')
                and r.get('domain') in sites):
            post_id_by[(r['domain'], r['topic'])] = r['post_id']


def auth(site):
    enc = base64.b64encode(f"{site['username']}:{site['password']}".encode()).decode()
    return {'Authorization': f'Basic {enc}'}


def wget(url, headers, params):
    for px in (proxies, None):
        try:
            r = requests.get(url, headers=headers, params=params, proxies=px, timeout=25)
            if r.status_code == 200:
                return r.json()
        except Exception:
            continue
    return None


_cat_slug = {}


def category_slug(domain, api, headers, cat_id):
    key = (domain, cat_id)
    if key not in _cat_slug:
        j = wget(f"{api}/categories/{cat_id}", headers, {'_fields': 'slug'})
        _cat_slug[key] = j.get('slug') if j else None
    return _cat_slug[key]


def host_of(link):
    p = urlparse(link)
    return f"{p.scheme}://{p.netloc}"


_struct = {}


def structure_ok(domain, api, headers):
    """True — у сайта структура /<рубрика>/<slug>/, проверено на
    опубликованной статье. None — проверить не удалось."""
    if domain in _struct:
        return _struct[domain]
    result = None
    lst = wget(f"{api}/posts", headers,
               {'status': 'publish', 'per_page': 1,
                '_fields': 'link,slug,categories'})
    if isinstance(lst, list) and lst:
        sp = lst[0]
        link, slug, cats = sp.get('link', ''), sp.get('slug', ''), sp.get('categories') or []
        if link and slug and cats and '?p=' not in link:
            cslug = category_slug(domain, api, headers, cats[0])
            if cslug:
                result = f"{host_of(link)}/{cslug}/{slug}/" == link
    _struct[domain] = result
    return result


rows = []
verified, assumed, problems = 0, 0, 0

for i, (sid, topic, anchor, target) in enumerate(anchors, 1):
    site = site_by_id[sid]
    domain = site['domain']
    headers = auth(site)
    api = f"{site['url']}/wp-json/wp/v2"

    pid = post_id_by.get((domain, topic))
    post = wget(f"{api}/posts/{pid}", headers,
                {'_fields': 'slug,link,status,date,categories'}) if pid else None
    if not post:
        rows.append([i, domain, '', 'ОШИБКА: пост не найден', anchor, target])
        problems += 1
        continue

    link = post.get('link', '')
    slug = post.get('slug', '')
    cats = post.get('categories') or []
    date = (post.get('date') or '')[:10]
    is_ugly = '?p=' in link or '?page_id=' in link

    if not is_ugly:
        # статья уже опубликована — ЧПУ-адрес финальный
        rows.append([i, domain, date, link, anchor, target])
        verified += 1
        continue

    # отложенная статья — собрать постоянный ЧПУ-адрес
    if not cats or not slug:
        rows.append([i, domain, date, link, anchor, target])
        problems += 1
        continue
    cslug = category_slug(domain, api, headers, cats[0])
    if not cslug:
        rows.append([i, domain, date, link, anchor, target])
        problems += 1
        continue

    pretty = f"{host_of(link)}/{cslug}/{slug}/"
    ok = structure_ok(domain, api, headers)
    if ok is True:
        verified += 1
    elif ok is False:
        problems += 1
        print(f"  ⚠ {domain}: структура ЧПУ не /<рубрика>/<slug>/ — адрес под вопросом")
    else:
        assumed += 1
        print(f"  ~ {domain}: нет опубликованных статей для проверки структуры — адрес собран по стандарту")
    rows.append([i, domain, date, pretty, anchor, target])

os.makedirs(os.path.dirname(args.out) or '.', exist_ok=True)
with open(args.out, 'w', encoding='utf-8-sig', newline='') as f:
    w = csv.writer(f)
    w.writerow(['№', 'Сайт', 'Дата публикации', 'URL статьи', 'Анкор', 'Целевая ссылка'])
    w.writerows(rows)

print(f"\nЗаписано: {args.out} — {len(rows)} строк")
print(f"  URL подтверждён/проверен: {verified}")
print(f"  URL собран по стандартной структуре (без проверки): {assumed}")
print(f"  проблемных: {problems}")
ugly_left = [r for r in rows if '?p=' in r[3] or 'ОШИБКА' in r[3]]
if ugly_left:
    print("Остались проблемные строки:")
    for r in ugly_left:
        print(f"  №{r[0]} {r[1]}: {r[3]}")
