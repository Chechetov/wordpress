#!/usr/bin/env python3
"""Сбор отчёта по ссылкам кампании №2.

Берёт все опубликованные посты из отчётов publish_all_*.json и
republish_*.json, подтягивает живые URL статей из WordPress и формирует:
  - reports/campaign2_links.tsv  — плоская таблица (вставка в Google Sheets)
  - reports/campaign2_links.md   — анкорная таблица + полный список
"""

import os
import json
import csv
import glob
import base64
import requests
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv

load_dotenv()

proxies = {}
if os.getenv('PROXY_HTTP'):
    proxies['http'] = os.getenv('PROXY_HTTP')
if os.getenv('PROXY_HTTPS'):
    proxies['https'] = os.getenv('PROXY_HTTPS')

sites = {s['domain']: s for s in json.load(open('campaign2_sites.json', encoding='utf-8'))}

# контент-план: (site_id, topic) -> данные статьи
plan = {}
categories = {}
for row in csv.DictReader(open('content_plan.csv', encoding='utf-8'), delimiter=';'):
    sid = int(row['Сайт'])
    plan[(sid, row['Тема статьи'])] = {
        'anchor': row.get('Анкор', ''),
        'target': row.get('Ссылка', ''),
        'type': row.get('Тип', '') or 'тематическая',
    }
    categories[sid] = row['Рубрика']

# собрать опубликованные посты из отчётов — только по 29 сайтам кампании №2
# (отчёты прошлой кампании на старых доменах отфильтровываются)
posts = {}
for pat in ('reports/publish_all_*.json', 'reports/republish_*.json'):
    for path in glob.glob(pat):
        for r in json.load(open(path, encoding='utf-8')):
            if (r.get('status') == 'success' and r.get('post_id')
                    and r.get('domain') in sites):
                posts[(r['domain'], r['post_id'])] = r['topic']

print(f"Постов к обработке: {len(posts)}")


def fetch(item):
    (domain, post_id), topic = item
    site = sites.get(domain)
    if not site:
        return {'domain': domain, 'post_id': post_id, 'topic': topic, 'link': '', 'date': ''}
    cred = f"{site['username']}:{site['password']}"
    enc = base64.b64encode(cred.encode()).decode()
    headers = {'Authorization': f'Basic {enc}'}
    api = f"{site['url']}/wp-json/wp/v2/posts/{post_id}"
    params = {'_fields': 'id,link,date'}
    for use_proxy in (proxies, None):
        try:
            r = requests.get(api, headers=headers, params=params,
                             proxies=use_proxy, timeout=20)
            if r.status_code == 200:
                j = r.json()
                return {'domain': domain, 'post_id': post_id, 'topic': topic,
                        'link': j.get('link', ''), 'date': (j.get('date') or '')[:10]}
        except Exception:
            continue
    return {'domain': domain, 'post_id': post_id, 'topic': topic,
            'link': 'ОШИБКА ЗАГРУЗКИ', 'date': ''}


rows = []
with ThreadPoolExecutor(max_workers=6) as ex:
    futures = [ex.submit(fetch, it) for it in posts.items()]
    for f in as_completed(futures):
        rows.append(f.result())

# обогатить данными плана
for row in rows:
    site = sites.get(row['domain'])
    sid = site['id'] if site else 0
    info = plan.get((sid, row['topic']), {'anchor': '', 'target': '', 'type': '?'})
    row['site_id'] = sid
    row['category'] = categories.get(sid, '')
    row['anchor'] = info['anchor']
    row['target'] = info['target']
    row['type'] = info['type']

rows.sort(key=lambda r: (r['site_id'], r['date']))

# --- TSV (для вставки в Google Sheets) ---
with open('reports/campaign2_links.tsv', 'w', encoding='utf-8') as f:
    cols = ['Сайт ID', 'Домен', 'Рубрика', 'Тип', 'Тема статьи',
            'URL статьи', 'Дата', 'Анкор', 'Целевая ссылка']
    f.write('\t'.join(cols) + '\n')
    for r in rows:
        f.write('\t'.join([
            str(r['site_id']), r['domain'], r['category'], r['type'],
            r['topic'], r['link'], r['date'], r['anchor'], r['target'],
        ]) + '\n')

# --- Markdown ---
anchors = [r for r in rows if r['type'] == 'анкор клиента']
anchors.sort(key=lambda r: r['site_id'])
errors = [r for r in rows if r['link'] in ('', 'ОШИБКА ЗАГРУЗКИ')]

with open('reports/campaign2_links.md', 'w', encoding='utf-8') as f:
    f.write('# Кампания №2 — отчёт по ссылкам\n\n')
    f.write(f'Сформирован: {datetime.now():%Y-%m-%d %H:%M}  \n')
    f.write(f'Статей опубликовано: **{len(rows)}**  ·  '
            f'анкорных: **{len(anchors)}**  ·  '
            f'ошибок загрузки URL: **{len(errors)}**\n\n')

    f.write('## Анкорные статьи клиента\n\n')
    f.write('| # | Сайт | Дата | URL статьи | Анкор | Целевая ссылка |\n')
    f.write('|---|---|---|---|---|---|\n')
    for i, r in enumerate(anchors, 1):
        f.write(f"| {i} | {r['domain']} | {r['date']} | {r['link']} | "
                f"`{r['anchor']}` | {r['target']} |\n")

    f.write('\n## Все статьи по сайтам\n\n')
    cur = None
    for r in rows:
        if r['site_id'] != cur:
            cur = r['site_id']
            f.write(f"\n### Сайт {r['site_id']}: {r['domain']} — {r['category']}\n\n")
        mark = {'анкор клиента': '🔗 анкор', 'траст': '↗ траст'}.get(r['type'], '·')
        f.write(f"- [{mark}] {r['date']} — [{r['topic']}]({r['link']})\n")

print(f"\nГотово. Опубликовано {len(rows)} статей, анкорных {len(anchors)}, "
      f"ошибок URL {len(errors)}")
print('  reports/campaign2_links.tsv')
print('  reports/campaign2_links.md')
if errors:
    print('\nНе удалось получить URL:')
    for r in errors:
        print(f"  {r['domain']} post {r['post_id']} — {r['topic'][:50]}")
