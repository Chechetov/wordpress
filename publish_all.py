#!/usr/bin/env python3
"""
Мультисайтовая публикация статей с отложенным расписанием.

Использование:
    python publish_all.py                   # Публикация на все сайты
    python publish_all.py --site 1          # Только сайт #1
    python publish_all.py --site 1,2,3      # Несколько сайтов
    python publish_all.py --dry-run         # Без публикации, только показать план
    python publish_all.py --schedule-only   # Показать расписание без генерации
"""

import os
import sys
import json
import csv
import logging
import time
import base64
import html
import requests
import argparse
import random
from datetime import datetime, timedelta
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv

load_dotenv()

# Logging
log_dir = Path("logs")
log_dir.mkdir(exist_ok=True)
log_file = log_dir / f"publish_all_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Импорт модулей
from src.content_generator import ContentGenerator
from src.image_generator import ImageGenerator
from src.fal_image_generator import FalImageGenerator
from src.openai_image_generator import OpenAIImageGenerator
from schedule_builder import build_schedule, pick_status


def load_sites(path="sites.json"):
    """Загрузка конфигурации сайтов"""
    with open(path, 'r', encoding='utf-8') as f:
        sites = json.load(f)
    return [s for s in sites if not s.get('disabled')]


def load_content_plan(path: str = "content_plan.csv"):
    """Загрузка контент-плана"""
    plan = {}
    with open(path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f, delimiter=';')
        for row in reader:
            site_id = int(row['Сайт'])
            if site_id not in plan:
                plan[site_id] = {
                    'category': row['Рубрика'],
                    'articles': []
                }
            plan[site_id]['articles'].append({
                'topic': row['Тема статьи'],
                'anchor': row.get('Анкор', ''),
                'url': row.get('Ссылка', ''),
                'type': row.get('Тип', '')
            })
    return plan


# build_schedule и pick_status импортируются из schedule_builder


def find_post_by_title(api_base, headers, use_proxy, title, attempts=3):
    """ID поста с точно таким заголовком либо None.

    Нужна после обрыва соединения на POST: пост мог создаться, а ответ — нет.
    """
    for attempt in range(attempts):
        try:
            r = requests.get(f"{api_base}/posts", headers=headers, proxies=use_proxy,
                             params={'search': title[:60], 'per_page': 20,
                                     'status': 'publish,future,draft',
                                     '_fields': 'id,title'},
                             timeout=60)
            if r.status_code == 200:
                for post in r.json():
                    rendered = html.unescape(post.get('title', {}).get('rendered', '')).strip()
                    if rendered == title.strip():
                        return post['id']
                return None
        except Exception:
            pass
        time.sleep(5 * (attempt + 1))
    return None


def publish_to_site(site_config, articles, schedule, content_gen, image_gen, dry_run=False):
    """Публикация статей на один сайт"""
    domain = site_config['domain']
    url = site_config['url']
    username = site_config['username']
    password = site_config['password']

    # Прокси
    proxies = {}
    if os.getenv('PROXY_HTTP'):
        proxies['http'] = os.getenv('PROXY_HTTP')
    if os.getenv('PROXY_HTTPS'):
        proxies['https'] = os.getenv('PROXY_HTTPS')

    # Auth headers
    cred = f"{username}:{password}"
    encoded = base64.b64encode(cred.encode()).decode()
    headers = {
        'Authorization': f'Basic {encoded}',
        'Content-Type': 'application/json'
    }

    api_base = f"{url}/wp-json/wp/v2"
    results = []

    # Определяем, нужен ли прокси для этого сайта.
    # Прокси — вариант по умолчанию: часть доноров за Cloudflare и прямые
    # запросы к ним получают «Just a moment...» (403). Уходим на прямое
    # соединение ТОЛЬКО если оно реально вернуло 200: requests не бросает
    # исключение на 4xx, и раньше 403-заставка засчитывалась за успех.
    def _probe(px):
        try:
            r = requests.get(f"{api_base}/posts", headers=headers,
                             proxies=px, timeout=30)
            return r.status_code == 200
        except Exception:
            return False

    use_proxy = proxies
    if not _probe(proxies) and _probe(None):
        use_proxy = None
        logger.info(f"[{domain}] прокси недоступен, работаем напрямую")

    category = articles['category']
    category_id = None

    for i, (article_data, pub_time) in enumerate(zip(articles['articles'], schedule)):
        article_num = i + 1
        topic = article_data['topic']
        anchor = article_data.get('anchor', '')
        link_url = article_data.get('url', '')

        logger.info(f"[{domain}] Статья {article_num}/6: {topic}")
        logger.info(f"[{domain}] Запланирована на: {pub_time.strftime('%Y-%m-%d %H:%M')}")

        if dry_run:
            results.append({
                'domain': domain, 'article': article_num, 'topic': topic,
                'scheduled': pub_time.strftime('%Y-%m-%d %H:%M'), 'status': 'dry-run'
            })
            continue

        try:
            # 1. Генерация контента
            logger.info(f"[{domain}] Генерация текста...")
            content = content_gen.generate_article_content(
                topic=topic,
                anchor=anchor if anchor else '',
                url=link_url if link_url else '',
                target_words=1750
            )

            # 2. Генерация изображения
            logger.info(f"[{domain}] Генерация изображения...")
            img = image_gen.generate_featured_image(topic=topic, article_title=content['title'])

            # 3. Получение/создание категории (один раз)
            if category_id is None:
                # Поиск существующей
                try:
                    r = requests.get(f"{api_base}/categories", headers=headers,
                                     params={'search': category}, proxies=use_proxy, timeout=30)
                    if r.status_code == 200:
                        for cat in r.json():
                            if cat['name'].lower() == category.lower():
                                category_id = cat['id']
                                break
                except:
                    pass

                # Создание новой
                if category_id is None:
                    try:
                        r = requests.post(f"{api_base}/categories", headers=headers,
                                          json={'name': category}, proxies=use_proxy, timeout=30)
                        if r.status_code == 201:
                            category_id = r.json()['id']
                        else:
                            category_id = 1  # Без рубрики
                    except:
                        category_id = 1

                logger.info(f"[{domain}] Категория '{category}' ID: {category_id}")

            # 4. Загрузка изображения
            media_id = None
            if img and img.get('data'):
                ctype = img.get('content_type', 'image/webp')
                ext = img.get('ext', 'webp')
                img_headers = headers.copy()
                img_headers['Content-Type'] = ctype
                img_headers['Content-Disposition'] = f'attachment; filename="article_{article_num}.{ext}"'
                try:
                    r = requests.post(f"{api_base}/media", headers=img_headers,
                                      data=img['data'], proxies=use_proxy, timeout=90)
                    if r.status_code == 201:
                        media_id = r.json()['id']
                        logger.info(f"[{domain}] Изображение загружено: ID {media_id}")
                except Exception as e:
                    logger.warning(f"[{domain}] Ошибка загрузки изображения: {e}")

            # 5. Публикация с отложенной датой
            post_data = {
                'title': content['title'],
                'content': content['content'],
                'status': pick_status(pub_time),
                'date': pub_time.isoformat(),
                'categories': [category_id],
                'featured_media': media_id if media_id else 0
            }

            try:
                r = requests.post(f"{api_base}/posts", headers=headers,
                                  json=post_data, proxies=use_proxy, timeout=120)
            except Exception as post_err:
                # Прокси рвёт крупные POST (~20 КБ тела): пост на сайте создаётся,
                # а ответ до нас не доходит. Проверяем по заголовку, прежде чем
                # считать это ошибкой — иначе при повторе получим дубль.
                logger.warning(f"[{domain}] соединение оборвалось ({post_err}), "
                               f"проверяю, создался ли пост")
                time.sleep(5)
                found = find_post_by_title(api_base, headers, use_proxy, content['title'])
                if found:
                    logger.info(f"[{domain}] ✓ Статья запланирована: ID={found}, "
                                f"дата={pub_time.strftime('%Y-%m-%d %H:%M')} "
                                f"(подтверждено проверкой после обрыва)")
                    results.append({
                        'domain': domain, 'article': article_num, 'topic': topic,
                        'post_id': found, 'scheduled': pub_time.strftime('%Y-%m-%d %H:%M'),
                        'status': 'success', 'title': content['title']
                    })
                    time.sleep(3)
                    continue
                raise

            if r.status_code == 201:
                post = r.json()
                logger.info(f"[{domain}] ✓ Статья запланирована: ID={post['id']}, "
                            f"дата={pub_time.strftime('%Y-%m-%d %H:%M')}")
                results.append({
                    'domain': domain, 'article': article_num, 'topic': topic,
                    'post_id': post['id'], 'scheduled': pub_time.strftime('%Y-%m-%d %H:%M'),
                    'status': 'success', 'title': content['title']
                })
            else:
                logger.error(f"[{domain}] ✗ Ошибка публикации: {r.status_code} - {r.text[:200]}")
                results.append({
                    'domain': domain, 'article': article_num, 'topic': topic,
                    'scheduled': pub_time.strftime('%Y-%m-%d %H:%M'),
                    'status': 'error', 'error': r.text[:200]
                })

            # Пауза между статьями (не нагружать API)
            time.sleep(3)

        except Exception as e:
            logger.error(f"[{domain}] ✗ Исключение: {str(e)}")
            results.append({
                'domain': domain, 'article': article_num, 'topic': topic,
                'scheduled': pub_time.strftime('%Y-%m-%d %H:%M'),
                'status': 'error', 'error': str(e)
            })

    return results


def main():
    parser = argparse.ArgumentParser(description='Мультисайтовая публикация статей')
    parser.add_argument('--sites-file', default='sites.json', help='JSON-файл с сайтами')
    parser.add_argument('--plan', default='content_plan.csv',
                        help='CSV контент-плана (по умолчанию content_plan.csv)')
    parser.add_argument('--site', type=str, help='ID сайтов через запятую (1,2,3)')
    parser.add_argument('--dry-run', action='store_true', help='Только показать план')
    parser.add_argument('--schedule-only', action='store_true', help='Показать расписание')
    parser.add_argument('--workers', type=int, default=5,
                        help='Сколько сайтов обрабатывать параллельно')
    parser.add_argument('--start-date', type=str, default=None,
                        help='Точка отсчёта YYYY-MM-DD (по умолчанию REF_DATE)')
    parser.add_argument('--site-step', type=str, default=None,
                        help='Диапазон сдвига между сайтами, например 0-1')
    parser.add_argument('--article-step', type=str, default=None,
                        help='Диапазон между статьями внутри сайта, например 2-3')
    parser.add_argument('--image-backend', choices=['openai', 'fal', 'google'], default='openai',
                        help='Бэкенд генерации обложек (по умолчанию openai gpt-image-2; '
                             'google — нет квоты, fal — платный баланс)')
    parser.add_argument('--image-quality', choices=['low', 'medium', 'high'], default='low',
                        help='Качество обложки для openai-бэкенда (low ~$0.005/шт)')
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("Мультисайтовая публикация статей")
    logger.info("=" * 60)

    # Загрузка данных
    sites = load_sites(args.sites_file)
    plan = load_content_plan(args.plan)

    # Фильтр по сайтам
    if args.site:
        site_ids = [int(x) for x in args.site.split(',')]
        sites = [s for s in sites if s['id'] in site_ids]

    logger.info(f"Сайтов: {len(sites)}")
    logger.info(f"Рубрик в плане: {len(plan)}")

    # Параметры расписания
    sched_kwargs = {}
    if args.start_date:
        sched_kwargs['start_date'] = datetime.strptime(args.start_date, '%Y-%m-%d')
    if args.site_step:
        lo, hi = args.site_step.split('-')
        sched_kwargs['site_step'] = (int(lo), int(hi))
    if args.article_step:
        lo, hi = args.article_step.split('-')
        sched_kwargs['article_step'] = (int(lo), int(hi))

    # Генерация расписания.
    # Дат на сайт — по самому «длинному» сайту плана: zip ниже обрежет лишние.
    # Иначе у сайта с двойным анкором (7 статей) последняя статья молча терялась.
    max_articles = max(len(p['articles']) for p in plan.values())
    schedules = build_schedule(len(sites), articles_per_site=max_articles, **sched_kwargs)

    # Показать расписание
    if args.schedule_only or args.dry_run:
        print("\n📅 РАСПИСАНИЕ ПУБЛИКАЦИЙ\n")
        for idx, site in enumerate(sites):
            site_id = site['id']
            if site_id not in plan:
                continue
            site_plan = plan[site_id]
            site_schedule = schedules[idx]
            print(f"{'='*60}")
            print(f"Сайт #{site_id}: {site['domain']} | Рубрика: {site_plan['category']}")
            print(f"{'='*60}")
            for j, (article, pub_time) in enumerate(zip(site_plan['articles'], site_schedule)):
                type_mark = ''
                if article.get('type') == 'анкор клиента':
                    type_mark = ' [АНКОР]'
                elif article.get('type') == 'траст':
                    type_mark = ' [траст]'
                mark = 'задним числом' if pick_status(pub_time) == 'publish' else 'отложенная'
                print(f"  {j+1}. {pub_time.strftime('%d.%m.%Y %H:%M')} [{mark}] — {article['topic']}{type_mark}")
            print()

        if args.schedule_only:
            return

    if args.dry_run:
        print("\n[DRY RUN] Публикация не выполнялась.\n")
        return

    # Инициализация генераторов
    content_gen = ContentGenerator(
        api_key=os.getenv('OPENAI_API_KEY'),
        model=os.getenv('OPENAI_MODEL', 'gpt-5.4')
    )
    if args.image_backend == 'openai':
        image_gen = OpenAIImageGenerator(
            api_key=os.getenv('OPENAI_API_KEY'),
            model=os.getenv('OPENAI_IMAGE_MODEL', 'gpt-image-2'),
            quality=args.image_quality,
        )
    elif args.image_backend == 'fal':
        image_gen = FalImageGenerator(
            api_key=os.getenv('FAL_KEY'),
            model=os.getenv('FAL_IMAGE_MODEL', 'fal-ai/nano-banana'),
        )
    else:
        image_gen = ImageGenerator(
            api_key=os.getenv('GOOGLE_API_KEY'),
            model=os.getenv('IMAGEN_MODEL', 'gemini-3.1-flash-image-preview'),
        )

    # Публикация — параллельно по сайтам
    jobs = []
    for idx, site in enumerate(sites):
        if site['id'] not in plan:
            logger.warning(f"Нет плана для сайта #{site['id']} ({site['domain']})")
            continue
        jobs.append((idx, site))

    logger.info(f"Параллельная публикация: {len(jobs)} сайтов, "
                f"{args.workers} потоков")

    all_results = []
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(publish_to_site, site, plan[site['id']],
                            schedules[idx], content_gen, image_gen,
                            args.dry_run): site['domain']
            for idx, site in jobs
        }
        for future in as_completed(futures):
            domain = futures[future]
            try:
                all_results.extend(future.result())
                logger.info(f"[{domain}] сайт завершён")
            except Exception as e:
                logger.error(f"[{domain}] сбой обработки сайта: {e}")

    # Сохранение отчёта
    report_dir = Path("reports")
    report_dir.mkdir(exist_ok=True)
    report_file = report_dir / f"publish_all_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)

    # Итоги
    success = sum(1 for r in all_results if r['status'] == 'success')
    errors = sum(1 for r in all_results if r['status'] == 'error')
    total = len(all_results)

    print(f"\n{'='*60}")
    print(f"ИТОГО: {success}/{total} статей запланировано, {errors} ошибок")
    print(f"Отчёт: {report_file}")
    print(f"Лог: {log_file}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
