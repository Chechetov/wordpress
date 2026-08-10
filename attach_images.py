#!/usr/bin/env python3
"""Прикрепление обложек (fal.ai nano-banana) к опубликованным постам.

Берёт последний отчёт reports/publish_all_*.json, для каждой успешно
опубликованной статьи генерирует обложку через fal.ai, загружает её в
медиатеку сайта и проставляет посту featured_media. Посты, у которых
обложка уже есть, пропускаются — скрипт идемпотентен.

Использование:
    python attach_images.py                # все посты последнего отчёта
    python attach_images.py --workers 8    # больше параллелизма
"""

import os
import sys
import json
import glob
import base64
import logging
import argparse
import requests
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv

load_dotenv()

from src.openai_image_generator import OpenAIImageGenerator


log_dir = Path('logs')
log_dir.mkdir(exist_ok=True)
log_file = log_dir / f"attach_images_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler(log_file, encoding='utf-8'), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


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


def main():
    parser = argparse.ArgumentParser(description='Прикрепление обложек к постам')
    parser.add_argument('--workers', type=int, default=5,
                        help='Сколько постов обрабатывать параллельно')
    parser.add_argument('--sites-file', default='campaign2_sites.json')
    parser.add_argument('--reports', nargs='+', default=None,
                        help='Один или несколько отчётов; по умолчанию — последний publish_all_*.json')
    args = parser.parse_args()

    proxies = {}
    if os.getenv('PROXY_HTTP'):
        proxies['http'] = os.getenv('PROXY_HTTP')
    if os.getenv('PROXY_HTTPS'):
        proxies['https'] = os.getenv('PROXY_HTTPS')

    if args.reports:
        report_paths = args.reports
    else:
        reports = glob.glob('reports/publish_all_*.json')
        if not reports:
            logger.error('Нет отчётов publish_all_*.json')
            sys.exit(1)
        report_paths = [max(reports, key=os.path.getmtime)]

    posts = []
    seen = set()
    for rp in report_paths:
        data = json.load(open(rp, encoding='utf-8'))
        for r in data:
            if r['status'] == 'success' and r.get('post_id'):
                key = (r['domain'], r['post_id'])
                if key in seen:
                    continue
                seen.add(key)
                posts.append(r)
        logger.info(f"Отчёт: {rp}")
    logger.info(f"Постов к обработке: {len(posts)}")
    if not posts:
        logger.info('Нет опубликованных постов.')
        return

    sites = {s['domain']: s for s in json.load(open(args.sites_file, encoding='utf-8'))}
    image_gen = OpenAIImageGenerator(
        api_key=os.getenv('OPENAI_API_KEY'),
        model=os.getenv('OPENAI_IMAGE_MODEL', 'gpt-image-2'),
        quality=os.getenv('IMAGE_QUALITY', 'low'),
    )

    def auth_headers(site):
        cred = f"{site['username']}:{site['password']}"
        enc = base64.b64encode(cred.encode()).decode()
        return {'Authorization': f'Basic {enc}', 'Content-Type': 'application/json'}

    # Прокси определяем один раз на домен (последовательно, до пула)
    proxy_by_domain = {}
    for domain in sorted({p['domain'] for p in posts}):
        site = sites.get(domain)
        if not site:
            continue
        api_base = f"{site['url']}/wp-json/wp/v2"
        proxy_by_domain[domain] = detect_proxy(api_base, auth_headers(site), proxies)

    def process(post):
        domain = post['domain']
        post_id = post['post_id']
        topic = post.get('topic', '')
        title = post.get('title', topic)
        site = sites.get(domain)
        if not site:
            return {'domain': domain, 'post_id': post_id,
                    'status': 'error', 'error': 'site not found'}

        headers = auth_headers(site)
        api_base = f"{site['url']}/wp-json/wp/v2"
        use_proxy = proxy_by_domain.get(domain)

        try:
            # Уже есть обложка? — пропустить
            g = requests.get(f"{api_base}/posts/{post_id}",
                             headers=headers, params={'_fields': 'id,featured_media'},
                             proxies=use_proxy, timeout=20)
            if g.status_code == 200 and g.json().get('featured_media', 0) > 0:
                logger.info(f"[{domain}] пост {post_id}: обложка уже есть — пропуск")
                return {'domain': domain, 'post_id': post_id, 'status': 'skipped'}

            img = image_gen.generate_featured_image(topic=topic, article_title=title)
            if not img or not img.get('data'):
                logger.error(f"[{domain}] пост {post_id}: обложка не сгенерирована")
                return {'domain': domain, 'post_id': post_id,
                        'status': 'error', 'error': 'image generation failed'}

            ih = headers.copy()
            ih['Content-Type'] = img['content_type']
            ih['Content-Disposition'] = f'attachment; filename="cover-{post_id}.{img["ext"]}"'
            m = requests.post(f"{api_base}/media", headers=ih, data=img['data'],
                              proxies=use_proxy, timeout=90)
            if m.status_code != 201:
                logger.error(f"[{domain}] пост {post_id}: медиа не загружено ({m.status_code})")
                return {'domain': domain, 'post_id': post_id,
                        'status': 'error', 'error': f'media upload {m.status_code}'}
            media_id = m.json()['id']

            u = requests.post(f"{api_base}/posts/{post_id}", headers=headers,
                              json={'featured_media': media_id},
                              proxies=use_proxy, timeout=30)
            if u.status_code == 200:
                logger.info(f"[{domain}] пост {post_id}: обложка прикреплена (media {media_id})")
                return {'domain': domain, 'post_id': post_id,
                        'status': 'success', 'media_id': media_id}
            logger.error(f"[{domain}] пост {post_id}: featured_media не проставлен ({u.status_code})")
            return {'domain': domain, 'post_id': post_id,
                    'status': 'error', 'error': f'post update {u.status_code}'}

        except Exception as e:
            logger.error(f"[{domain}] пост {post_id}: исключение {e}")
            return {'domain': domain, 'post_id': post_id,
                    'status': 'error', 'error': str(e)}

    logger.info(f"Параллельная обработка: {len(posts)} постов, {args.workers} потоков")
    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = [executor.submit(process, p) for p in posts]
        for future in as_completed(futures):
            results.append(future.result())

    out = Path('reports') / f"attach_images_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    json.dump(results, open(out, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    ok = sum(1 for r in results if r['status'] == 'success')
    skip = sum(1 for r in results if r['status'] == 'skipped')
    err = sum(1 for r in results if r['status'] == 'error')
    print(f"\n{'='*60}")
    print(f"ОБЛОЖКИ: прикреплено {ok}, пропущено {skip}, ошибок {err} (всего {len(results)})")
    print(f"Отчёт: {out}")
    print(f"{'='*60}")


if __name__ == '__main__':
    main()
