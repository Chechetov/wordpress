#!/usr/bin/env python3
"""Перенос дат клиентских анкорных статей: раскидать с 16 по 22 апреля"""

import os
import json
import csv
import base64
import requests
import random
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

proxies = {}
if os.getenv('PROXY_HTTP'):
    proxies['http'] = os.getenv('PROXY_HTTP')
if os.getenv('PROXY_HTTPS'):
    proxies['https'] = os.getenv('PROXY_HTTPS')

# Load sites
with open('sites.json', 'r') as f:
    all_sites = {s['id']: s for s in json.load(f)}

# Load content plan — find anchor articles
anchor_articles = {}
with open('content_plan.csv', 'r', encoding='utf-8') as f:
    for row in csv.DictReader(f, delimiter=';'):
        if row.get('Тип', '') == 'анкор клиента':
            sid = int(row['Сайт'])
            anchor_articles[sid] = row['Тема статьи']

# Target dates: spread 20 anchors across Apr 16-22
# 16: 5 шт, 17: 3, 18: 3, 19: 3, 20: 2, 21: 2, 22: 2
schedule_dates = (
    [16]*5 + [17]*3 + [18]*3 + [19]*3 + [20]*2 + [21]*2 + [22]*2
)
random.shuffle(schedule_dates)

# Different hours for each
hours_pool = [8, 9, 10, 11, 13, 14, 15, 16, 17, 18, 19, 20]
random.shuffle(hours_pool)

site_ids = sorted(anchor_articles.keys())

print(f"Перенос дат для {len(site_ids)} анкорных статей\n")

for i, sid in enumerate(site_ids):
    site = all_sites.get(sid)
    if not site:
        continue

    domain = site['domain']
    topic = anchor_articles[sid]

    # Auth
    cred = f"{site['username']}:{site['password']}"
    enc = base64.b64encode(cred.encode()).decode()
    headers = {
        'Authorization': f'Basic {enc}',
        'Content-Type': 'application/json'
    }
    api_base = f"{site['url']}/wp-json/wp/v2"

    # Detect proxy
    use_proxy = proxies
    try:
        r = requests.get(f"{api_base}/posts?per_page=1", headers=headers, proxies=proxies, timeout=10)
        if r.status_code != 200:
            r = requests.get(f"{api_base}/posts?per_page=1", headers=headers, timeout=10)
            if r.status_code == 200:
                use_proxy = None
    except:
        try:
            requests.get(f"{api_base}/posts?per_page=1", headers=headers, timeout=10)
            use_proxy = None
        except:
            pass

    # Find the anchor post — search by title or get all future posts
    try:
        r = requests.get(
            f"{api_base}/posts",
            headers=headers,
            params={'status': 'future,publish', 'per_page': 10, 'search': topic[:30]},
            proxies=use_proxy,
            timeout=15
        )

        if r.status_code != 200:
            print(f"✗ {domain}: не удалось получить посты ({r.status_code})")
            continue

        posts = r.json()
        if not posts:
            # Try broader search
            r = requests.get(
                f"{api_base}/posts",
                headers=headers,
                params={'status': 'future,publish', 'per_page': 20},
                proxies=use_proxy,
                timeout=15
            )
            posts = r.json() if r.status_code == 200 else []

        # Find the matching post
        target_post = None
        for post in posts:
            title = post.get('title', {}).get('rendered', '')
            if any(word in title.lower() for word in topic.lower().split()[:3]):
                target_post = post
                break

        if not target_post and posts:
            # Take the earliest post as likely the anchor
            target_post = posts[0]

        if not target_post:
            print(f"✗ {domain}: пост не найден для '{topic[:40]}...'")
            continue

        post_id = target_post['id']
        old_date = target_post.get('date', '?')

        # New date
        day = schedule_dates[i % len(schedule_dates)]
        hour = hours_pool[i % len(hours_pool)]
        minute = random.randint(5, 55)
        new_date = datetime(2026, 4, day, hour, minute, 0)

        # Skip if date is in the past
        if new_date < datetime.now():
            new_date = datetime.now() + timedelta(hours=random.randint(1, 6))

        # Update post date
        update_data = {
            'date': new_date.isoformat(),
            'status': 'future'
        }

        r = requests.post(
            f"{api_base}/posts/{post_id}",
            headers=headers,
            json=update_data,
            proxies=use_proxy,
            timeout=15
        )

        if r.status_code == 200:
            print(f"✓ {domain:<25s} {old_date[:10]} → {new_date.strftime('%d.%m %H:%M')}  |  {topic[:50]}")
        else:
            print(f"✗ {domain}: ошибка обновления ({r.status_code})")

    except Exception as e:
        print(f"✗ {domain}: {str(e)[:60]}")

print("\nГотово!")
