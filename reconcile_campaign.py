#!/usr/bin/env python3
"""Сверка контент-плана с тем, что реально опубликовано на донорах.

Ходит по сайтам через WordPress REST API, забирает посты, созданные начиная
с --after, и сопоставляет их с темами плана по порядку публикации: статьи
сайта уходят строго в порядке плана. Заголовки модель переписывает вольно,
поэтому схожесть текста считается только как индикатор для ручной проверки.

Зачем: прогон может оборваться (убитый процесс, разрыв соединения после
создания поста), и лог перестаёт быть источником правды. Скрипт отвечает на
вопрос «что осталось опубликовать» так, чтобы не наплодить дублей.

    python3 reconcile_campaign.py --sites-file campaign4_sites.json \
        --plan content_plan_campaign4.csv --after 2026-08-10 \
        --out content_plan_campaign4_remaining.csv
"""
from __future__ import annotations

import argparse
import base64
import csv
import html
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor
from difflib import SequenceMatcher

import requests
from dotenv import load_dotenv

load_dotenv()

MATCH_THRESHOLD = 0.45


def norm(s: str) -> str:
    s = html.unescape(s).lower().replace('ё', 'е')
    return re.sub(r'[^a-zа-я0-9 ]+', ' ', s)


def similarity(a: str, b: str) -> float:
    """Схожесть темы и заголовка: пересечение слов + посимвольная близость."""
    wa, wb = set(norm(a).split()), set(norm(b).split())
    jaccard = len(wa & wb) / len(wa | wb) if wa | wb else 0
    return max(jaccard, SequenceMatcher(None, norm(a), norm(b)).ratio())


def fetch_posts(site, after, proxies):
    api = f"{site['url'].rstrip('/')}/wp-json/wp/v2/posts"
    enc = base64.b64encode(f"{site['username']}:{site['password']}".encode()).decode()
    headers = {'Authorization': f'Basic {enc}'}
    params = {'per_page': 100, 'status': 'publish,future,draft',
              'after': f'{after}T00:00:00', '_fields': 'id,title,date,status'}
    for px in (proxies, None):
        try:
            r = requests.get(api, headers=headers, params=params, proxies=px, timeout=60)
            if r.status_code == 200:
                return [{'id': p['id'],
                         'title': html.unescape(p['title']['rendered']).strip(),
                         'date': p['date'], 'status': p['status']} for p in r.json()]
        except Exception:
            continue
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--sites-file', default='campaign4_sites.json')
    ap.add_argument('--plan', default='content_plan_campaign4.csv')
    ap.add_argument('--after', required=True, help='YYYY-MM-DD — с какой даты считать посты кампании')
    ap.add_argument('--out', default=None, help='куда записать остаток плана')
    ap.add_argument('--report-out', default=None,
                    help='JSON в формате отчёта publish_all (для build_anchors_csv.py)')
    args = ap.parse_args()

    proxies = {}
    if os.getenv('PROXY_HTTP'):
        proxies['http'] = os.getenv('PROXY_HTTP')
    if os.getenv('PROXY_HTTPS'):
        proxies['https'] = os.getenv('PROXY_HTTPS')

    sites = json.load(open(args.sites_file, encoding='utf-8'))
    by_id = {s['id']: s for s in sites}
    plan = list(csv.DictReader(open(args.plan, encoding='utf-8-sig'), delimiter=';'))

    with ThreadPoolExecutor(max_workers=6) as ex:
        fetched = dict(zip([s['id'] for s in sites],
                           ex.map(lambda s: fetch_posts(s, args.after, proxies), sites)))

    remaining, done, unreachable, extra = [], [], [], []
    for site_id, site in by_id.items():
        rows = [r for r in plan if int(r['Сайт']) == site_id]
        posts = fetched[site_id]
        if posts is None:
            unreachable.append(site['domain'])
            remaining.extend(rows)          # сайт недоступен — считаем всё неопубликованным
            continue

        # Сопоставляем по позиции, а не по заголовку: статьи сайта публикуются
        # строго в порядке плана, поэтому N-й по времени пост — это N-я тема.
        # Заголовки модель переписывает свободно («частые ошибки заказчиков» →
        # «Ошибки при заказе фотобудки в Москве»), и матчинг по тексту путает
        # соседние темы — в том числе принимает анкорную статью за обычную.
        # Схожесть считаем только как индикатор для ручной проверки.
        posts = sorted(posts, key=lambda p: p['id'])
        if len(posts) > len(rows):
            extra.append((site['domain'], len(posts), len(rows)))

        for row, post in zip(rows, posts):
            done.append((site['domain'], row['Тема статьи'], post['id'],
                         post['date'], post['status'],
                         round(similarity(row['Тема статьи'], post['title']), 2)))
        remaining.extend(rows[len(posts):])

    print(f"{'донор':<22}{'в плане':>9}{'опубликовано':>14}{'осталось':>10}")
    for site_id, site in by_id.items():
        total = sum(1 for r in plan if int(r['Сайт']) == site_id)
        d = sum(1 for x in done if x[0] == site['domain'])
        mark = '  ← недоступен' if site['domain'] in unreachable else ''
        print(f"{site['domain']:<22}{total:>9}{d:>14}{total - d:>10}{mark}")

    print(f"\nВСЕГО: план {len(plan)}, опубликовано {len(done)}, осталось {len(remaining)}")
    print(f"Анкоров клиента осталось: "
          f"{sum(1 for r in remaining if r['Тип'] == 'анкор клиента')}")
    if extra:
        print("\nПостов больше, чем тем в плане (посторонние публикации?):")
        for dom, np_, nr in extra:
            print(f"  {dom}: постов {np_}, тем {nr}")

    weak = [x for x in done if x[5] < 0.6]
    if weak:
        print(f"\nНизкая схожесть заголовка с темой ({len(weak)}) — сверка по позиции, "
              f"это нормально при вольном заголовке:")
        for dom, topic, pid, date, st, sc in weak:
            print(f"  {sc}  {dom} ID={pid}  {topic[:60]}")

    if args.report_out:
        # Формат publish_all: прогон может оборваться, не записав свой отчёт,
        # поэтому собираем его из фактического состояния сайтов.
        json.dump([{'domain': dom, 'topic': topic, 'post_id': pid,
                    'scheduled': date[:16].replace('T', ' '), 'status': 'success'}
                   for dom, topic, pid, date, st, sc in done],
                  open(args.report_out, 'w', encoding='utf-8'),
                  ensure_ascii=False, indent=1)
        print(f"Отчёт по фактическому состоянию: {args.report_out} ({len(done)} записей)")

    if args.out:
        with open(args.out, 'w', encoding='utf-8', newline='') as f:
            w = csv.writer(f, delimiter=';')
            w.writerow(['Сайт', 'Рубрика', 'Тема статьи', 'Анкор', 'Ссылка', 'Тип'])
            for r in remaining:
                w.writerow([r['Сайт'], r['Рубрика'], r['Тема статьи'],
                            r['Анкор'], r['Ссылка'], r['Тип']])
        print(f"\nОстаток записан: {args.out}")


if __name__ == '__main__':
    main()
