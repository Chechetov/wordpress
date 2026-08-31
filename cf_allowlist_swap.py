#!/usr/bin/env python3
"""Меняет IP в белых списках custom-правил Cloudflare.

На зонах сети стоит правило вида «Search Protection»: всем, кроме поисковых
ботов и горстки своих IP, показывается Managed Challenge. Среди своих IP
прописан origin — после переезда на новый сервер там остаётся мёртвый адрес,
и сам сервер начинает ловить челлендж на соседних доменах сети.

Скрипт проходит по всем custom-правилам зоны, находит те, где в выражении
встречается старый IP, и подставляет новый. Ничего кроме этой подстроки в
выражении не меняется: действие, порядок и статус правила остаются как были.

Доступ — тот же файл, что у cf_repoint.py (в gitignore):

    reports/recovery/cf_access.csv
    Домен;Email;Токен;Глобальный ключ

Токену нужны права Zone:Read и Zone WAF:Edit (у глобального ключа они есть).

    python3 cf_allowlist_swap.py --old 45.95.203.95 --new 157.228.135.19 --dry-run
    python3 cf_allowlist_swap.py --old 45.95.203.95 --new 157.228.135.19
    python3 cf_allowlist_swap.py --old 45.95.203.95 --new 157.228.135.19 --only elintel.ru
"""
import argparse
import csv
import os
import sys

from cf_repoint import ACCESS, Cloudflare, errors, sniff, to_ascii

PHASE = "http_request_firewall_custom"


def custom_rules(cf, zone_id):
    """Точка входа фазы custom-правил. Нет правил — нет и рулсета."""
    res = cf.call("GET", f"/zones/{zone_id}/rulesets/phases/{PHASE}/entrypoint")
    if not res.get("success"):
        return None, [], errors(res)
    ruleset = res.get("result") or {}
    return ruleset.get("id"), ruleset.get("rules") or [], None


def patch_rule(cf, zone_id, ruleset_id, rule, expression):
    body = {"expression": expression,
            "action": rule.get("action"),
            "description": rule.get("description", ""),
            "enabled": rule.get("enabled", True)}
    if rule.get("action_parameters"):
        body["action_parameters"] = rule["action_parameters"]
    return cf.call("PATCH",
                   f"/zones/{zone_id}/rulesets/{ruleset_id}/rules/{rule['id']}",
                   json=body)


def main():
    ap = argparse.ArgumentParser(description="Замена IP в белых списках правил")
    ap.add_argument("--old", required=True, help="IP, который надо убрать")
    ap.add_argument("--new", required=True, help="IP, который надо поставить")
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

    print(f"Доменов: {len(rows)}  {args.old} -> {args.new}"
          f"{'  РЕЖИМ ПРОСМОТРА' if args.dry_run else ''}\n")

    changed = untouched = failed = 0
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

        ruleset_id, rules, problem = custom_rules(cf, zone["id"])
        if problem:
            print(f"  {domain}: не читаются custom-правила — {problem}")
            failed += 1
            continue

        hits = [r for r in rules if args.old in (r.get("expression") or "")]
        if not hits:
            names = ", ".join(r.get("description") or r["id"][:8] for r in rules)
            print(f"  {domain}: {args.old} в правилах не встречается"
                  f"{f' (есть: {names})' if rules else ' (custom-правил нет)'}")
            untouched += 1
            continue

        problems = []
        for rule in hits:
            expression = rule["expression"].replace(args.old, args.new)
            res = patch_rule(cf, zone["id"], ruleset_id, rule, expression)
            label = rule.get("description") or rule["id"][:8]
            if res.get("success"):
                print(f"  {domain}: правило «{label}» — {args.old} -> {args.new}")
            else:
                problems.append(f"{label}: {errors(res)}")

        if problems:
            print(f"  {domain}: ОШИБКИ — {'; '.join(problems)}")
            failed += 1
        else:
            changed += 1

    print(f"\nизменено: {changed}, без изменений: {untouched}, с ошибками: {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
