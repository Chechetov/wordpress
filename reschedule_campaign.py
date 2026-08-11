#!/usr/bin/env python3
"""Сжатие расписания уже созданных отложенных постов кампании.

Посты не перепубликуются — у существующих записей правится только дата
(PATCH /wp/v2/posts/<id>). Порядок статей внутри донора сохраняется, поэтому
анкорная статья остаётся на своём месте в цепочке.

    python3 reschedule_campaign.py --sites-file campaign4_sites.json \
        --plan content_plan_campaign4.csv --state reports/campaign4_state.json \
        --start 2026-08-12 --deadline 2026-08-25 --dry-run
"""
from __future__ import annotations

import argparse
import base64
import csv
import json
import os
import random
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

import requests
from dotenv import load_dotenv

load_dotenv()


def build_dates(n, site_start, deadline, rnd):
    """n возрастающих дат от site_start, последняя не позже deadline.

    Шаги между статьями случайные (1–3 дня). Если цепочка не влезает в окно,
    шаги пропорционально ужимаются. Равномерное деление окна здесь не годится:
    оно выстраивает все доноры в шеренгу, и анкоры сбиваются в один день.
    """
    span = (deadline - site_start).days
    gaps = [rnd.uniform(1.0, 3.0) for _ in range(n - 1)]
    total = sum(gaps)
    if total > span:                              # не влезаем — ужимаем шаги
        gaps = [g * span / total for g in gaps]
    days, acc = [0.0], 0.0
    for g in gaps:
        acc += g
        days.append(acc)
    out, prev = [], None
    for d in days:
        dt = site_start + timedelta(days=d)
        dt = dt.replace(hour=rnd.randint(8, 21), minute=rnd.randint(5, 55),
                        second=0, microsecond=0)
        if prev and dt <= prev:                  # строго по возрастанию
            dt = prev + timedelta(hours=rnd.randint(3, 8))
        out.append(dt)
        prev = dt
    return out


def patch_date(site, post_id, when, proxies):
    api = f"{site['url'].rstrip('/')}/wp-json/wp/v2/posts/{post_id}"
    enc = base64.b64encode(f"{site['username']}:{site['password']}".encode()).decode()
    headers = {'Authorization': f'Basic {enc}', 'Content-Type': 'application/json'}
    payload = {'date': when.strftime('%Y-%m-%dT%H:%M:%S'), 'status': 'future'}
    for attempt in range(3):
        try:
            r = requests.post(api, headers=headers, json=payload,
                              proxies=proxies, timeout=90)
            if r.status_code == 200:
                got = r.json().get('date', '')[:16]
                return got == when.strftime('%Y-%m-%dT%H:%M'), got
        except Exception:
            pass
    return False, 'нет ответа'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--sites-file', default='campaign4_sites.json')
    ap.add_argument('--plan', default='content_plan_campaign4.csv')
    ap.add_argument('--state', required=True)
    ap.add_argument('--start', required=True, help='YYYY-MM-DD — не раньше этой даты')
    ap.add_argument('--deadline', required=True, help='YYYY-MM-DD — последняя допустимая дата')
    ap.add_argument('--site-spread', type=int, default=5,
                    help='на сколько дней разносить старты доноров')
    ap.add_argument('--seed', type=int, default=11)
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    rnd = random.Random(args.seed)
    start = datetime.strptime(args.start, '%Y-%m-%d')
    deadline = datetime.strptime(args.deadline, '%Y-%m-%d')

    proxies = {}
    if os.getenv('PROXY_HTTP'):
        proxies['http'] = os.getenv('PROXY_HTTP')
    if os.getenv('PROXY_HTTPS'):
        proxies['https'] = os.getenv('PROXY_HTTPS')

    sites = {s['id']: s for s in json.load(open(args.sites_file, encoding='utf-8'))}
    plan = list(csv.DictReader(open(args.plan, encoding='utf-8-sig'), delimiter=';'))
    post_id = {(r['domain'], r['topic']): r['post_id']
               for r in json.load(open(args.state, encoding='utf-8'))}

    jobs = []
    for i, (site_id, site) in enumerate(sites.items()):
        rows = [r for r in plan if int(r['Сайт']) == site_id]
        site_start = start + timedelta(days=i % args.site_spread,
                                       hours=rnd.randint(0, 12))
        dates = build_dates(len(rows), site_start, deadline, rnd)
        for row, when in zip(rows, dates):
            pid = post_id.get((site['domain'], row['Тема статьи']))
            if pid:
                jobs.append((site, pid, when, row))

    last = max(w for _, _, w, _ in jobs)
    anchors = sorted(w for _, _, w, r in jobs if r['Тип'] == 'анкор клиента')
    print(f"Постов к переносу: {len(jobs)}")
    print(f"Новый период: {min(w for _, _, w, _ in jobs):%d.%m %H:%M} — {last:%d.%m %H:%M}")
    print(f"Анкоры: {anchors[0]:%d.%m} — {anchors[-1]:%d.%m}")
    from collections import Counter
    print("Анкоров по дням:", dict(sorted(Counter(f"{a:%d.%m}" for a in anchors).items())))
    print("Статей по дням:", dict(sorted(Counter(f"{w:%d.%m}" for _, _, w, _ in jobs).items())))
    if last > deadline + timedelta(days=1):
        raise SystemExit(f"ОШИБКА: последняя дата {last} выходит за дедлайн")

    if args.dry_run:
        print("\n[DRY RUN] Даты не менялись.")
        return

    with ThreadPoolExecutor(max_workers=4) as ex:
        results = list(ex.map(lambda j: (j[0]['domain'], j[1], j[2],
                                         *patch_date(j[0], j[1], j[2], proxies)), jobs))
    ok = [r for r in results if r[3]]
    print(f"\nПеренесено: {len(ok)} из {len(results)}")
    for dom, pid, when, good, got in results:
        if not good:
            print(f"  ✗ {dom} ID={pid}: ждали {when:%Y-%m-%d %H:%M}, получили {got}")


if __name__ == '__main__':
    main()
