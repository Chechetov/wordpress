#!/usr/bin/env python3
"""Заводит зоны в Cloudflare и направляет домены на сервер.

Для каждого домена: создаёт зону, ставит проксируемые A-записи @ и www,
включает SSL-режим Full и оставляет ботозащиту выключенной. Возвращает пару
неймсерверов, которую надо прописать у регистратора.

Идемпотентен: существующие зоны и записи не дублирует, а обновляет.

Токен берётся из .env (CLOUDFLARE_API_TOKEN) или из --token.
Нужные права: Account → Zone:Edit, Zone → DNS:Edit, Zone → Zone Settings:Edit.

Использование:
    python3 cloudflare_setup.py --ip 1.2.3.4 --dry-run
    python3 cloudflare_setup.py --ip 1.2.3.4 --domains-from reports/recovery
    python3 cloudflare_setup.py --ip 1.2.3.4 --domains promplo.ru,elintel.ru
"""
import argparse
import csv
import glob
import json
import os
import sys
import time

import requests

API = "https://api.cloudflare.com/client/v4"

# 20 упавших доноров — цель восстановления
DEFAULT_DOMAINS = [
    "drunk-fish.ru", "kgdink.ru", "mai-hoshi.ru", "omegabay.ru", "prforce.ru",
    "property-in-alanya.ru", "speciallabel.ru", "techfile.ru", "top-audit.ru",
    "unit-org.ru", "2semechki.ru", "avtogear62.ru", "promplo.ru", "kakudobrit.ru",
    "ledpnz.ru", "elintel.ru", "pro-covers.ru", "yellodigital.ru",
    "доступныйсервис.рф", "стандарт72.рф",
]


def to_ascii(domain):
    try:
        return domain.encode("idna").decode()
    except Exception:
        return domain


class Cloudflare:
    def __init__(self, token, dry_run=False):
        self.s = requests.Session()
        self.s.headers.update({"Authorization": f"Bearer {token}",
                               "Content-Type": "application/json"})
        self.dry_run = dry_run

    def call(self, method, path, **kw):
        if self.dry_run and method != "GET":
            return {"success": True, "result": {"_dry_run": True}, "errors": []}
        for attempt in range(4):
            r = self.s.request(method, API + path, timeout=45, **kw)
            if r.status_code == 429:            # rate limit — подождать и повторить
                time.sleep(3 * (attempt + 1))
                continue
            try:
                return r.json()
            except ValueError:
                return {"success": False, "errors": [{"message": f"HTTP {r.status_code}"}]}
        return {"success": False, "errors": [{"message": "rate limited"}]}

    def account_id(self):
        d = self.call("GET", "/accounts?per_page=50")
        if not d.get("success") or not d.get("result"):
            raise SystemExit(f"Не удалось получить аккаунт: {errors(d)}")
        accounts = d["result"]
        if len(accounts) > 1:
            print("Аккаунтов несколько, беру первый:")
            for a in accounts:
                print(f"   {a['id']}  {a['name']}")
        return accounts[0]["id"], accounts[0]["name"]

    def find_zone(self, name):
        d = self.call("GET", f"/zones?name={name}")
        res = d.get("result") or []
        return res[0] if res else None

    def create_zone(self, name, account_id):
        return self.call("POST", "/zones", data=json.dumps(
            {"name": name, "account": {"id": account_id}, "type": "full"}))

    def dns_records(self, zone_id, name):
        d = self.call("GET", f"/zones/{zone_id}/dns_records?type=A&name={name}")
        return d.get("result") or []

    def upsert_a(self, zone_id, name, ip):
        existing = self.dns_records(zone_id, name)
        body = json.dumps({"type": "A", "name": name, "content": ip,
                           "ttl": 1, "proxied": True})
        if existing:
            return self.call("PUT", f"/zones/{zone_id}/dns_records/{existing[0]['id']}",
                             data=body), "обновлена"
        return self.call("POST", f"/zones/{zone_id}/dns_records", data=body), "создана"

    def set_ssl_full(self, zone_id):
        # Flexible недопустим: с мёртвым или чужим origin он даёт петлю редиректов
        return self.call("PATCH", f"/zones/{zone_id}/settings/ssl",
                         data=json.dumps({"value": "full"}))

    def disable_bot_fight(self, zone_id):
        # Ботозащита челленджит и поисковиков, и наш /wp-json — держим выключенной
        return self.call("POST", f"/zones/{zone_id}/bot_management",
                         data=json.dumps({"fight_mode": False}))


def errors(d):
    return "; ".join(e.get("message", "?") for e in (d.get("errors") or [])) or "неизвестно"


def load_domains(args):
    if args.domains:
        return [d.strip() for d in args.domains.split(",") if d.strip()]
    if args.domains_from:
        found = []
        for path in sorted(glob.glob(os.path.join(args.domains_from, "*_sites.json"))):
            for site in json.load(open(path, encoding="utf-8")):
                if site["domain"] not in found:
                    found.append(site["domain"])
        if found:
            return found
        sys.exit(f"В {args.domains_from} не нашлось *_sites.json")
    return list(DEFAULT_DOMAINS)


def main():
    p = argparse.ArgumentParser(description="Настройка зон Cloudflare для восстановления сетки")
    p.add_argument("--ip", required=True, help="IP сервера, куда указывают A-записи")
    p.add_argument("--token", default=None, help="API-токен (иначе CLOUDFLARE_API_TOKEN из .env)")
    p.add_argument("--domains", default=None, help="список доменов через запятую")
    p.add_argument("--domains-from", default=None, help="каталог с *_sites.json")
    p.add_argument("--dry-run", action="store_true", help="ничего не менять, только показать")
    p.add_argument("--out", default="reports/cloudflare_ns.csv")
    args = p.parse_args()

    token = args.token
    if not token:
        try:
            from dotenv import load_dotenv
            load_dotenv()
        except ImportError:
            pass
        token = os.getenv("CLOUDFLARE_API_TOKEN")
    if not token:
        sys.exit("Нет токена: добавьте CLOUDFLARE_API_TOKEN в .env или передайте --token")

    cf = Cloudflare(token, dry_run=args.dry_run)
    acc_id, acc_name = cf.account_id()
    domains = load_domains(args)

    print(f"Аккаунт: {acc_name} ({acc_id})")
    print(f"Доменов: {len(domains)} | цель: {args.ip}"
          f"{' | РЕЖИМ ПРОСМОТРА, изменений не будет' if args.dry_run else ''}\n")

    rows = []
    for i, domain in enumerate(domains, 1):
        name = to_ascii(domain)
        print(f"[{i}/{len(domains)}] {domain}")

        zone = cf.find_zone(name)
        if zone:
            zone_id, ns, status = zone["id"], zone.get("name_servers") or [], zone.get("status")
            print(f"    зона уже есть (статус {status})")
        else:
            d = cf.create_zone(name, acc_id)
            if not d.get("success"):
                print(f"    ОШИБКА создания зоны: {errors(d)}")
                rows.append({"Домен": domain, "NS1": "", "NS2": "", "Статус": f"ошибка: {errors(d)}"})
                continue
            res = d["result"]
            zone_id = res.get("id", "dry-run")
            ns = res.get("name_servers") or []
            status = res.get("status", "pending")
            print(f"    зона создана (статус {status})")

        if not args.dry_run and zone_id != "dry-run":
            for rec in (name, f"www.{name}"):
                d, what = cf.upsert_a(zone_id, rec, args.ip)
                print(f"    A {rec} -> {args.ip} ({what})" if d.get("success")
                      else f"    ОШИБКА записи {rec}: {errors(d)}")
            d = cf.set_ssl_full(zone_id)
            print("    SSL: Full" if d.get("success") else f"    SSL не выставлен: {errors(d)}")
            d = cf.disable_bot_fight(zone_id)
            if not d.get("success"):
                print(f"    ботозащита: проверьте вручную ({errors(d)})")

        rows.append({"Домен": domain,
                     "NS1": ns[0] if len(ns) > 0 else "",
                     "NS2": ns[1] if len(ns) > 1 else "",
                     "Статус": status})

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["Домен", "NS1", "NS2", "Статус"])
        w.writeheader()
        w.writerows(rows)

    print(f"\nНеймсерверы для регистраторов: {args.out}")
    print("Дальше: прописать эти NS у регистратора (14 доменов в первой панели, 6 в REG.RU).")
    print("Зона станет Active сама, как только делегирование обновится.")


if __name__ == "__main__":
    main()
