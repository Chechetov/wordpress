#!/usr/bin/env python3
"""Раскладывает домены по нескольким аккаунтам Cloudflare.

Зачем: пара неймсерверов выдаётся Cloudflare на аккаунт, а не на зону. Все зоны
одного аккаунта получают одинаковые NS, и домены связываются между собой
напрямую через DNS. Развести их можно только разными аккаунтами.

Скрипт берёт раскладку из CSV, заводит зоны там, где они должны быть, ставит
проксируемые A-записи и SSL Full, а получившиеся пары NS пишет обратно в тот же
CSV — оттуда их и прописывают у регистратора.

Аккаунты скрипт НЕ создаёт: регистрация руками, см. reports/infra/README.md.
От каждого аккаунта нужен только API-токен с правами
Zone:Edit + DNS:Edit + Zone Settings:Edit. Токены лежат в .env:

    CLOUDFLARE_TOKEN_CF1=...
    CLOUDFLARE_TOKEN_CF2=...

Использование:
    python3 cf_distribute.py --ip 157.228.135.19 --dry-run
    python3 cf_distribute.py --ip 157.228.135.19
    python3 cf_distribute.py --ip 157.228.135.19 --only CF-2,CF-3
"""
import argparse
import csv
import os
import re
import sys
import time

import requests

API = "https://api.cloudflare.com/client/v4"
SPLIT = "reports/recovery/cf_accounts_split.csv"


def to_ascii(domain):
    try:
        return domain.encode("idna").decode()
    except Exception:
        return domain


def slot_of(account_label):
    """«CF-3 (новый)» -> «CF3», чтобы найти CLOUDFLARE_TOKEN_CF3 в .env."""
    m = re.search(r"CF-?(\d+)", account_label)
    return f"CF{m.group(1)}" if m else None


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
            if r.status_code == 429:
                time.sleep(3 * (attempt + 1))
                continue
            try:
                return r.json()
            except ValueError:
                return {"success": False, "errors": [{"message": f"HTTP {r.status_code}"}]}
        return {"success": False, "errors": [{"message": "rate limited"}]}

    def account_id(self):
        d = self.call("GET", "/accounts?per_page=50")
        res = d.get("result") or []
        if not res:
            raise SystemExit(f"аккаунт не читается: {errors(d)}")
        return res[0]["id"], res[0]["name"]

    def find_zone(self, name):
        res = self.call("GET", f"/zones?name={name}").get("result") or []
        return res[0] if res else None

    def create_zone(self, name, account_id):
        return self.call("POST", "/zones", json={"name": name,
                                                 "account": {"id": account_id},
                                                 "type": "full"})

    def delete_zone(self, zone_id):
        return self.call("DELETE", f"/zones/{zone_id}")

    def upsert_a(self, zone_id, name, ip):
        existing = self.call("GET", f"/zones/{zone_id}/dns_records?type=A&name={name}")
        body = {"type": "A", "name": name, "content": ip, "ttl": 1, "proxied": True}
        rec = (existing.get("result") or [])
        if rec:
            return self.call("PUT", f"/zones/{zone_id}/dns_records/{rec[0]['id']}", json=body)
        return self.call("POST", f"/zones/{zone_id}/dns_records", json=body)

    def set_ssl_full(self, zone_id):
        # Flexible нельзя: Cloudflare пойдёт на origin по HTTP, WordPress с
        # https в siteurl ответит редиректом — и это бесконечная петля,
        # ровно та, что положила прежние доноры.
        return self.call("PATCH", f"/zones/{zone_id}/settings/ssl",
                         json={"value": "full"})


def errors(d):
    return "; ".join(e.get("message", "?") for e in (d.get("errors") or [])) or "неизвестно"


def sniff_delimiter(path):
    """Файлы реестра ведутся руками, разделитель бывает и «,» и «;»."""
    with open(path, encoding="utf-8-sig") as f:
        head = f.readline()
    return ";" if head.count(";") > head.count(",") else ","


def load_split(path):
    delim = sniff_delimiter(path)
    with open(path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f, delimiter=delim)), delim


def main():
    p = argparse.ArgumentParser(description="Раскладка доменов по аккаунтам Cloudflare")
    p.add_argument("--ip", required=True, help="IP сервера для A-записей")
    p.add_argument("--split", default=SPLIT, help="CSV с раскладкой")
    p.add_argument("--only", default=None, help="только эти аккаунты, через запятую")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    rows, delim = load_split(args.split)
    by_account = {}
    for r in rows:
        by_account.setdefault(r["Аккаунт Cloudflare"], []).append(r)

    if args.only:
        want = {w.strip() for w in args.only.split(",")}
        by_account = {k: v for k, v in by_account.items()
                      if any(w in k for w in want)}

    if not by_account:
        sys.exit("под фильтр ничего не попало")

    print(f"Аккаунтов: {len(by_account)} | доменов: {sum(len(v) for v in by_account.values())}"
          f"{' | РЕЖИМ ПРОСМОТРА' if args.dry_run else ''}\n")

    missing = []
    for label in by_account:
        slot = slot_of(label)
        if not slot or not os.getenv(f"CLOUDFLARE_TOKEN_{slot}"):
            missing.append(f"{label} -> CLOUDFLARE_TOKEN_{slot or '??'}")
    if missing:
        print("Нет токенов, эти аккаунты пропущу:")
        for m in missing:
            print(f"   {m}")
        print()

    for label, items in by_account.items():
        slot = slot_of(label)
        token = os.getenv(f"CLOUDFLARE_TOKEN_{slot}") if slot else None
        if not token:
            continue

        cf = Cloudflare(token, dry_run=args.dry_run)
        acc_id, acc_name = cf.account_id()
        print(f"=== {label}  ->  {acc_name} ({acc_id})")

        for row in items:
            domain = row["Домен"]
            name = to_ascii(domain)
            zone = cf.find_zone(name)

            if zone and zone.get("account", {}).get("id") not in (acc_id, None):
                # Зона висит в другом аккаунте. Cloudflare не даёт держать один
                # домен в двух аккаунтах сразу, поэтому переносить можно только
                # удалив старую. Делаем это осознанно и только по команде.
                print(f"    {domain}: зона в чужом аккаунте — пропускаю, "
                      f"перенос делайте вручную")
                continue

            if not zone:
                d = cf.create_zone(name, acc_id)
                if not d.get("success"):
                    print(f"    {domain}: ОШИБКА создания зоны — {errors(d)}")
                    continue
                zone = d["result"]
                print(f"    {domain}: зона создана")
            else:
                print(f"    {domain}: зона уже есть ({zone.get('status')})")

            zone_id = zone.get("id", "dry-run")
            if not args.dry_run and zone_id != "dry-run":
                for rec in (name, f"www.{name}"):
                    d = cf.upsert_a(zone_id, rec, args.ip)
                    if not d.get("success"):
                        print(f"      A {rec}: ОШИБКА — {errors(d)}")
                d = cf.set_ssl_full(zone_id)
                if not d.get("success"):
                    print(f"      SSL: не выставлен — {errors(d)}")

            ns = zone.get("name_servers") or []
            row["NS1"] = ns[0] if len(ns) > 0 else ""
            row["NS2"] = ns[1] if len(ns) > 1 else ""
        print()

    if not args.dry_run:
        with open(args.split, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()), delimiter=delim)
            w.writeheader()
            w.writerows(rows)
        print(f"Пары NS записаны в {args.split} — их и прописывать у регистратора.")

    pairs = {(r.get("NS1"), r.get("NS2")) for r in rows if r.get("NS1")}
    if pairs:
        print(f"Различных пар NS получилось: {len(pairs)} на {len(rows)} доменов.")


if __name__ == "__main__":
    main()
