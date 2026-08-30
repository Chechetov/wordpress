#!/usr/bin/env python3
"""Восстановление постов из WXR-выгрузки через WP REST API.

Штатный импорт WordPress требует WP-CLI или плагина, то есть доступа к серверу.
Этот скрипт делает то же самое поверх REST — тем же путём, которым работает
publish_all.py: создаёт рубрики, публикует записи с исходными заголовком, телом,
слагом и датой.

Вложения пропускаются намеренно: в выгрузке лежат только ссылки на картинки,
самих файлов нет, а старые домены за Cloudflare отдают 403. Обложки ставятся
отдельно через attach_images.py.

Идемпотентность: перед публикацией проверяется, нет ли уже записи с таким слагом.
Повторный запуск дополняет недостающее, а не плодит дубли.

Использование:
    python3 import_wxr.py --sites-file reports/recovery/c2_sites.json --dry-run
    python3 import_wxr.py --sites-file reports/recovery/c2_sites.json --backups backups/wxr-2026-02
    python3 import_wxr.py --sites-file sites.json --only promplo.ru --limit 5
"""
import argparse
import json
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime

import requests
from requests.auth import HTTPBasicAuth

NS = {
    "wp": "http://wordpress.org/export/1.2/",
    "content": "http://purl.org/rss/1.0/modules/content/",
    "excerpt": "http://wordpress.org/export/1.2/excerpt/",
}

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"}


def text_of(node, path, default=""):
    found = node.find(path, NS)
    return found.text if found is not None and found.text else default


def parse_wxr(path):
    """Достаёт из выгрузки опубликованные записи с рубриками."""
    tree = ET.parse(path)
    root = tree.getroot()
    channel = root.find("channel")
    base = text_of(channel, "wp:base_site_url") or text_of(channel, "link")

    posts = []
    for item in channel.findall("item"):
        if text_of(item, "wp:post_type") != "post":
            continue
        if text_of(item, "wp:status") != "publish":
            continue
        cats = [c.text for c in item.findall("category")
                if c.get("domain") == "category" and c.text]
        posts.append({
            "title": (item.findtext("title") or "").strip(),
            "slug": text_of(item, "wp:post_name"),
            "date": text_of(item, "wp:post_date"),
            "content": text_of(item, "content:encoded"),
            "excerpt": text_of(item, "excerpt:encoded"),
            "categories": cats,
        })
    posts.sort(key=lambda p: p["date"])
    return base, posts


def rewrite_links(html, old_host, new_host):
    """Меняет абсолютные ссылки со старого домена на новый."""
    if not old_host or old_host == new_host:
        return html
    old = re.escape(old_host)
    html = re.sub(rf"https?://(?:www\.)?{old}", f"https://{new_host}", html)
    return html


class WP:
    def __init__(self, site, timeout=90, proxies=None):
        self.auth = HTTPBasicAuth(site["username"], site["password"])
        self.timeout = timeout
        self.proxies = proxies
        self._cats = None
        self.base = self._pick_base(site["url"].rstrip("/"))

    def _pick_base(self, root):
        """Выбирает рабочий вход в REST.

        На части доноров nginx закрывает путь /wp-json и отвечает 403 сам, без
        WordPress. Штатный запасной вход «?rest_route=» при этом работает, и
        различить это можно только пробой.
        """
        candidates = [root + "/wp-json/wp/v2", root + "/?rest_route=/wp/v2"]
        for base in candidates:
            try:
                r = requests.get(base + "/posts", auth=self.auth, headers=UA,
                                 proxies=self.proxies, timeout=self.timeout,
                                 params={"per_page": 1})
                if r.status_code == 200:
                    return base
            except requests.RequestException:
                pass
        return candidates[0]

    def _req(self, method, path, **kw):
        for attempt in range(3):
            try:
                r = requests.request(method, self.base + path, auth=self.auth, headers=UA,
                                     proxies=self.proxies, timeout=self.timeout, **kw)
                if r.status_code == 429:
                    time.sleep(3 * (attempt + 1))
                    continue
                return r
            except requests.RequestException:
                if attempt == 2:
                    raise
                time.sleep(2 * (attempt + 1))
        return None

    def categories(self):
        if self._cats is None:
            self._cats = {}
            page = 1
            while True:
                r = self._req("GET", "/categories", params={"per_page": 100, "page": page})
                if not r or r.status_code != 200:
                    break
                batch = r.json()
                for c in batch:
                    self._cats[c["name"].strip().lower()] = c["id"]
                if len(batch) < 100:
                    break
                page += 1
        return self._cats

    def ensure_category(self, name):
        key = name.strip().lower()
        cats = self.categories()
        if key in cats:
            return cats[key]
        r = self._req("POST", "/categories", json={"name": name})
        if r is not None and r.status_code in (200, 201):
            cid = r.json()["id"]
            cats[key] = cid
            return cid
        # гонка: рубрику мог создать параллельный процесс
        if r is not None and r.status_code == 400:
            existing = (r.json().get("data") or {}).get("term_id")
            if existing:
                cats[key] = existing
                return existing
        return None

    def slug_exists(self, slug):
        r = self._req("GET", "/posts", params={"slug": slug, "status": "publish,draft,future"})
        if r is None or r.status_code != 200:
            return False
        return bool(r.json())

    def create_post(self, payload):
        return self._req("POST", "/posts", json=payload)


def main():
    p = argparse.ArgumentParser(description="Импорт постов из WXR через WP REST")
    p.add_argument("--sites-file", required=True, help="JSON с сайтами (домен, url, логин, пароль)")
    p.add_argument("--backups", default="backups/wxr-2026-02", help="каталог с <домен>.wxr.xml")
    p.add_argument("--only", default=None, help="только эти домены через запятую")
    p.add_argument("--limit", type=int, default=None, help="не больше N записей на сайт")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--proxy", nargs="?", const="env", default=None,
                   help="'--proxy' берёт PROXY_* из .env, либо укажите URL")
    p.add_argument("--pause", type=float, default=1.0, help="пауза между записями, сек")
    args = p.parse_args()

    proxies = None
    if args.proxy == "env":
        try:
            from dotenv import load_dotenv
            load_dotenv()
        except ImportError:
            pass
        proxies = {k: v for k, v in (("http", os.getenv("PROXY_HTTP")),
                                     ("https", os.getenv("PROXY_HTTPS"))) if v}
    elif args.proxy:
        proxies = {"http": args.proxy, "https": args.proxy}

    sites = json.load(open(args.sites_file, encoding="utf-8"))
    if args.only:
        wanted = {d.strip() for d in args.only.split(",")}
        sites = [s for s in sites if s["domain"] in wanted]
    if not sites:
        sys.exit("Подходящих сайтов не нашлось")

    def to_ascii(d):
        try:
            return d.encode("idna").decode()
        except Exception:
            return d

    total_new = total_skip = total_fail = 0
    report = []

    for site in sites:
        domain = site["domain"]
        path = os.path.join(args.backups, f"{to_ascii(domain)}.wxr.xml")
        if not os.path.exists(path):
            print(f"[{domain}] выгрузки нет: {path}")
            continue

        base, posts = parse_wxr(path)
        old_host = re.sub(r"^https?://", "", base).strip("/")
        if args.limit:
            posts = posts[:args.limit]
        print(f"\n=== {domain}: в выгрузке {len(posts)} опубликованных записей "
              f"(исходный хост {old_host}) ===")

        if args.dry_run:
            for post in posts[:5]:
                print(f"    {post['date'][:10]}  {post['title'][:64]}  "
                      f"[{', '.join(post['categories']) or 'без рубрики'}]  "
                      f"{len(post['content'])} симв.")
            if len(posts) > 5:
                print(f"    … и ещё {len(posts) - 5}")
            report.append({"domain": domain, "planned": len(posts)})
            continue

        wp = WP(site, proxies=proxies)
        new = skip = fail = 0
        for post in posts:
            if post["slug"] and wp.slug_exists(post["slug"]):
                skip += 1
                continue
            cat_ids = [cid for cid in (wp.ensure_category(c) for c in post["categories"]) if cid]
            payload = {
                "title": post["title"],
                "content": rewrite_links(post["content"], old_host, to_ascii(domain)),
                "status": "publish",
                "date": post["date"].replace(" ", "T") if post["date"] else None,
            }
            if post["slug"]:
                payload["slug"] = post["slug"]
            if post["excerpt"]:
                payload["excerpt"] = post["excerpt"]
            if cat_ids:
                payload["categories"] = cat_ids
            payload = {k: v for k, v in payload.items() if v is not None}

            try:
                r = wp.create_post(payload)
            except Exception as exc:
                print(f"    ОШИБКА {post['slug'][:40]}: {type(exc).__name__}")
                fail += 1
                continue
            if r is not None and r.status_code in (200, 201):
                new += 1
                print(f"    + {post['date'][:10]} {post['title'][:60]}")
            else:
                fail += 1
                code = r.status_code if r is not None else "нет ответа"
                body = (r.text[:120] if r is not None else "")
                print(f"    ОШИБКА {code} {post['title'][:40]}: {body}")
            time.sleep(args.pause)

        print(f"  итог {domain}: добавлено {new}, пропущено {skip}, ошибок {fail}")
        total_new += new
        total_skip += skip
        total_fail += fail
        report.append({"domain": domain, "added": new, "skipped": skip, "failed": fail})

    print(f"\nВСЕГО: добавлено {total_new}, пропущено (уже были) {total_skip}, ошибок {total_fail}")
    if not args.dry_run and report:
        os.makedirs("reports", exist_ok=True)
        out = f"reports/import_wxr_{datetime.now():%Y%m%d_%H%M%S}.json"
        json.dump(report, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"Отчёт: {out}")


if __name__ == "__main__":
    main()
