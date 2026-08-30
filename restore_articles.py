#!/usr/bin/env python3
"""Пишет заново потерянные статьи и собирает их в файлы импорта WordPress.

Работает по reports/recovery/restore_plan.csv. Для каждой статьи заголовок,
адрес, рубрика, дата и анкор заданы заранее — генератор пишет только текст.
Заголовок навязывается: WordPress собирает из него слаг, и свой заголовок увёл
бы статью на новый адрес, а прежний остался бы 404.

Результат — не публикация по REST, а WXR-файл на домен. Так надо по двум
причинам: REST не умеет задавать post_id, а без него не воскресить адреса вида
?p=ID; и домены сейчас не резолвятся, публиковать снаружи всё равно некуда.
Тот же штатный импортёр уже вернул 569 записей с сохранением их ID.

Прогон возобновляемый: каждая готовая статья кладётся в кеш, повторный запуск
её не перегенерирует и денег не тратит.

    python3 restore_articles.py --only drunk-fish.ru --limit 2   # проба
    python3 restore_articles.py --workers 4                      # весь план
    python3 restore_articles.py --build-only                     # только WXR
"""
import argparse
import csv
import html
import json
import logging
import os
import re
import sys
import threading
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

from dotenv import load_dotenv

load_dotenv()

from src.content_generator import ContentGenerator

PLAN = "reports/recovery/restore_plan.csv"
AUTHORS = "reports/recovery/authors.json"
CACHE = Path("articles/restore/cache")
WXR_DIR = Path("articles/restore/wxr")
RESULT = "reports/recovery/restored_urls.csv"

# На донорах стоит московское время: в февральских выгрузках post_date идёт
# на три часа впереди post_date_gmt.
TZ_OFFSET = timedelta(hours=3)

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("restore")

CYR = {
    'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'jo',
    'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'j', 'к': 'k', 'л': 'l', 'м': 'm',
    'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
    'ф': 'f', 'х': 'h', 'ц': 'c', 'ч': 'ch', 'ш': 'sh', 'щ': 'shh', 'ъ': '',
    'ы': 'y', 'ь': '', 'э': 'je', 'ю': 'ju', 'я': 'ja',
}


def slugify(text):
    out = ''.join(CYR.get(ch, ch) for ch in text.lower())
    return re.sub(r'-+', '-', re.sub(r'[^a-z0-9]+', '-', out)).strip('-')


def cdata(text):
    """CDATA рвётся на последовательности ]]> — разбиваем её пополам."""
    return "<![CDATA[" + str(text).replace("]]>", "]]]]><![CDATA[>") + "]]>"


def cache_path(row):
    return CACHE / f"{row['Домен ASCII']}_{row['ID']}.json"


def generate_one(row, generator, target_words):
    """Пишет одну статью. Возвращает словарь с заголовком, слагом и текстом."""
    path = cache_path(row)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))

    anchor = row["Анкор"].strip()
    link = row["Целевая ссылка"].strip()
    fixed_title = row["Заголовок"].strip() or None
    topic = row["Тема"].strip() or fixed_title or row["Слаг"]

    # Без анкора ссылку вставлять нечем: пустой url превратился бы в <a href="">
    result = generator.generate_article_content(
        topic=topic,
        anchor=anchor if (anchor and link) else "",
        url=link if (anchor and link) else "",
        target_words=target_words,
        title=fixed_title,
    )

    title = result["title"].strip()
    slug = row["Слаг"].strip() or slugify(title)
    if row["Слаг"].strip() and slugify(title) != row["Слаг"].strip():
        # Заголовок навязан, значит слаг обязан из него собираться. Если нет —
        # генератор подменил заголовок, и статья уедет на чужой адрес.
        logger.warning("%s id=%s: заголовок разошёлся со слагом (%s != %s)",
                       row["Домен"], row["ID"], slugify(title), row["Слаг"])

    out = {
        "domain": row["Домен"], "domain_ascii": row["Домен ASCII"],
        "post_id": int(row["ID"]), "title": title, "slug": slug,
        "category": row["Рубрика"], "category_slug": row["Слаг рубрики"],
        "date": row["Дата"], "anchor": anchor, "link": link,
        "money": row["Денежная"] == "да",
        "content": result["content"], "words": result.get("word_count", 0),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    return out


def build_wxr(domain_ascii, domain, articles, author):
    """Собирает WXR по одному домену."""
    site = f"https://{domain}"
    cats = {}
    for a in articles:
        cats[a["category_slug"]] = a["category"]

    parts = ['<?xml version="1.0" encoding="UTF-8" ?>',
             '<!-- Восстановление статей, утраченных при потере серверов -->',
             '<rss version="2.0"',
             '\txmlns:excerpt="http://wordpress.org/export/1.2/excerpt/"',
             '\txmlns:content="http://purl.org/rss/1.0/modules/content/"',
             '\txmlns:wfw="http://wellformedweb.org/CommentAPI/"',
             '\txmlns:dc="http://purl.org/dc/elements/1.1/"',
             '\txmlns:wp="http://wordpress.org/export/1.2/"',
             '>', '', '<channel>',
             f'\t<title>{html.escape(domain)}</title>',
             f'\t<link>{site}</link>',
             '\t<description></description>',
             '\t<language>ru-RU</language>',
             '\t<wp:wxr_version>1.2</wp:wxr_version>',
             f'\t<wp:base_site_url>{site}</wp:base_site_url>',
             f'\t<wp:base_blog_url>{site}</wp:base_blog_url>',
             f'\t<wp:author><wp:author_id>1</wp:author_id>'
             f'<wp:author_login>{cdata(author["login"])}</wp:author_login>'
             f'<wp:author_email>{cdata(author["email"])}</wp:author_email>'
             f'<wp:author_display_name>{cdata(author["login"])}</wp:author_display_name>'
             f'<wp:author_first_name>{cdata("")}</wp:author_first_name>'
             f'<wp:author_last_name>{cdata("")}</wp:author_last_name></wp:author>']

    for slug, name in sorted(cats.items()):
        parts.append(f'\t<wp:category><wp:term_id>0</wp:term_id>'
                     f'<wp:category_nicename>{cdata(slug)}</wp:category_nicename>'
                     f'<wp:category_parent>{cdata("")}</wp:category_parent>'
                     f'<wp:cat_name>{cdata(name)}</wp:cat_name></wp:category>')

    for a in sorted(articles, key=lambda x: x["post_id"]):
        local = datetime.strptime(a["date"][:16], "%Y-%m-%d %H:%M")
        gmt = local - TZ_OFFSET
        url = f'{site}/{a["category_slug"]}/{a["slug"]}/'
        parts += [
            '\t<item>',
            f'\t\t<title>{cdata(a["title"])}</title>',
            f'\t\t<link>{html.escape(url)}</link>',
            f'\t\t<pubDate>{gmt.strftime("%a, %d %b %Y %H:%M:%S +0000")}</pubDate>',
            f'\t\t<dc:creator>{cdata(author["login"])}</dc:creator>',
            f'\t\t<guid isPermaLink="false">{site}/?p={a["post_id"]}</guid>',
            '\t\t<description></description>',
            f'\t\t<content:encoded>{cdata(a["content"])}</content:encoded>',
            f'\t\t<excerpt:encoded>{cdata("")}</excerpt:encoded>',
            f'\t\t<wp:post_id>{a["post_id"]}</wp:post_id>',
            f'\t\t<wp:post_date>{cdata(local.strftime("%Y-%m-%d %H:%M:%S"))}</wp:post_date>',
            f'\t\t<wp:post_date_gmt>{cdata(gmt.strftime("%Y-%m-%d %H:%M:%S"))}</wp:post_date_gmt>',
            f'\t\t<wp:post_modified>{cdata(local.strftime("%Y-%m-%d %H:%M:%S"))}</wp:post_modified>',
            f'\t\t<wp:post_modified_gmt>{cdata(gmt.strftime("%Y-%m-%d %H:%M:%S"))}</wp:post_modified_gmt>',
            f'\t\t<wp:comment_status>{cdata("closed")}</wp:comment_status>',
            f'\t\t<wp:ping_status>{cdata("closed")}</wp:ping_status>',
            f'\t\t<wp:post_name>{cdata(a["slug"])}</wp:post_name>',
            f'\t\t<wp:status>{cdata("publish")}</wp:status>',
            '\t\t<wp:post_parent>0</wp:post_parent>',
            '\t\t<wp:menu_order>0</wp:menu_order>',
            f'\t\t<wp:post_type>{cdata("post")}</wp:post_type>',
            f'\t\t<wp:post_password>{cdata("")}</wp:post_password>',
            '\t\t<wp:is_sticky>0</wp:is_sticky>',
            f'\t\t<category domain="category" nicename="{html.escape(a["category_slug"])}">'
            f'{cdata(a["category"])}</category>',
            '\t</item>',
        ]

    parts += ['</channel>', '</rss>', '']
    WXR_DIR.mkdir(parents=True, exist_ok=True)
    out = WXR_DIR / f"{domain_ascii}.wxr.xml"
    out.write_text('\n'.join(parts), encoding="utf-8")
    return out


def main():
    ap = argparse.ArgumentParser(description="Восстановление утраченных статей")
    ap.add_argument("--plan", default=PLAN)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--words", type=int, default=1750)
    ap.add_argument("--only", default=None, help="домены через запятую")
    ap.add_argument("--limit", type=int, default=None, help="сколько статей всего")
    ap.add_argument("--build-only", action="store_true",
                    help="не генерировать, только собрать WXR из кеша")
    args = ap.parse_args()

    rows = list(csv.DictReader(open(args.plan, encoding="utf-8-sig")))
    if args.only:
        want = {d.strip() for d in args.only.split(",")}
        rows = [r for r in rows if r["Домен"] in want or r["Домен ASCII"] in want]
    if not rows:
        sys.exit("под фильтр ничего не попало")

    # Денежные первыми: если прогон прервётся, важное уже будет готово
    rows.sort(key=lambda r: (r["Денежная"] != "да", r["Домен"], int(r["ID"])))
    if args.limit:
        rows = rows[:args.limit]

    authors = json.load(open(AUTHORS, encoding="utf-8"))

    if not args.build_only:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            sys.exit("нет OPENAI_API_KEY в .env")
        generator = ContentGenerator(api_key=api_key)

        todo = [r for r in rows if not cache_path(r).exists()]
        logger.info("статей в работе: %d, уже готовы: %d",
                    len(todo), len(rows) - len(todo))

        done = failed = 0
        lock = threading.Lock()
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {pool.submit(generate_one, r, generator, args.words): r
                       for r in todo}
            for fut in as_completed(futures):
                row = futures[fut]
                try:
                    art = fut.result()
                    with lock:
                        done += 1
                    logger.info("[%d/%d] %s id=%s %s (%d слов)", done, len(todo),
                                row["Домен"], row["ID"],
                                "ДЕНЕЖНАЯ" if art["money"] else "траст",
                                art["words"])
                except Exception as exc:
                    with lock:
                        failed += 1
                    logger.error("%s id=%s: не написалась — %s",
                                 row["Домен"], row["ID"], exc)
        logger.info("написано: %d, не вышло: %d", done, failed)

    # --- сборка WXR из кеша
    by_domain = defaultdict(list)
    missing = 0
    for row in rows:
        path = cache_path(row)
        if not path.exists():
            missing += 1
            continue
        by_domain[(row["Домен ASCII"], row["Домен"])].append(
            json.loads(path.read_text(encoding="utf-8")))

    if missing:
        logger.warning("без текста осталось %d статей — в WXR они не попадут",
                       missing)

    result_rows = []
    for (ascii_d, domain), articles in sorted(by_domain.items()):
        author = authors.get(ascii_d) or authors.get(domain)
        if not author:
            logger.error("%s: не знаю автора, пропускаю", domain)
            continue
        out = build_wxr(ascii_d, domain, articles, author)
        logger.info("%s: %d статей -> %s", domain, len(articles), out)
        for a in sorted(articles, key=lambda x: x["post_id"]):
            result_rows.append({
                "Домен": domain, "ID": a["post_id"],
                "URL": f'https://{domain}/{a["category_slug"]}/{a["slug"]}/',
                "Заголовок": a["title"], "Дата": a["date"],
                "Денежная": "да" if a["money"] else "",
                "Анкор": a["anchor"], "Целевая ссылка": a["link"],
            })

    if result_rows:
        with open(RESULT, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=list(result_rows[0].keys()))
            w.writeheader()
            w.writerows(result_rows)
        logger.info("итоговые адреса: %s (%d)", RESULT, len(result_rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
