#!/usr/bin/env python3
"""Проверка опубликованных статей кампании: ссылки и обложки.

Для каждой строки плана сверяет фактический пост на доноре:
  * анкорная ссылка присутствует, ведёт на нужный URL, текст анкора совпадает;
  * траст-ссылка присутствует;
  * у поста есть обложка (featured_media);
  * ссылка не помечена rel="nofollow".

    python3 verify_campaign.py --sites-file campaign4_sites.json \
        --plan content_plan_campaign4.csv --state reports/campaign4_state.json
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

import requests
from dotenv import load_dotenv

load_dotenv()


def fetch_content(site, post_ids, proxies):
    """{post_id: (html, featured_media)} для указанных постов сайта."""
    api = f"{site['url'].rstrip('/')}/wp-json/wp/v2/posts"
    enc = base64.b64encode(f"{site['username']}:{site['password']}".encode()).decode()
    headers = {'Authorization': f'Basic {enc}'}
    out = {}
    # Пачками по 5: ответ с полным телом статей тяжёлый, прокси рвёт крупные.
    for chunk_start in range(0, len(post_ids), 5):
        chunk = post_ids[chunk_start:chunk_start + 5]
        params = {'include': ','.join(map(str, chunk)), 'per_page': len(chunk),
                  'status': 'publish,future,draft',
                  '_fields': 'id,content,featured_media'}
        for px in (proxies, None):
            try:
                r = requests.get(api, headers=headers, params=params,
                                 proxies=px, timeout=90)
                if r.status_code == 200:
                    for p in r.json():
                        out[p['id']] = (p['content']['rendered'],
                                        p.get('featured_media', 0))
                    break
            except Exception:
                continue

    # Что не долетело пачкой — добираем по одной статье, с повторами.
    for pid in [p for p in post_ids if p not in out]:
        for attempt in range(3):
            try:
                r = requests.get(f"{api}/{pid}", headers=headers,
                                 params={'_fields': 'id,content,featured_media'},
                                 proxies=proxies, timeout=90)
                if r.status_code == 200:
                    p = r.json()
                    out[pid] = (p['content']['rendered'], p.get('featured_media', 0))
                    break
            except Exception:
                pass
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--sites-file', default='campaign4_sites.json')
    ap.add_argument('--plan', default='content_plan_campaign4.csv')
    ap.add_argument('--state', required=True, help='JSON от reconcile_campaign.py')
    args = ap.parse_args()

    proxies = {}
    if os.getenv('PROXY_HTTP'):
        proxies['http'] = os.getenv('PROXY_HTTP')
    if os.getenv('PROXY_HTTPS'):
        proxies['https'] = os.getenv('PROXY_HTTPS')

    sites = {s['id']: s for s in json.load(open(args.sites_file, encoding='utf-8'))}
    plan = list(csv.DictReader(open(args.plan, encoding='utf-8-sig'), delimiter=';'))
    state = json.load(open(args.state, encoding='utf-8'))
    post_id = {(r['domain'], r['topic']): r['post_id'] for r in state}

    by_site = {}
    for row in plan:
        site = sites[int(row['Сайт'])]
        pid = post_id.get((site['domain'], row['Тема статьи']))
        if pid:
            by_site.setdefault(site['id'], []).append((pid, row))

    with ThreadPoolExecutor(max_workers=6) as ex:
        contents = dict(zip(
            by_site,
            ex.map(lambda sid: fetch_content(sites[sid],
                                             [p for p, _ in by_site[sid]], proxies),
                   by_site)))

    problems, checked, no_cover, nofollow = [], 0, 0, 0
    for sid, items in by_site.items():
        domain = sites[sid]['domain']
        for pid, row in items:
            got = contents[sid].get(pid)
            if got is None:
                problems.append(f"{domain} ID={pid}: не удалось получить содержимое")
                continue
            body, media = got
            checked += 1
            if not media:
                no_cover += 1
                problems.append(f"{domain} ID={pid}: нет обложки — {row['Тема статьи'][:50]}")

            target, anchor = row['Ссылка'], row['Анкор']
            if not target:
                continue
            m = re.search(r'<a\b[^>]*href=["\']' + re.escape(target) + r'["\'][^>]*>(.*?)</a>',
                          body, re.I | re.S)
            if not m:
                problems.append(f"{domain} ID={pid}: НЕТ ССЫЛКИ {target} "
                                f"[{row['Тип']}] — {row['Тема статьи'][:45]}")
                continue
            if 'nofollow' in m.group(0).lower():
                nofollow += 1
                problems.append(f"{domain} ID={pid}: ссылка с nofollow — {target}")
            text = html.unescape(re.sub(r'<[^>]+>', '', m.group(1))).strip()
            if text.lower() != anchor.lower():
                problems.append(f"{domain} ID={pid}: анкор «{text}» вместо «{anchor}»")

    anchors = [r for r in plan if r['Тип'] == 'анкор клиента']
    trusts = [r for r in plan if r['Тип'] == 'траст']
    print(f"Проверено статей: {checked} из {len(plan)}")
    print(f"  анкорных ссылок в плане: {len(anchors)}, трастовых: {len(trusts)}")
    print(f"  без обложки: {no_cover}, с nofollow: {nofollow}")
    if problems:
        print(f"\nПроблемы ({len(problems)}):")
        for p in problems:
            print("  " + p)
    else:
        print("\nПроблем не найдено: все ссылки на месте, анкоры совпадают, обложки есть.")


if __name__ == '__main__':
    main()
