#!/usr/bin/env python3
"""Переводит домены на новый сервер, не трогая неймсерверы.

Каждый домен сети живёт в своём аккаунте Cloudflare и имеет собственную пару
NS — именно это разносит доноров между собой. Пока аккаунт доступен, переезд
на новый сервер сводится к правке одной A-записи: неймсерверы не меняются,
регистратор не участвует, домен не уходит в перевыдачу.

Доступ берётся из файла с ключами (по строке на домен), он в gitignore:

    reports/recovery/cf_access.csv
    Домен;Email;Токен;Глобальный ключ

Достаточно любого из двух: токен с правами Zone:Read + DNS:Edit, либо связка
email и глобального ключа. Пароль тут не годится — API его не принимает.

    python3 cf_repoint.py --ip 157.228.135.19 --dry-run
    python3 cf_repoint.py --ip 157.228.135.19
    python3 cf_repoint.py --ip 157.228.135.19 --only drunk-fish.ru
"""
import argparse
import csv
import os
import sys
import time

import requests

API = "https://api.cloudflare.com/client/v4"
ACCESS = "reports/recovery/cf_access.csv"


def to_ascii(domain):
    try:
        return domain.encode("idna").decode()
    except Exception:
        return domain


def sniff(path):
    with open(path, encoding="utf-8-sig") as f:
        head = f.readline()
    return ";" if head.count(";") > head.count(",") else ","


def errors(payload):
    return "; ".join(e.get("message", "?") for e in (payload.get("errors") or [])) \
        or "неизвестно"


class Cloudflare:
    def __init__(self, email=None, token=None, key=None, dry_run=False):
        self.s = requests.Session()
        if token:
            self.s.headers.update({"Authorization": f"Bearer {token}"})
        elif email and key:
            self.s.headers.update({"X-Auth-Email": email, "X-Auth-Key": key})
        else:
            raise ValueError("нужен либо токен, либо email вместе с глобальным ключом")
        self.s.headers.update({"Content-Type": "application/json"})
        self.dry_run = dry_run

    def call(self, method, path, **kw):
        if self.dry_run and method != "GET":
            return {"success": True, "result": {"_dry_run": True}}
        for attempt in range(4):
            r = self.s.request(method, API + path, timeout=45, **kw)
            if r.status_code == 429:
                time.sleep(3 * (attempt + 1))
                continue
            try:
                return r.json()
            except ValueError:
                return {"success": False,
                        "errors": [{"message": f"HTTP {r.status_code}"}]}
        return {"success": False, "errors": [{"message": "rate limited"}]}

    def zone(self, name):
        res = self.call("GET", f"/zones?name={name}").get("result") or []
        return res[0] if res else None

    def a_records(self, zone_id, name):
        return self.call(
            "GET", f"/zones/{zone_id}/dns_records?type=A&name={name}"
        ).get("result") or []

    def set_a(self, zone_id, name, ip, record=None):
        body = {"type": "A", "name": name, "content": ip, "ttl": 1, "proxied": True}
        if record:
            return self.call("PUT", f"/zones/{zone_id}/dns_records/{record['id']}",
                             json=body)
        return self.call("POST", f"/zones/{zone_id}/dns_records", json=body)

    def setting(self, zone_id, key, value):
        return self.call("PATCH", f"/zones/{zone_id}/settings/{key}",
                         json={"value": value})


def main():
    ap = argparse.ArgumentParser(description="Перевод доменов на новый сервер")
    ap.add_argument("--ip", required=True, help="IP нового сервера")
    ap.add_argument("--access", default=ACCESS)
    ap.add_argument("--only", default=None, help="домены через запятую")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not os.path.exists(args.access):
        sys.exit(f"нет файла с доступами: {args.access}\n"
                 f"формат: Домен;Email;Токен;Глобальный ключ")

    rows = list(csv.DictReader(open(args.access, encoding="utf-8-sig"),
                               delimiter=sniff(args.access)))
    if args.only:
        want = {d.strip() for d in args.only.split(",")}
        rows = [r for r in rows
                if r["Домен"].strip() in want or to_ascii(r["Домен"].strip()) in want]
    if not rows:
        sys.exit("под фильтр ничего не попало")

    print(f"Доменов: {len(rows)}"
          f"{'  РЕЖИМ ПРОСМОТРА' if args.dry_run else ''}\n")

    done = failed = 0
    for row in rows:
        domain = row["Домен"].strip()
        name = to_ascii(domain)
        try:
            cf = Cloudflare(email=row.get("Email", "").strip() or None,
                            token=row.get("Токен", "").strip() or None,
                            key=row.get("Глобальный ключ", "").strip() or None,
                            dry_run=args.dry_run)
        except ValueError as exc:
            print(f"  {domain}: {exc}")
            failed += 1
            continue

        zone = cf.zone(name)
        if not zone:
            print(f"  {domain}: зона в этом аккаунте не найдена")
            failed += 1
            continue

        ns = "/".join(n.split(".")[0] for n in (zone.get("name_servers") or []))
        problems = []
        for record_name in (name, f"www.{name}"):
            existing = cf.a_records(zone["id"], record_name)
            was = existing[0]["content"] if existing else "нет записи"
            if existing and existing[0]["content"] == args.ip \
                    and existing[0].get("proxied"):
                continue
            res = cf.set_a(zone["id"], record_name, args.ip,
                           existing[0] if existing else None)
            if res.get("success"):
                print(f"  {domain}: {record_name} {was} -> {args.ip}")
            else:
                problems.append(f"{record_name}: {errors(res)}")

        # Тот же режим, что и на новых зонах: без full origin отвечает
        # редиректом на https и получается петля
        for key, value in (("ssl", "full"), ("always_use_https", "on")):
            res = cf.setting(zone["id"], key, value)
            if not res.get("success"):
                problems.append(f"{key}: {errors(res)}")

        if problems:
            print(f"  {domain}: ОШИБКИ — {'; '.join(problems)}")
            failed += 1
        else:
            print(f"  {domain}: готово, NS остались {ns}")
            done += 1

    print(f"\nпереведено: {done}, с ошибками: {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
