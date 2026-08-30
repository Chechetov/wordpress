#!/usr/bin/env python3
"""Спецификация восстановления размещений с упавших доноров.

Тела статей, опубликованных после февральской выгрузки, потеряны вместе с
серверами: в бэкапах их нет. Зато сохранились адреса, даты, анкоры и цели —
этого хватает, чтобы восстановить статьи на ТЕХ ЖЕ URL, а значит сохранить
ссылочный вес и позиции в индексе.

Ключевая тонкость: важен не только слаг записи, но и слаг рубрики — пермалинк
имеет вид /%category%/%postname%/, и если рубрика получит другой слаг,
восстановленная статья встанет по новому адресу, а старый останется 404.

    python3 build_recovery_spec.py
"""
import csv
import json
import os
from collections import defaultdict
from urllib.parse import urlparse, unquote

SRC = "reports/network_published_urls.csv"
OUT = "reports/recovery/money_placements.csv"
DEAD = [
    "drunk-fish.ru", "kgdink.ru", "mai-hoshi.ru", "omegabay.ru", "prforce.ru",
    "property-in-alanya.ru", "speciallabel.ru", "techfile.ru", "top-audit.ru",
    "unit-org.ru", "2semechki.ru", "avtogear62.ru", "promplo.ru", "kakudobrit.ru",
    "ledpnz.ru", "elintel.ru", "pro-covers.ru", "yellodigital.ru",
    "доступныйсервис.рф", "стандарт72.рф",
]
MONEY = ("divent.ru", "aso-cdo.ru")


def split_url(u):
    """Из адреса статьи достаёт слаг рубрики и слаг записи."""
    path = unquote(urlparse(u).path).strip("/")
    if not path:
        return "", ""
    parts = [p for p in path.split("/") if p]
    if len(parts) >= 2:
        return parts[-2], parts[-1]
    return "", parts[-1]


def main():
    dead = set(DEAD)
    rows = list(csv.DictReader(open(SRC, encoding="utf-8-sig")))
    out, by_domain = [], defaultdict(int)
    exact = byid = money = 0

    for r in rows:
        d = r["Домен"]
        if d not in dead:
            continue
        url = r["URL статьи"]
        target = r["Целевая ссылка"]
        is_money = any(m in target for m in MONEY)
        if "?p=" in url:
            cat_slug = post_slug = ""
            recoverable = "нет: адрес вида ?p=ID, слаг не восстановить"
            byid += 1
        else:
            cat_slug, post_slug = split_url(url)
            recoverable = "да"
            exact += 1
        if is_money:
            money += 1
        by_domain[d] += 1
        out.append({
            "Домен": d,
            "URL статьи": url,
            "Слаг рубрики": cat_slug,
            "Слаг записи": post_slug,
            "Дата": r["Дата"],
            "Анкор": r["Анкор"],
            "Целевая ссылка": target,
            "Денежная": "да" if is_money else "",
            "Тема": r["Тема"],
            "Точный URL": recoverable,
        })

    out.sort(key=lambda x: (x["Домен"], x["Дата"]))
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0].keys()))
        w.writeheader()
        w.writerows(out)

    print(f"Размещений на упавших донорах: {len(out)}")
    print(f"  восстановимы на прежний URL: {exact}")
    print(f"  адрес вида ?p=ID (URL не восстановить): {byid}")
    print(f"  ведут на divent.ru / aso-cdo.ru: {money}")
    print(f"\nДоноров затронуто: {len(by_domain)}")
    print(f"Спецификация: {OUT}")


if __name__ == "__main__":
    main()
