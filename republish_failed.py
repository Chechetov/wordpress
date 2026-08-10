#!/usr/bin/env python3
"""Допубликация статей, не прошедших в основном прогоне кампании №2.

Берёт последний отчёт reports/publish_all_*.json, находит строки со
status='error' и публикует их заново — с обложкой через fal.ai, на ту же
запланированную дату. Статус поста: publish для прошедшей даты, future
для будущей.
"""

import os
import sys
import json
import csv
import glob
import base64
import logging
import time
import requests
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

from src.content_generator import ContentGenerator
from src.openai_image_generator import OpenAIImageGenerator
from schedule_builder import pick_status


log_dir = Path('logs')
log_dir.mkdir(exist_ok=True)
log_file = log_dir / f"republish_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler(log_file, encoding='utf-8'), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


def load_plan(path='content_plan.csv'):
    plan = {}
    with open(path, encoding='utf-8') as f:
        for row in csv.DictReader(f, delimiter=';'):
            sid = int(row['Сайт'])
            plan.setdefault(sid, {'category': row['Рубрика'], 'articles': []})
            plan[sid]['articles'].append({
                'topic': row['Тема статьи'],
                'anchor': row.get('Анкор', ''),
                'url': row.get('Ссылка', ''),
                'type': row.get('Тип', ''),
            })
    return plan


def detect_proxy(api_base, headers, proxies):
    """Вернуть proxies, если без них API недоступен, иначе None."""
    try:
        r = requests.get(f"{api_base}/posts?per_page=1", headers=headers,
                          proxies=proxies, timeout=10)
        if r.status_code == 200:
            return proxies
        r = requests.get(f"{api_base}/posts?per_page=1", headers=headers, timeout=10)
        if r.status_code == 200:
            return None
    except Exception:
        pass
    return proxies


def resolve_category(api_base, headers, use_proxy, name):
    try:
        r = requests.get(f"{api_base}/categories", headers=headers,
                         params={'search': name}, proxies=use_proxy, timeout=15)
        if r.status_code == 200:
            for cat in r.json():
                if cat['name'].lower() == name.lower():
                    return cat['id']
    except Exception:
        pass
    try:
        r = requests.post(f"{api_base}/categories", headers=headers,
                          json={'name': name}, proxies=use_proxy, timeout=15)
        if r.status_code == 201:
            return r.json()['id']
    except Exception:
        pass
    return 1


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--sites-file', default='campaign2_sites.json')
    ap.add_argument('--plan', default='content_plan.csv')
    ap.add_argument('--report', default=None,
                    help='Конкретный отчёт publish_all_*.json (по умолчанию — последний)')
    args = ap.parse_args()

    proxies = {}
    if os.getenv('PROXY_HTTP'):
        proxies['http'] = os.getenv('PROXY_HTTP')
    if os.getenv('PROXY_HTTPS'):
        proxies['https'] = os.getenv('PROXY_HTTPS')

    if args.report:
        report_path = args.report
    else:
        reports = glob.glob('reports/publish_all_*.json')
        if not reports:
            logger.error('Нет отчётов publish_all_*.json')
            sys.exit(1)
        reports += glob.glob('reports/republish_*.json')
        report_path = max(reports, key=os.path.getmtime)
    report = json.load(open(report_path, encoding='utf-8'))
    errors = [r for r in report if r['status'] == 'error']
    logger.info(f"Отчёт: {report_path}")
    logger.info(f"Статей к допубликации: {len(errors)}")
    if not errors:
        logger.info('Ошибок нет — допубликация не требуется.')
        return

    sites = {s['domain']: s for s in json.load(open(args.sites_file, encoding='utf-8'))}
    plan = load_plan(args.plan)

    content_gen = ContentGenerator(api_key=os.getenv('OPENAI_API_KEY'),
                                   model=os.getenv('OPENAI_MODEL', 'gpt-5.4'))
    image_gen = OpenAIImageGenerator(
        api_key=os.getenv('OPENAI_API_KEY'),
        model=os.getenv('OPENAI_IMAGE_MODEL', 'gpt-image-2'),
        quality=os.getenv('IMAGE_QUALITY', 'low'),
    )

    results = []
    cat_cache = {}
    proxy_cache = {}

    for err in errors:
        domain = err['domain']
        topic = err['topic']
        site = sites.get(domain)
        if not site:
            logger.error(f"{domain}: нет в campaign2_sites.json — пропуск")
            results.append({'domain': domain, 'topic': topic,
                            'status': 'error', 'error': 'site not found'})
            continue

        site_plan = plan.get(site['id'])
        article = None
        if site_plan:
            for a in site_plan['articles']:
                if a['topic'] == topic:
                    article = a
                    break
        if not article:
            logger.error(f"[{domain}] статья не найдена в плане: {topic}")
            results.append({'domain': domain, 'topic': topic,
                            'status': 'error', 'error': 'article not in plan'})
            continue

        try:
            pub_time = datetime.strptime(err['scheduled'], '%Y-%m-%d %H:%M')
        except Exception:
            pub_time = datetime.now()

        cred = f"{site['username']}:{site['password']}"
        enc = base64.b64encode(cred.encode()).decode()
        headers = {'Authorization': f'Basic {enc}', 'Content-Type': 'application/json'}
        api_base = f"{site['url']}/wp-json/wp/v2"

        if domain not in proxy_cache:
            proxy_cache[domain] = detect_proxy(api_base, headers, proxies)
        use_proxy = proxy_cache[domain]

        if domain not in cat_cache:
            cat_cache[domain] = resolve_category(api_base, headers, use_proxy,
                                                 site_plan['category'])
        category_id = cat_cache[domain]

        logger.info(f"[{domain}] допубликация: {topic}")
        logger.info(f"[{domain}] дата: {pub_time:%Y-%m-%d %H:%M} ({pick_status(pub_time)})")

        try:
            content = content_gen.generate_article_content(
                topic=topic, anchor=article['anchor'], url=article['url'],
                target_words=1750)

            img = image_gen.generate_featured_image(
                topic=topic, article_title=content['title'])
            media_id = None
            if img and img.get('data'):
                ih = headers.copy()
                ih['Content-Type'] = img['content_type']
                ih['Content-Disposition'] = f'attachment; filename="cover.{img["ext"]}"'
                rr = requests.post(f"{api_base}/media", headers=ih,
                                   data=img['data'], proxies=use_proxy, timeout=60)
                if rr.status_code == 201:
                    media_id = rr.json()['id']
                    logger.info(f"[{domain}] обложка загружена: ID {media_id}")
                else:
                    logger.warning(f"[{domain}] обложка не загрузилась: {rr.status_code}")

            post_data = {
                'title': content['title'],
                'content': content['content'],
                'status': pick_status(pub_time),
                'date': pub_time.isoformat(),
                'categories': [category_id],
                'featured_media': media_id if media_id else 0,
            }
            r = requests.post(f"{api_base}/posts", headers=headers, json=post_data,
                              proxies=use_proxy, timeout=60)
            if r.status_code == 201:
                post = r.json()
                logger.info(f"[{domain}] ✓ ID={post['id']}, дата={pub_time:%Y-%m-%d %H:%M}")
                results.append({'domain': domain, 'topic': topic, 'post_id': post['id'],
                                'scheduled': pub_time.strftime('%Y-%m-%d %H:%M'),
                                'status': 'success', 'has_image': bool(media_id)})
            else:
                logger.error(f"[{domain}] ✗ {r.status_code}: {r.text[:200]}")
                results.append({'domain': domain, 'topic': topic,
                                'scheduled': pub_time.strftime('%Y-%m-%d %H:%M'),
                                'status': 'error', 'error': f"{r.status_code}: {r.text[:200]}"})
            time.sleep(3)
        except Exception as e:
            logger.error(f"[{domain}] ✗ исключение: {e}")
            results.append({'domain': domain, 'topic': topic,
                            'scheduled': pub_time.strftime('%Y-%m-%d %H:%M'),
                            'status': 'error', 'error': str(e)})

    out = Path('reports') / f"republish_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    json.dump(results, open(out, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    ok = sum(1 for r in results if r['status'] == 'success')
    with_img = sum(1 for r in results if r.get('has_image'))
    print(f"\n{'='*60}")
    print(f"ДОПУБЛИКАЦИЯ: {ok}/{len(results)} статей, с обложкой: {with_img}")
    print(f"Отчёт: {out}")
    print(f"{'='*60}")


if __name__ == '__main__':
    main()
