#!/usr/bin/env python3
"""Собирает поимённую спецификацию восстановления статей на 20 упавших донорах.

Тела статей погибли вместе с серверами. Всё, что задаёт адрес, уцелело в
репозитории, но не в одном месте:

  reports/publish_all_*.json, republish_*, campaign4_state.json
        — что и когда публиковалось: домен, post_id, заголовок, тема;
  reports/recovery/money_placements.csv
        — анкор, целевая ссылка и признак денежной ссылки, плюс 55 адресов,
          записанных целиком;
  content_plan*.csv
        — название рубрики по теме статьи.

Основой берутся журналы публикаций, а не реестр размещений: в реестре только
статьи с анкорами, и он теряет больше половины. Проверено по базам сайтов —
из 235 публикаций в журналах не уцелела ни одна.

Адрес статьи — /<слаг рубрики>/<слаг записи>/, слаг WordPress собирал из
заголовка транслитерацией Cyr-To-Lat. Значит по заголовку адрес восстанавливается
точно, а заголовки в журналах есть у 211 публикаций из 235.

Скрипт не угадывает: где слаг записан целиком, реконструкция обязана с ним
совпасть, иначе это ошибка и ненулевой код возврата.

    python3 build_restore_plan.py
    python3 build_restore_plan.py --ids-file reports/recovery/next_ids.json
"""
import argparse
import csv
import glob
import json
import re
import sys
from collections import defaultdict

PLACEMENTS = "reports/recovery/money_placements.csv"
NS_LIST = "reports/recovery/ns_change.csv"
OUT = "reports/recovery/restore_plan.csv"

# Серверы удалены 18–19 августа: всё, что стояло в очереди на более поздние
# даты, до публикации не дожило и в индекс не попало.
DEAD_FROM = "2026-08-19"

FIELDS = ["Домен", "Домен ASCII", "ID", "Заголовок", "Слаг", "Рубрика",
          "Слаг рубрики", "Дата", "Анкор", "Целевая ссылка", "Денежная",
          "Тема", "Был в индексе", "Источник заголовка", "Источник слага"]

# Транслитерация Cyr-To-Lat — та же, что стояла на донорах: я→ja, щ→shh, х→h.
# Проверена на 55 записанных целиком слагах, расхождений нет.
CYR = {
    'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'jo',
    'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'j', 'к': 'k', 'л': 'l', 'м': 'm',
    'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
    'ф': 'f', 'х': 'h', 'ц': 'c', 'ч': 'ch', 'ш': 'sh', 'щ': 'shh', 'ъ': '',
    'ы': 'y', 'ь': '', 'э': 'je', 'ю': 'ju', 'я': 'ja',
}

# Четыре денежные статьи кампании №4 публиковались без записи заголовка в
# журнал. Адрес у них известен целиком, поэтому заголовок восстановлен так,
# чтобы транслитерация давала ровно этот слаг — скрипт это проверяет.
TITLE_BY_SLUG = {
    "kak-vybrat-fotobudku-v-moskve-bez-pereplat":
        "Как выбрать фотобудку в Москве без переплат",
    "fotobudka-s-ii-v-moskve-vybor-bez-pereplat":
        "Фотобудка с ИИ в Москве: выбор без переплат",
    "kak-vybrat-led-fotozonu-dlja-arendy":
        "Как выбрать LED-фотозону для аренды",
    "led-fotozona-kak-vybrat-podrjadchika":
        "LED-фотозона: как выбрать подрядчика",
}


def slugify(text):
    out = ''.join(CYR.get(ch, ch) for ch in text.lower())
    return re.sub(r'-+', '-', re.sub(r'[^a-z0-9]+', '-', out)).strip('-')


def to_ascii(domain):
    try:
        return domain.encode("idna").decode()
    except Exception:
        return domain


def load_fallen():
    return [r["Домен"].strip()
            for r in csv.DictReader(open(NS_LIST, encoding="utf-8-sig"))]


def load_publications(fallen):
    """Все успешные публикации по упавшим доменам, склеенные по (домен, ID).

    Одна и та же статья попадает в несколько журналов: publish_all её создал,
    attach_images дописал обложку, republish переопубликовал. Поля берём по
    первому непустому — так заголовок из publish_all не теряется, даже если
    более поздний журнал его не записал.
    """
    merged = defaultdict(dict)
    for path in sorted(glob.glob("reports/*.json")):
        try:
            data = json.load(open(path, encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(data, list):
            continue
        for item in data:
            if not isinstance(item, dict):
                continue
            domain, pid = item.get("domain"), item.get("post_id")
            if domain not in fallen or not pid or item.get("status") != "success":
                continue
            rec = merged[(domain, pid)]
            for key, value in item.items():
                if value and not rec.get(key):
                    rec[key] = value
    return merged


def load_categories():
    """Тема статьи -> название рубрики, из планов кампаний."""
    plan = {}
    for path in glob.glob("content_plan*.csv"):
        with open(path, encoding="utf-8-sig") as f:
            delim = ";" if f.readline().count(";") else ","
            f.seek(0)
            for row in csv.DictReader(f, delimiter=delim):
                topic = (row.get("Тема статьи") or row.get("Тема") or "").strip()
                cat = (row.get("Рубрика") or "").strip()
                if topic and cat:
                    plan.setdefault(topic, cat)
    return plan


def load_anchors():
    """Анкоры и адреса из реестра размещений, разложенные по способам поиска."""
    by_id, by_slug, by_date = {}, {}, defaultdict(list)
    for row in csv.DictReader(open(PLACEMENTS, encoding="utf-8-sig")):
        domain = row["Домен"].strip()
        m = re.search(r"\?p=(\d+)", row["URL статьи"])
        if m:
            by_id[(domain, int(m.group(1)))] = row
        slug = row["Слаг записи"].strip()
        if slug:
            by_slug[(domain, slug)] = row
        by_date[(domain, row["Дата"].strip())].append(row)
    return by_id, by_slug, by_date


def main():
    ap = argparse.ArgumentParser(description="Спецификация восстановления статей")
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--ids-file", default=None,
                    help="JSON {домен: следующий свободный ID} с сервера")
    args = ap.parse_args()

    fallen = load_fallen()
    pubs = load_publications(set(fallen))
    topic_to_cat = load_categories()
    anch_id, anch_slug, anch_date = load_anchors()
    cat_by_slug = {slugify(c): c for c in set(topic_to_cat.values())}

    out_rows, problems = [], []
    used_anchor_rows = set()

    for (domain, post_id), pub in sorted(pubs.items()):
        title = (pub.get("title") or "").strip()
        topic = (pub.get("topic") or "").strip()
        date = (pub.get("scheduled") or "")[:10]

        # --- анкор: ищем в реестре по ID, затем по слагу заголовка,
        #     затем по дате — так находятся статьи, чей заголовок не записан
        anchor_row = anch_id.get((domain, post_id))
        if not anchor_row and title:
            anchor_row = anch_slug.get((domain, slugify(title)))
        if not anchor_row and not title:
            same_day = [r for r in anch_date.get((domain, date), [])
                        if not r["Слаг записи"].strip()
                        or r["Слаг записи"].strip() in TITLE_BY_SLUG]
            if len(same_day) == 1:
                anchor_row = same_day[0]

        # --- заголовок и слаг
        known_slug = anchor_row["Слаг записи"].strip() if anchor_row else ""
        if title:
            title_src = "журнал публикаций"
        elif known_slug in TITLE_BY_SLUG:
            title = TITLE_BY_SLUG[known_slug]
            title_src = "восстановлен из слага"
        else:
            title_src = "сгенерируется"

        if title and known_slug:
            if slugify(title) != known_slug:
                problems.append(
                    f"{domain} id={post_id}: слаг из заголовка не сошёлся — "
                    f"ждали {known_slug}, получилось {slugify(title)}")
            slug, slug_src = known_slug, "записан в реестре"
        elif title:
            slug, slug_src = slugify(title), "из заголовка"
        else:
            # Ни заголовка, ни адреса: статью придётся написать заново, и она
            # встанет по новому адресу. Прежний URL для неё потерян.
            slug, slug_src = "", "утрачен"

        # --- рубрика
        cat_slug = anchor_row["Слаг рубрики"].strip() if anchor_row else ""
        cat_name = topic_to_cat.get(topic, "")
        if cat_slug:
            cat_name = cat_by_slug.get(cat_slug, cat_name)
        elif cat_name:
            cat_slug = slugify(cat_name)
        if not cat_name or not cat_slug:
            problems.append(f"{domain} id={post_id}: не определилась рубрика "
                            f"(тема «{topic}»)")
            continue

        if anchor_row:
            used_anchor_rows.add(id(anchor_row))

        out_rows.append({
            "Домен": domain, "Домен ASCII": to_ascii(domain),
            "ID": post_id, "Заголовок": title, "Слаг": slug,
            "Рубрика": cat_name, "Слаг рубрики": cat_slug,
            "Дата": date,
            "Анкор": anchor_row["Анкор"].strip() if anchor_row else "",
            "Целевая ссылка": anchor_row["Целевая ссылка"].strip() if anchor_row else "",
            "Денежная": anchor_row["Денежная"].strip() if anchor_row else "",
            "Тема": topic,
            "Был в индексе": "нет" if date >= DEAD_FROM else "да",
            "Источник заголовка": title_src, "Источник слага": slug_src,
        })

    # --- одинаковые заголовки: повторяем правило WordPress
    # В кампании несколько статей на сайте выходили под одним заголовком.
    # WordPress не допускает двух записей с одинаковым post_name и дописывает
    # к слагу «-2», «-3» в порядке создания. Порядок создания — это порядок
    # post_id, так что прежние адреса воспроизводятся точно.
    same_slug = defaultdict(list)
    for row in out_rows:
        if row["Слаг"]:
            same_slug[(row["Домен"], row["Слаг"])].append(row)
    renamed = 0
    for (dom, slug), group in same_slug.items():
        if len(group) < 2:
            continue
        group.sort(key=lambda r: int(r["ID"]))
        for n, row in enumerate(group[1:], start=2):
            if row["Источник слага"] == "записан в реестре":
                problems.append(
                    f"{dom}: слаг {slug} записан в реестре, но на него "
                    f"претендует и ID {row['ID']}")
                continue
            row["Слаг"] = f"{slug}-{n}"
            row["Источник слага"] = "из заголовка, суффикс WordPress"
            renamed += 1

    seen = defaultdict(list)
    for row in out_rows:
        if row["Слаг"]:
            seen[(row["Домен"], row["Слаг"])].append(row["ID"])
    for (dom, slug), ids in seen.items():
        if len(ids) > 1:
            problems.append(f"{dom}: слаг {slug} занят дважды, ID {ids}")

    # --- сверка ID со свободным диапазоном сайтов
    if args.ids_file:
        next_ids = json.load(open(args.ids_file, encoding="utf-8"))
        for row in out_rows:
            nxt = next_ids.get(row["Домен ASCII"]) or next_ids.get(row["Домен"])
            if nxt and int(row["ID"]) < int(nxt):
                problems.append(
                    f"{row['Домен']}: ID {row['ID']} уже занят "
                    f"(следующий свободный {nxt})")

    with open(args.out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(out_rows)

    money = sum(1 for r in out_rows if r["Денежная"] == "да")
    exact = sum(1 for r in out_rows if r["Слаг"])
    indexed = sum(1 for r in out_rows if r["Был в индексе"] == "да")
    print(f"Статей к восстановлению: {len(out_rows)}")
    print(f"  денежных: {money} | трастовых: {len(out_rows) - money}")
    print(f"  успели попасть в индекс: {indexed} | "
          f"не успели (стояли в очереди после 19.08): {len(out_rows) - indexed}")
    print(f"  встанут на прежний адрес: {exact} | адрес утрачен, будет новый: "
          f"{len(out_rows) - exact}")
    print(f"  с суффиксом -2/-3 из-за одинаковых заголовков: {renamed}")
    print(f"  слаг записан в реестре: "
          f"{sum(1 for r in out_rows if r['Источник слага'] == 'записан в реестре')}"
          f" | восстановлен из заголовка: "
          f"{sum(1 for r in out_rows if r['Источник слага'] == 'из заголовка')}")
    print(f"Записано: {args.out}")

    if problems:
        print(f"\nПРОБЛЕМЫ ({len(problems)}):", file=sys.stderr)
        for p in problems:
            print(f"  {p}", file=sys.stderr)
        return 1
    print("\nПроверки пройдены: слаги сходятся, адреса уникальны.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
