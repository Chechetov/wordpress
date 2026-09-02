#!/usr/bin/env python3
"""Прикрепление обложек (OpenAI gpt-image-2) к опубликованным постам.

Два способа набрать список постов:

* по отчёту публикации — берёт последний reports/publish_all_*.json;
* по факту с сайта (--from-sites) — обходит опубликованные записи через
  REST и берёт те, у кого нет featured_media. Нужен для восстановленных
  статей: они пришли импортом WXR, и отчёта публикации по ним нет.

Для каждой статьи генерируется обложка, грузится в медиатеку и ставится
постом как featured_media. Посты с обложкой пропускаются — скрипт
идемпотентен, его можно гонять частями и повторять.

Каждому донору достаётся свой стиль иллюстраций (см. STYLES в
src/openai_image_generator.py): одинаковые картинки по всей сети — такой
же отпечаток, как одинаковая тема.

Использование:
    python attach_images.py                                   # последний отчёт
    python attach_images.py --from-sites \\
        --sites-file reports/recovery/restored_sites.json     # по факту с сайтов
    python attach_images.py --from-sites --only yellodigital.ru --limit 3
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


# Проверять ли сертификат. Через туннель к origin он самоподписанный.
VERIFY = True


def detect_proxy(api_base, headers, proxies):
    """Вернуть proxies, если без них API недоступен, иначе None.

    Каждую попытку проверяем отдельно: мёртвый прокси бросает исключение,
    и раньше на этом всё заканчивалось — функция возвращала тот же мёртвый
    прокси, ни разу не попробовав прямое соединение.
    """
    if proxies:
        try:
            r = requests.get(f"{api_base}/posts?per_page=1", headers=headers,
                             proxies=proxies, timeout=10, verify=VERIFY)
            if r.status_code == 200:
                return proxies
        except Exception as e:
            logger.warning(f"Прокси не отвечает ({str(e)[:80]}) — пробую напрямую")
    try:
        r = requests.get(f"{api_base}/posts?per_page=1", headers=headers,
                         timeout=10, verify=VERIFY)
        if r.status_code == 200:
            return None
    except Exception:
        pass
    return proxies or None


def auth_headers(site):
    cred = f"{site['username']}:{site['password']}"
    enc = base64.b64encode(cred.encode()).decode()
    h = {'Authorization': f'Basic {enc}', 'Content-Type': 'application/json'}
    if site.get('host'):  # ходим на origin по IP, вхост выбирается заголовком
        h['Host'] = site['host']
    return h


def category_names(api_base, headers, use_proxy):
    """id категории -> название. Нужны для осмысленного промпта."""
    names = {}
    try:
        page = 1
        while True:
            r = requests.get(f"{api_base}/categories", headers=headers,
                             params={'per_page': 100, 'page': page, '_fields': 'id,name'},
                             proxies=use_proxy, timeout=30, verify=VERIFY)
            if r.status_code != 200:
                break
            chunk = r.json()
            if not chunk:
                break
            names.update({c['id']: c['name'] for c in chunk})
            if len(chunk) < 100:
                break
            page += 1
    except Exception as e:
        logger.warning(f"Категории не прочитаны ({e}) — промпт пойдёт по заголовку")
    return names


def existing_media(api_base, headers, use_proxy):
    """id вложений, которые реально есть в медиатеке.

    Проверять featured_media на «не ноль» недостаточно: после падения сети
    у 562 постов метка осталась, а вложения из базы пропали. Такой пост
    показывает пустоту, и обложку ему всё равно надо ставить заново.
    """
    ids = set()
    page = 1
    while True:
        try:
            r = requests.get(f"{api_base}/media", headers=headers,
                             params={'per_page': 100, 'page': page, '_fields': 'id'},
                             proxies=use_proxy, timeout=60, verify=VERIFY)
        except Exception as e:
            logger.warning(f"Медиатека не прочитана ({str(e)[:80]}) — считаем её пустой")
            return ids
        if r.status_code != 200:
            break
        chunk = r.json()
        if not chunk:
            break
        ids.update(m['id'] for m in chunk)
        if len(chunk) < 100:
            break
        page += 1
    return ids


def collect_from_sites(sites, only, proxy_by_domain):
    """Обойти сайты и вернуть посты без живой обложки в формате отчёта публикации."""
    found = []
    for domain in sorted(sites):
        if only and domain not in only:
            continue
        site = sites[domain]
        headers = auth_headers(site)
        api_base = f"{site['url']}/wp-json/wp/v2"
        use_proxy = proxy_by_domain.get(domain)
        cats = category_names(api_base, headers, use_proxy)
        media_ids = existing_media(api_base, headers, use_proxy)

        page, total, without = 1, 0, 0
        while True:
            try:
                r = requests.get(f"{api_base}/posts", headers=headers,
                                 params={'per_page': 100, 'page': page, 'status': 'publish',
                                         '_fields': 'id,title,featured_media,categories'},
                                 proxies=use_proxy, timeout=60, verify=VERIFY)
            except Exception as e:
                logger.error(f"[{domain}] список постов не прочитан: {e}")
                break
            if r.status_code != 200:
                if r.status_code != 400:  # 400 = страниц больше нет
                    logger.error(f"[{domain}] список постов: HTTP {r.status_code}")
                break
            chunk = r.json()
            if not chunk:
                break
            total += len(chunk)
            for p in chunk:
                fm = p.get('featured_media', 0)
                if fm and fm in media_ids:
                    continue  # обложка на месте
                without += 1
                title = (p.get('title') or {}).get('rendered', '') or ''
                cat_ids = p.get('categories') or []
                topic = next((cats[c] for c in cat_ids if c in cats), '') or title
                found.append({'domain': domain, 'post_id': p['id'],
                              'topic': topic, 'title': title})
            if len(chunk) < 100:
                break
            page += 1
        logger.info(f"[{domain}] постов {total}, без обложки {without}")
    return found


def assign_styles(domains, override):
    """Свой стиль каждому донору: по кругу, детерминированно по имени."""
    from src.openai_image_generator import STYLES
    keys = sorted(STYLES)
    out = {}
    for i, d in enumerate(sorted(domains)):
        out[d] = override.get(d) or keys[i % len(keys)]
    return out


def main():
    parser = argparse.ArgumentParser(description='Прикрепление обложек к постам')
    parser.add_argument('--workers', type=int, default=5,
                        help='Сколько постов обрабатывать параллельно')
    parser.add_argument('--sites-file', default='campaign2_sites.json')
    parser.add_argument('--reports', nargs='+', default=None,
                        help='Один или несколько отчётов; по умолчанию — последний publish_all_*.json')
    parser.add_argument('--from-sites', action='store_true',
                        help='Брать посты без обложки прямо с сайтов, а не из отчёта')
    parser.add_argument('--only', default=None,
                        help='Домены через запятую — ограничить обработку')
    parser.add_argument('--limit', type=int, default=None,
                        help='Взять не больше N постов (для пробного прогона)')
    parser.add_argument('--style-map', default=None,
                        help='JSON {домен: стиль}; чего нет — раздаётся по кругу')
    parser.add_argument('--dry-run', action='store_true',
                        help='Показать, что будет сделано, и выйти')
    parser.add_argument('--origin', default=None,
                        help='Ходить на origin по этому адресу вместо публичного, '
                             'домен уходит заголовком Host. Снимает Cloudflare с пути: '
                             'REST сети закрыт Managed Challenge. Пример: '
                             'ssh -N -L 8443:127.0.0.1:443 root@СЕРВЕР, затем '
                             '--origin https://127.0.0.1:8443')
    args = parser.parse_args()

    global VERIFY
    if args.origin:
        VERIFY = False  # у origin самоподписанный сертификат
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    proxies = {}
    if args.origin:
        # ходим на localhost — внешний прокси тут только мешает и вешает таймауты
        logger.info('Прокси отключён: работаем напрямую с origin')
    else:
        if os.getenv('PROXY_HTTP'):
            proxies['http'] = os.getenv('PROXY_HTTP')
        if os.getenv('PROXY_HTTPS'):
            proxies['https'] = os.getenv('PROXY_HTTPS')

    sites = {s['domain']: s for s in json.load(open(args.sites_file, encoding='utf-8'))}
    if args.origin:
        for domain, site in sites.items():
            # вхост на origin выбирается заголовком Host, см. auth_headers
            site['host'] = site.get('url', '').split('//')[-1].split('/')[0] or domain
            site['url'] = args.origin.rstrip('/')
        logger.info(f"Работаем через origin {args.origin}, Cloudflare не участвует")
    only = {d.strip() for d in args.only.split(',')} if args.only else None
    if only:
        missing = only - set(sites)
        if missing:
            logger.error(f"В {args.sites_file} нет доменов: {', '.join(sorted(missing))}")
            sys.exit(1)

    # Прокси определяем один раз на домен (последовательно, до пула)
    proxy_by_domain = {}
    for domain in sorted(sites):
        if only and domain not in only:
            continue
        api_base = f"{sites[domain]['url']}/wp-json/wp/v2"
        proxy_by_domain[domain] = detect_proxy(api_base, auth_headers(sites[domain]), proxies)

    if args.from_sites:
        posts = collect_from_sites(sites, only, proxy_by_domain)
    else:
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
                    if key in seen or (only and r['domain'] not in only):
                        continue
                    seen.add(key)
                    posts.append(r)
            logger.info(f"Отчёт: {rp}")

    if args.limit:
        posts = posts[:args.limit]
    logger.info(f"Постов к обработке: {len(posts)}")
    if not posts:
        logger.info('Нечего обрабатывать: постов без обложки не найдено.')
        return

    override = json.loads(args.style_map) if args.style_map else {}
    # Раздаём по ВСЕМ доменам файла, а не по попавшим в этот прогон: иначе
    # --only сдвигает круг, и один сайт набирает разные стили за два запуска.
    styles = assign_styles(set(sites), override)
    for d in sorted({p['domain'] for p in posts}):
        logger.info(f"[{d}] стиль обложек: {styles[d]}")

    gen_by_domain = {
        d: OpenAIImageGenerator(
            api_key=os.getenv('OPENAI_API_KEY'),
            model=os.getenv('OPENAI_IMAGE_MODEL', 'gpt-image-2'),
            quality=os.getenv('IMAGE_QUALITY', 'low'),
            output_format='webp',
            style=styles[d],
        )
        for d in styles
    }

    if args.dry_run:
        print("\nРЕЖИМ ПРОСМОТРА: ничего не меняем.")
        by_domain = {}
        for p in posts:
            by_domain.setdefault(p['domain'], []).append(p)
        for d in sorted(by_domain):
            print(f"  {d:<28} постов {len(by_domain[d]):>3}  стиль: {styles[d]}")
        print(f"\nИТОГО {len(posts)} обложек, ~${len(posts) * 0.005:.2f} по gpt-image-2/low")
        return

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
            # Уже есть обложка? Метки мало — вложение должно существовать.
            g = requests.get(f"{api_base}/posts/{post_id}",
                             headers=headers, params={'_fields': 'id,featured_media'},
                             proxies=use_proxy, timeout=20, verify=VERIFY)
            if g.status_code == 200 and g.json().get('featured_media', 0) > 0:
                fm = g.json()['featured_media']
                mr = requests.get(f"{api_base}/media/{fm}", headers=headers,
                                  params={'_fields': 'id'}, proxies=use_proxy,
                                  timeout=20, verify=VERIFY)
                if mr.status_code == 200:
                    logger.info(f"[{domain}] пост {post_id}: обложка уже есть — пропуск")
                    return {'domain': domain, 'post_id': post_id, 'status': 'skipped'}
                logger.info(f"[{domain}] пост {post_id}: метка {fm} висит в пустоту — ставим заново")

            img = gen_by_domain[domain].generate_featured_image(topic=topic, article_title=title)
            if not img or not img.get('data'):
                logger.error(f"[{domain}] пост {post_id}: обложка не сгенерирована")
                return {'domain': domain, 'post_id': post_id,
                        'status': 'error', 'error': 'image generation failed'}

            ih = headers.copy()
            ih['Content-Type'] = img['content_type']
            ih['Content-Disposition'] = f'attachment; filename="cover-{post_id}.{img["ext"]}"'
            m = requests.post(f"{api_base}/media", headers=ih, data=img['data'],
                              proxies=use_proxy, timeout=90, verify=VERIFY)
            if m.status_code != 201:
                logger.error(f"[{domain}] пост {post_id}: медиа не загружено ({m.status_code})")
                return {'domain': domain, 'post_id': post_id,
                        'status': 'error', 'error': f'media upload {m.status_code}'}
            media_id = m.json()['id']

            u = requests.post(f"{api_base}/posts/{post_id}", headers=headers,
                              json={'featured_media': media_id},
                              proxies=use_proxy, timeout=30, verify=VERIFY)
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
