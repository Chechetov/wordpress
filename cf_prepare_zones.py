#!/usr/bin/env python3
"""Приводит зоны Cloudflare в состояние, пригодное для переезда сайтов.

Меняет ровно две вещи и обе — обязательные:

  ssl = full             Cloudflare ходит на origin по HTTPS. Режим flexible
                         вместе с https в siteurl даёт бесконечный редирект —
                         ровно тот, что положил прежние доноры.
  always_use_https = on  http-адрес отвечает 301 на https прямо на границе,
                         не доходя до сайта.

Остальное только показывает, не трогая: уровень безопасности и проверка
браузера выставлены осознанно, они отсекают чужие краулеры, а проверенных
Googlebot и YandexBot Cloudflare пропускает мимо них. А вот Bot Fight Mode
поисковых роботов как раз задевает — если он включён, скрипт об этом кричит.

    python3 cf_prepare_zones.py --dry-run
    python3 cf_prepare_zones.py
    python3 cf_prepare_zones.py --account CF2
"""
import argparse
import os
import sys

import requests

API = "https://api.cloudflare.com/client/v4"
WANT = {"ssl": "full", "always_use_https": "on"}
SHOW = ("security_level", "browser_check", "automatic_https_rewrites")


def token_for(slot):
    token = os.getenv(f"CLOUDFLARE_TOKEN_{slot}")
    if not token and slot == "CF1":
        token = os.getenv("CLOUDFLARE_API_TOKEN")
    return token


def errors(payload):
    return "; ".join(e.get("message", "?") for e in (payload.get("errors") or [])) \
        or "неизвестно"


def main():
    ap = argparse.ArgumentParser(description="Настройка зон Cloudflare под переезд")
    ap.add_argument("--account", default="CF1", help="слот токена: CF1, CF2, …")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    token = token_for(args.account)
    if not token:
        sys.exit(f"нет токена для {args.account} в .env")

    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {token}",
                      "Content-Type": "application/json"})

    zones = s.get(f"{API}/zones?per_page=100", timeout=45).json()
    if not zones.get("success"):
        sys.exit(f"аккаунт не читается: {errors(zones)}")
    zones = sorted(zones["result"], key=lambda z: z["name"])
    print(f"Зон в аккаунте {args.account}: {len(zones)}"
          f"{'  РЕЖИМ ПРОСМОТРА' if args.dry_run else ''}\n")

    changed = warned = 0
    for zone in zones:
        zid, name = zone["id"], zone["name"]
        line = []
        for key, want in WANT.items():
            cur = s.get(f"{API}/zones/{zid}/settings/{key}", timeout=30).json()
            value = (cur.get("result") or {}).get("value")
            if value == want:
                line.append(f"{key}={value}")
            elif args.dry_run:
                line.append(f"{key}: {value} -> {want} (не менял)")
            else:
                res = s.patch(f"{API}/zones/{zid}/settings/{key}",
                              json={"value": want}, timeout=30).json()
                if res.get("success"):
                    line.append(f"{key}: {value} -> {want}")
                    changed += 1
                else:
                    line.append(f"{key}: НЕ выставлен ({errors(res)})")

        extra = []
        for key in SHOW:
            cur = s.get(f"{API}/zones/{zid}/settings/{key}", timeout=30).json()
            extra.append(f"{key}={(cur.get('result') or {}).get('value')}")

        bots = s.get(f"{API}/zones/{zid}/bot_management", timeout=30).json()
        result = bots.get("result") or {}
        if result.get("fight_mode") or result.get("crawler_protection") == "enabled":
            warned += 1
            extra.append("ВНИМАНИЕ: включена защита от ботов, "
                         "она задевает поисковых роботов")

        print(f"  {name:34} {zone['status']:14} {', '.join(line)}")
        print(f"  {'':34} {'':14} {', '.join(extra)}")

    print(f"\nизменено настроек: {changed}"
          f"{f', зон с риском для краулеров: {warned}' if warned else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
