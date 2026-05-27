#!/usr/bin/env python3
"""Генерация контент-плана для кампании №3 (divent.ru, фотозоны).

25 сайтов × 6 статей = 150 строк CSV.
На сайте: 1 анкор клиента + 2 траста + 3 без анкора, всего 6 статей.

Анкоры клиента берём из docs Google Sheets (CSV-экспорт сохранён в /tmp/campaign3.csv
либо передаётся параметром --anchors).
"""
from __future__ import annotations

import argparse
import csv
import random
from pathlib import Path

# 25 рубрик — разные ракурсы event/photo-индустрии.
# Каждой рубрике соответствует список из 6 тем в порядке:
#   [no-anchor, trust1, client-anchor, no-anchor, trust2, no-anchor]
# (то есть «бутерброд»: трасты и клиентский анкор обрамлены нейтральными статьями)
CATEGORIES = [
    "Аренда фотозон в Екатеринбурге",
    "Аренда фотозон в Москве",
    "Фотозоны для свадебных церемоний",
    "Корпоративные мероприятия и фото-оформление",
    "Фотозоны в Екатеринбурге: тренды и форматы",
    "Фотозоны на массовых мероприятиях",
    "Аренда фотозон в Екб: гид по выбору",
    "Event-индустрия Москвы: фотозоны и оформление",
    "Фотозоны в Екатеринбурге для бизнеса",
    "Интерактивные фотозоны на мероприятиях",
    "Фотозоны в городской среде",
    "Аренда фотозон: что важно знать заказчику",
    "Фотозоны в Екатеринбурге: подбор по случаю",
    "Праздничное оформление: фотозоны и декор",
    "Фотозоны как часть сценария мероприятия",
    "LED-технологии в оформлении фотозон",
    "Аренда фотозон под событие любого масштаба",
    "Светодиодное оборудование на мероприятиях",
    "Тренды в аренде фотозон",
    "LED-фотозоны: технические характеристики",
    "Свадебные фотозоны в Екатеринбурге",
    "LED-оформление массовых event-проектов",
    "Свадьбы в Екатеринбурге: фотозоны и декор",
    "Светодиодные фотозоны: преимущества для event",
    "Выпускные в Екатеринбурге: оформление фотозон",
]

# Универсальные траст-источники для event/photo-тематики
TRUST_SOURCES = [
    ("фотография", "https://ru.wikipedia.org/wiki/Фотография"),
    ("свадебные традиции", "https://ru.wikipedia.org/wiki/Свадьба"),
    ("светодиод", "https://ru.wikipedia.org/wiki/Светодиод"),
    ("корпоративное мероприятие", "https://ru.wikipedia.org/wiki/Корпоративное_мероприятие"),
    ("event-менеджмент", "https://ru.wikipedia.org/wiki/Event-маркетинг"),
    ("светодиодный экран", "https://ru.wikipedia.org/wiki/Светодиодный_экран"),
    ("Росстандарт", "https://www.rst.gov.ru/"),
    ("ГОСТ Р", "https://www.gost.ru/"),
    ("выпускной вечер", "https://ru.wikipedia.org/wiki/Выпускной_вечер"),
    ("фотосессия", "https://ru.wikipedia.org/wiki/Фотосессия"),
    ("освещение", "https://ru.wikipedia.org/wiki/Освещение"),
    ("праздничное оформление", "https://ru.wikipedia.org/wiki/Декор"),
    ("Министерство культуры РФ", "https://culture.gov.ru/"),
    ("дополненная реальность", "https://ru.wikipedia.org/wiki/Дополненная_реальность"),
    ("RGB-светодиод", "https://ru.wikipedia.org/wiki/RGB"),
]


def topic_templates(category: str, anchor: str) -> list[tuple[str, str]]:
    """Шесть пар (тема, slot_marker) для рубрики.

    slot_marker: 'no', 'trust', 'client', 'no', 'trust', 'no'
    """
    a = anchor
    cat = category
    return [
        (f"{cat}: основные форматы и решения 2026 года", "no"),
        (f"{cat}: технологии, материалы и оборудование", "trust"),
        (f"Как выбрать {a}: критерии, сервис и бюджет", "client"),
        (f"{cat}: примеры удачных кейсов и нестандартные идеи", "no"),
        (f"{cat}: безопасность, монтаж и нормативы", "trust"),
        (f"{cat}: ошибки заказчиков и как их избежать", "no"),
    ]


def load_anchors(path: Path) -> list[tuple[str, str]]:
    anchors = []
    with open(path, encoding='utf-8') as f:
        reader = csv.reader(f)
        for row in reader:
            if len(row) >= 2 and row[0].strip() and row[1].strip():
                anchors.append((row[0].strip(), row[1].strip()))
    return anchors


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--anchors', default='/tmp/campaign3.csv',
                   help='CSV «анкор,url» — 25 строк')
    p.add_argument('--out', default='content_plan_campaign3.csv')
    p.add_argument('--seed', type=int, default=42)
    args = p.parse_args()

    random.seed(args.seed)

    anchors = load_anchors(Path(args.anchors))
    if len(anchors) != 25:
        raise SystemExit(f"Ожидалось 25 анкоров, найдено {len(anchors)} в {args.anchors}")
    if len(CATEGORIES) != 25:
        raise SystemExit(f"Ожидалось 25 рубрик, в коде {len(CATEGORIES)}")

    # Для каждого сайта выбираем 2 разных траст-источника
    trust_pool = list(TRUST_SOURCES)

    rows = []
    rows.append(["Сайт", "Рубрика", "Тема статьи", "Анкор", "Ссылка", "Тип"])

    for site_id, ((anchor, client_url), category) in enumerate(zip(anchors, CATEGORIES), start=1):
        topics = topic_templates(category, anchor)
        # Берём 2 траст-источника для двух trust-слотов; разные между собой
        trusts = random.sample(trust_pool, 2)
        trust_iter = iter(trusts)

        for topic, slot in topics:
            if slot == 'no':
                rows.append([site_id, category, topic, '', '', ''])
            elif slot == 'trust':
                t_anchor, t_url = next(trust_iter)
                rows.append([site_id, category, topic, t_anchor, t_url, 'траст'])
            elif slot == 'client':
                rows.append([site_id, category, topic, anchor, client_url, 'анкор клиента'])

    with open(args.out, 'w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f, delimiter=';')
        writer.writerows(rows)

    print(f"Готово: {args.out}, строк: {len(rows) - 1}")
    print(f"  Анкоров клиента: {sum(1 for r in rows[1:] if r[5] == 'анкор клиента')}")
    print(f"  Траст-ссылок:    {sum(1 for r in rows[1:] if r[5] == 'траст')}")
    print(f"  Без анкоров:     {sum(1 for r in rows[1:] if r[5] == '')}")


if __name__ == "__main__":
    main()
