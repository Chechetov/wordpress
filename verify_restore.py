#!/usr/bin/env python3
"""Проверяет, что все прежние адреса 20 упавших доноров снова отдают 200.

Проверка идёт по origin с подставленным заголовком Host, а не через интернет:
пока домены делегированы на старые зоны Cloudflare, снаружи они недоступны, но
знать состояние сайтов надо уже сейчас. После смены неймсерверов тот же скрипт
запускается с --public и ходит обычным путём.

Проверяются три вещи:
  1. все восстановленные статьи отдают 200 по своему адресу;
  2. на денежных страницах стоит нужный анкор с нужной ссылкой;
  3. февральские записи, вернувшиеся из выгрузок, тоже на месте.

    python3 verify_restore.py
    python3 verify_restore.py --public
    python3 verify_restore.py --only drunk-fish.ru
"""
import argparse
import csv
import json
import os
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime
from urllib.parse import urlsplit

PLAN = "reports/recovery/restore_plan.csv"
RESTORED = "reports/recovery/restored_urls.csv"
SERVER = os.getenv("PBN_SERVER", "157.228.135.19")
SSH_KEY = os.path.expanduser(os.getenv("PBN_SSH_KEY", "~/.ssh/pbn_recovery"))

# Скрипт, который бежит на сервере: обходит адреса и отдаёт по строке на каждый.
REMOTE = r'''
import json, subprocess, sys
targets = json.load(open("/tmp/verify_targets.json", encoding="utf-8"))
public = targets.get("public", False)
out = []
for t in targets["items"]:
    host, path = t["host"], t["path"]
    if public:
        url = "https://%s%s" % (host, path)
        cmd = ["curl", "-sL", "--max-time", "25", "-w", "\n__CODE__%{http_code}", url]
    else:
        url = "http://127.0.0.1" + path
        cmd = ["curl", "-s", "--max-time", "25", "-H", "Host: " + host,
               "-w", "\n__CODE__%{http_code}", url]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=40)
        body, _, code = r.stdout.rpartition("__CODE__")
    except Exception as exc:
        body, code = "", "ERR"
    row = {"host": host, "path": path, "code": code.strip()}
    if t.get("link"):
        row["link_ok"] = ('href="%s"' % t["link"]) in body
        row["anchor_ok"] = bool(t.get("anchor")) and t["anchor"] in body
    out.append(row)
print(json.dumps(out, ensure_ascii=False))
'''


def ssh(cmd, capture=True):
    full = ["ssh", "-o", "ConnectTimeout=20", "-i", SSH_KEY, f"root@{SERVER}", cmd]
    return subprocess.run(full, capture_output=capture, text=True)


def load_targets(only):
    """Адреса восстановленных статей: итоговые, если генерация уже прошла."""
    src = RESTORED if os.path.exists(RESTORED) else PLAN
    items, kind = [], ("restored" if src == RESTORED else "plan")
    for row in csv.DictReader(open(src, encoding="utf-8-sig")):
        domain = row["Домен"]
        if only and domain not in only:
            continue
        if kind == "restored":
            url = row["URL"]
        else:
            if not row["Слаг"]:
                continue
            url = f'https://{domain}/{row["Слаг рубрики"]}/{row["Слаг"]}/'
        parts = urlsplit(url)
        items.append({
            "host": parts.netloc, "path": parts.path or "/",
            "domain": domain,
            "anchor": row.get("Анкор", ""),
            "link": row.get("Целевая ссылка", "") if row.get("Денежная") == "да" else "",
            "group": "восстановленные",
        })
    return items


def load_existing(only):
    """Постоянные адреса записей, уже стоящих на сайтах (февральские выгрузки)."""
    remote = r'''
import json, subprocess, os
res = []
for name in sorted(os.listdir("/var/www")):
    root = "/var/www/" + name
    if not os.path.exists(root + "/wp-config.php"):
        continue
    r = subprocess.run(["sudo", "-u", "www-data", "-H",
                        "WP_CLI_CACHE_DIR=/var/www/.wp-cli-cache", "wp", "post",
                        "list", "--post_type=post", "--post_status=publish",
                        "--field=url", "--path=" + root],
                       capture_output=True, text=True)
    for line in r.stdout.split():
        res.append([name, line.strip()])
print(json.dumps(res, ensure_ascii=False))
'''
    proc = ssh(f"python3 - <<'PYEOF'\n{remote}\nPYEOF")
    try:
        rows = json.loads(proc.stdout.strip().splitlines()[-1])
    except Exception:
        print("не удалось получить список адресов с сервера", file=sys.stderr)
        return []
    items = []
    for _, url in rows:
        parts = urlsplit(url)
        if only and parts.netloc not in only:
            continue
        items.append({"host": parts.netloc, "path": parts.path or "/",
                      "domain": parts.netloc, "anchor": "", "link": "",
                      "group": "все записи сайта"})
    return items


def main():
    ap = argparse.ArgumentParser(description="Проверка адресов после восстановления")
    ap.add_argument("--public", action="store_true",
                    help="ходить через интернет, а не по origin")
    ap.add_argument("--only", default=None, help="домены через запятую")
    ap.add_argument("--skip-existing", action="store_true",
                    help="не проверять февральские записи")
    args = ap.parse_args()

    only = {d.strip() for d in args.only.split(",")} if args.only else None

    items = load_targets(only)
    seen = {(i["host"], i["path"]) for i in items}
    if not args.skip_existing:
        for it in load_existing(only):
            if (it["host"], it["path"]) not in seen:
                items.append(it)
                seen.add((it["host"], it["path"]))

    if not items:
        sys.exit("нечего проверять")

    print(f"адресов к проверке: {len(items)} "
          f"({'через интернет' if args.public else 'по origin с заголовком Host'})")

    payload = json.dumps({"public": args.public, "items": items}, ensure_ascii=False)
    proc = subprocess.run(
        ["ssh", "-o", "ConnectTimeout=20", "-i", SSH_KEY, f"root@{SERVER}",
         "cat > /tmp/verify_targets.json"],
        input=payload, text=True, capture_output=True)
    if proc.returncode:
        sys.exit(f"не удалось отправить список на сервер: {proc.stderr}")

    proc = ssh(f"python3 - <<'PYEOF'\n{REMOTE}\nPYEOF")
    try:
        results = json.loads(proc.stdout.strip().splitlines()[-1])
    except Exception:
        sys.exit(f"сервер не ответил разбираемым JSON:\n{proc.stdout[-500:]}\n{proc.stderr[-500:]}")

    by_key = {(r["host"], r["path"]): r for r in results}
    codes = Counter()
    bad, link_bad = [], []
    per_domain = defaultdict(lambda: Counter())

    for it in items:
        res = by_key.get((it["host"], it["path"]), {"code": "нет ответа"})
        code = res.get("code", "?")
        codes[code] += 1
        per_domain[it["domain"]][code] += 1
        if code != "200":
            bad.append((it, code))
        elif it["link"] and not (res.get("link_ok") and res.get("anchor_ok")):
            link_bad.append((it, res))

    print("\nкоды ответа:")
    for code, n in codes.most_common():
        print(f"   {code}: {n}")

    if bad:
        print(f"\nне отдают 200 ({len(bad)}):")
        for it, code in bad[:40]:
            print(f"   {code}  https://{it['host']}{it['path']}")
        if len(bad) > 40:
            print(f"   … и ещё {len(bad) - 40}")

    if link_bad:
        print(f"\nденежная ссылка или анкор не на месте ({len(link_bad)}):")
        for it, res in link_bad[:20]:
            print(f"   https://{it['host']}{it['path']}  "
                  f"ссылка={res.get('link_ok')} анкор={res.get('anchor_ok')}")

    money = [i for i in items if i["link"]]
    money_ok = len(money) - len(link_bad)
    print(f"\nденежных страниц: {len(money)}, ссылка и анкор на месте: {money_ok}")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = f"reports/recovery/verify_{stamp}.csv"
    with open(out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["Домен", "URL", "Код", "Группа", "Ссылка на месте", "Анкор на месте"])
        for it in items:
            res = by_key.get((it["host"], it["path"]), {})
            w.writerow([it["domain"], f"https://{it['host']}{it['path']}",
                        res.get("code", ""), it["group"],
                        res.get("link_ok", ""), res.get("anchor_ok", "")])
    print(f"подробности: {out}")
    return 1 if bad or link_bad else 0


if __name__ == "__main__":
    sys.exit(main())
