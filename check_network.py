#!/usr/bin/env python3
"""Проверка живости всей PBN-сетки: DNS, HTTP, WP REST, количество и дата постов.

Использование:
    python3 check_network.py                      # прямые запросы
    python3 check_network.py --proxy              # через PROXY_HTTP/PROXY_HTTPS из .env
    python3 check_network.py --proxy socks5://user:pass@host:port
    python3 check_network.py --workers 8 --out reports/network_health.csv

Важно: доноры стоят за Cloudflare с включённым челленджем — прямые запросы
получают 403 «Just a moment...» независимо от того, жив сайт или нет.
Осмысленный результат даёт только рабочий прокси с доверенным IP.
"""
import argparse
import csv
import json
import os
import socket
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import requests
from requests.auth import HTTPBasicAuth

SITE_FILES = ["sites.json", "campaign2_sites.json", "campaign3_sites.json", "campaign4_sites.json"]

UA = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9",
}

CF_IP_PREFIXES = ("104.16.", "104.17.", "104.18.", "104.19.", "104.20.", "104.21.", "104.22.",
                  "104.24.", "104.26.", "162.159.", "172.64.", "172.65.", "172.66.", "172.67.",
                  "172.68.", "172.69.", "188.114.", "198.41.")


def load_donors():
    """Объединяет доноров из всех файлов кампаний (домен -> учётка + список кампаний)."""
    donors = {}
    for path in SITE_FILES:
        if not os.path.exists(path):
            continue
        campaign = path.replace("_sites.json", "").replace("sites.json", "campaign1")
        for site in json.load(open(path, encoding="utf-8")):
            entry = donors.setdefault(site["domain"].lower(), {
                "domain": site["domain"].lower(),
                "url": site["url"].rstrip("/"),
                "username": site["username"],
                "password": site["password"],
                "campaigns": [],
            })
            entry["campaigns"].append(campaign)
    return sorted(donors.values(), key=lambda d: d["domain"])


def to_ascii(domain):
    try:
        return domain.encode("idna").decode()
    except Exception:
        return domain


def classify(row):
    """Ставит диагноз по собранным сигналам."""
    if not row["ip"]:
        return "МЁРТВ: домен не резолвится"
    if row["api_status"] == 200:
        return "ЖИВ"
    if isinstance(row["home_status"], int) and row["home_status"] in (521, 522, 523, 525, 526):
        return f"ORIGIN УПАЛ (CF {row['home_status']})"
    if row["home_status"] == 403 and "just a moment" in row["home_snippet"].lower():
        return "НЕИЗВЕСТНО: Cloudflare-челлендж (нужен доверенный прокси)"
    if row["api_status"] in (401, 403):
        return "САЙТ ОТВЕЧАЕТ, но REST не авторизует (пароль приложения слетел)"
    if isinstance(row["home_status"], int) and 200 <= row["home_status"] < 400:
        return "САЙТ ОТВЕЧАЕТ, WP REST недоступен"
    return f"ПРОБЛЕМА: home={row['home_status']} api={row['api_status']}"


def check(site, proxies, timeout):
    ascii_domain = to_ascii(site["domain"])
    row = {
        "domain": site["domain"],
        "campaigns": "+".join(site["campaigns"]),
        "ip": "",
        "behind_cf": "",
        "home_status": "",
        "home_snippet": "",
        "api_status": "",
        "posts_total": "",
        "latest_post": "",
        "verdict": "",
    }
    try:
        row["ip"] = socket.gethostbyname(ascii_domain)
        row["behind_cf"] = "да" if row["ip"].startswith(CF_IP_PREFIXES) else "нет"
    except Exception:
        pass

    try:
        resp = requests.get(site["url"] + "/", headers=UA, proxies=proxies,
                            timeout=timeout, allow_redirects=True)
        row["home_status"] = resp.status_code
        row["home_snippet"] = " ".join(resp.text[:400].split())[:160]
    except Exception as exc:
        row["home_status"] = f"ERR:{type(exc).__name__}"

    try:
        resp = requests.get(site["url"] + "/wp-json/wp/v2/posts",
                            params={"per_page": 1, "orderby": "date", "order": "desc"},
                            auth=HTTPBasicAuth(site["username"], site["password"]),
                            headers=UA, proxies=proxies, timeout=timeout)
        row["api_status"] = resp.status_code
        if resp.status_code == 200:
            row["posts_total"] = resp.headers.get("X-WP-Total", "")
            try:
                posts = resp.json()
                if posts:
                    row["latest_post"] = posts[0].get("date", "")[:10]
            except ValueError:
                pass
    except Exception as exc:
        row["api_status"] = f"ERR:{type(exc).__name__}"

    row["verdict"] = classify(row)
    return row


def main():
    parser = argparse.ArgumentParser(description="Проверка живости PBN-сетки")
    parser.add_argument("--proxy", nargs="?", const="env", default=None,
                        help="'--proxy' берёт PROXY_HTTP/PROXY_HTTPS из .env, "
                             "или укажите URL прокси явно")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--timeout", type=int, default=45)
    parser.add_argument("--out", default=None, help="куда писать CSV")
    args = parser.parse_args()

    proxies = None
    if args.proxy == "env":
        try:
            from dotenv import load_dotenv
            load_dotenv()
        except ImportError:
            pass
        proxies = {}
        if os.getenv("PROXY_HTTP"):
            proxies["http"] = os.getenv("PROXY_HTTP")
        if os.getenv("PROXY_HTTPS"):
            proxies["https"] = os.getenv("PROXY_HTTPS")
        if not proxies:
            sys.exit("В .env нет PROXY_HTTP/PROXY_HTTPS")
    elif args.proxy:
        proxies = {"http": args.proxy, "https": args.proxy}

    donors = load_donors()
    print(f"Доноров к проверке: {len(donors)}; прокси: {'да' if proxies else 'нет'}\n")

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        rows = list(pool.map(lambda s: check(s, proxies, args.timeout), donors))

    print(f"{'ДОМЕН':28} {'HOME':8} {'API':6} {'ПОСТОВ':7} {'ПОСЛЕДНИЙ':11} ДИАГНОЗ")
    for row in rows:
        print(f"{row['domain'][:27]:28} {str(row['home_status'])[:7]:8} "
              f"{str(row['api_status'])[:5]:6} {str(row['posts_total']):7} "
              f"{str(row['latest_post']):11} {row['verdict']}")

    alive = [r for r in rows if r["verdict"] == "ЖИВ"]
    dead = [r for r in rows if r["verdict"].startswith(("МЁРТВ", "ORIGIN"))]
    unknown = [r for r in rows if r["verdict"].startswith("НЕИЗВЕСТНО")]
    print(f"\nИТОГО: живых {len(alive)}, упавших {len(dead)}, "
          f"неопределимых {len(unknown)}, прочих {len(rows) - len(alive) - len(dead) - len(unknown)}")
    if dead:
        print("Упавшие: " + ", ".join(r["domain"] for r in dead))

    out = args.out or f"reports/network_health_{datetime.now():%Y%m%d_%H%M%S}.csv"
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nОтчёт: {out}")


if __name__ == "__main__":
    main()
