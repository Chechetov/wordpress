#!/usr/bin/env python3
"""Допубликация пропущенных статей + замена cover-grouping.ru"""

import os
import json
import csv
import base64
import logging
import time
import requests
import random
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

from src.content_generator import ContentGenerator
from src.openai_image_generator import OpenAIImageGenerator


logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler(f"logs/publish_missing_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log", encoding='utf-8'),
              logging.StreamHandler()])
logger = logging.getLogger(__name__)

# Load sites
with open('sites.json', 'r') as f:
    all_sites = {s['id']: s for s in json.load(f)}

# Load content plan
plan = {}
with open('content_plan.csv', 'r', encoding='utf-8') as f:
    for row in csv.DictReader(f, delimiter=';'):
        sid = int(row['Сайт'])
        if sid not in plan:
            plan[sid] = {'category': row['Рубрика'], 'articles': []}
        plan[sid]['articles'].append({
            'topic': row['Тема статьи'], 'anchor': row.get('Анкор', ''),
            'url': row.get('Ссылка', ''), 'type': row.get('Тип', '')
        })

# Missing articles: site_id -> list of 0-based article indices
missing = {
    5:  [0],        # sibertek.ru:     статья 1 (анкор!)
    9:  [2],        # studio-santech:  статья 3
    7:  [2, 3],     # vsenamag.ru:     статьи 3, 4
    8:  [0, 3],     # oybox.by:        статьи 1 (анкор!), 4
    10: [0, 1, 3],  # photoset-msk.ru: статьи 1 (анкор!), 2, 4
    3:  [0, 1, 2, 3, 4, 5],  # 2semechki.ru: все 6 (замена cover-grouping.ru)
}

proxies = {}
if os.getenv('PROXY_HTTP'):
    proxies['http'] = os.getenv('PROXY_HTTP')
if os.getenv('PROXY_HTTPS'):
    proxies['https'] = os.getenv('PROXY_HTTPS')

content_gen = ContentGenerator(api_key=os.getenv('OPENAI_API_KEY'), model='gpt-5.2')
image_gen = OpenAIImageGenerator(
    api_key=os.getenv('OPENAI_API_KEY'),
    model=os.getenv('OPENAI_IMAGE_MODEL', 'gpt-image-2'),
    quality=os.getenv('IMAGE_QUALITY', 'low'),
)

results = []

for site_id, article_indices in missing.items():
    site = all_sites[site_id]
    domain = site['domain']
    logger.info(f"{'='*50}")
    logger.info(f"Сайт #{site_id}: {domain} — допубликация {len(article_indices)} статей")

    cred = f"{site['username']}:{site['password']}"
    enc = base64.b64encode(cred.encode()).decode()
    headers = {'Authorization': f'Basic {enc}', 'Content-Type': 'application/json'}
    api_base = f"{site['url']}/wp-json/wp/v2"

    # Detect proxy need
    use_proxy = proxies
    try:
        r = requests.get(f"{api_base}/categories", headers=headers, proxies=proxies, timeout=10)
        if r.status_code != 200:
            r = requests.get(f"{api_base}/categories", headers=headers, timeout=10)
            if r.status_code == 200:
                use_proxy = None
    except:
        try:
            requests.get(f"{api_base}/categories", headers=headers, timeout=10)
            use_proxy = None
        except:
            pass

    category_name = plan[site_id]['category']
    category_id = None

    # Get or create category
    try:
        r = requests.get(f"{api_base}/categories", headers=headers,
                         params={'search': category_name}, proxies=use_proxy, timeout=15)
        if r.status_code == 200:
            for cat in r.json():
                if cat['name'].lower() == category_name.lower():
                    category_id = cat['id']
                    break
    except:
        pass

    if category_id is None:
        try:
            r = requests.post(f"{api_base}/categories", headers=headers,
                              json={'name': category_name}, proxies=use_proxy, timeout=15)
            if r.status_code == 201:
                category_id = r.json()['id']
            else:
                category_id = 1
        except:
            category_id = 1

    for idx in article_indices:
        article = plan[site_id]['articles'][idx]
        topic = article['topic']
        anchor = article.get('anchor', '')
        link_url = article.get('url', '')

        # Schedule time: spread across next days
        hours_offset = random.randint(2, 12) + idx * random.randint(36, 48)
        pub_time = datetime.now() + timedelta(hours=hours_offset)
        pub_time = pub_time.replace(hour=random.randint(8, 20), minute=random.randint(5, 55), second=0)

        logger.info(f"[{domain}] Статья {idx+1}/6: {topic}")
        logger.info(f"[{domain}] Дата: {pub_time.strftime('%Y-%m-%d %H:%M')}")

        try:
            # Generate content
            content = content_gen.generate_article_content(
                topic=topic, anchor=anchor, url=link_url, target_words=1750)

            # Generate image
            img = image_gen.generate_featured_image(topic=topic, article_title=content['title'])

            # Upload image
            media_id = None
            if img and img.get('data'):
                img_h = headers.copy()
                img_h['Content-Type'] = 'image/webp'
                img_h['Content-Disposition'] = f'attachment; filename="article_{idx+1}.webp"'
                r = requests.post(f"{api_base}/media", headers=img_h,
                                  data=img['data'], proxies=use_proxy, timeout=60)
                if r.status_code == 201:
                    media_id = r.json()['id']

            # Publish
            post_data = {
                'title': content['title'], 'content': content['content'],
                'status': 'future', 'date': pub_time.isoformat(),
                'categories': [category_id],
                'featured_media': media_id if media_id else 0
            }
            r = requests.post(f"{api_base}/posts", headers=headers,
                              json=post_data, proxies=use_proxy, timeout=60)

            if r.status_code == 201:
                post = r.json()
                logger.info(f"[{domain}] ✓ ID={post['id']}, дата={pub_time.strftime('%Y-%m-%d %H:%M')}")
                results.append({'domain': domain, 'status': 'success', 'post_id': post['id']})
            else:
                logger.error(f"[{domain}] ✗ {r.status_code}: {r.text[:200]}")
                results.append({'domain': domain, 'status': 'error'})

            time.sleep(3)
        except Exception as e:
            logger.error(f"[{domain}] ✗ {str(e)}")
            results.append({'domain': domain, 'status': 'error'})

success = sum(1 for r in results if r['status'] == 'success')
print(f"\nИТОГО: {success}/{len(results)} допубликовано")
