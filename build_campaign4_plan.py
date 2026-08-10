#!/usr/bin/env python3
"""Генерация контент-плана для кампании №4 (divent.ru, лист «Месяц 2»).

24 донора × 6 статей + 1 донор с двойным анкором (7 статей) = 145 строк CSV.
На сайте: 1 анкор клиента + 2 траста + 3 без анкора.
yellodigital.ru — 2 анкора клиента + 2 траста + 3 без анкора (7 статей).

Анкоры берутся из листа «Месяц 2» Google Sheets (--anchors month2.json),
сайты — из campaign4_sites.json (24 донора, на которых divent ещё не размещался).

Отличия от кампании №3:
  * другие шаблоны тем (чтобы не повторять след прошлого прогона);
  * траст-пул подобран по тематике блока и полностью проверен на 200 OK —
    из старого пула выброшены «Event-маркетинг» и «Корпоративное мероприятие»
    (обе страницы в ru.wikipedia отдают 404) и гос-сайты (недоступны для проверки).
"""
from __future__ import annotations

import argparse
import csv
import json
import random
from pathlib import Path

# --- Траст-источники по тематическим блокам (все проверены: HTTP 200) ---------
TRUST = {
    'photobooth': [
        ("фотокабина", "https://ru.wikipedia.org/wiki/Фотокабина"),
        ("фотография", "https://ru.wikipedia.org/wiki/Фотография"),
        ("фотосессия", "https://ru.wikipedia.org/wiki/Фотосессия"),
        ("освещение", "https://ru.wikipedia.org/wiki/Освещение"),
    ],
    'ai': [
        ("искусственная нейронная сеть",
         "https://ru.wikipedia.org/wiki/Искусственная_нейронная_сеть"),
        ("компьютерное зрение", "https://ru.wikipedia.org/wiki/Компьютерное_зрение"),
        ("генеративный искусственный интеллект",
         "https://ru.wikipedia.org/wiki/Генеративный_искусственный_интеллект"),
        ("фотокабина", "https://ru.wikipedia.org/wiki/Фотокабина"),
    ],
    'led': [
        ("светодиод", "https://ru.wikipedia.org/wiki/Светодиод"),
        ("светодиодный экран", "https://ru.wikipedia.org/wiki/Светодиодный_экран"),
        ("неоновая лампа", "https://ru.wikipedia.org/wiki/Неоновая_лампа"),
        ("освещение", "https://ru.wikipedia.org/wiki/Освещение"),
        ("электробезопасность", "https://ru.wikipedia.org/wiki/Электробезопасность"),
    ],
    'robots': [
        ("робот", "https://ru.wikipedia.org/wiki/Робот"),
        ("робототехника", "https://ru.wikipedia.org/wiki/Робототехника"),
        ("сервисный робот", "https://ru.wikipedia.org/wiki/Сервисный_робот"),
        ("компьютерное зрение", "https://ru.wikipedia.org/wiki/Компьютерное_зрение"),
    ],
    'interactive': [
        ("мультимедиапроектор", "https://ru.wikipedia.org/wiki/Мультимедиапроектор"),
        ("дополненная реальность", "https://ru.wikipedia.org/wiki/Дополненная_реальность"),
        ("светодиодный экран", "https://ru.wikipedia.org/wiki/Светодиодный_экран"),
        ("освещение", "https://ru.wikipedia.org/wiki/Освещение"),
    ],
    'event': [
        ("фотография", "https://ru.wikipedia.org/wiki/Фотография"),
        ("фотосессия", "https://ru.wikipedia.org/wiki/Фотосессия"),
        ("освещение", "https://ru.wikipedia.org/wiki/Освещение"),
    ],
}

# --- Раскладка: домен -> (рубрика, тематический блок, № строк листа «Месяц 2») -
# Номера строк — колонка «№» в листе. У yellodigital.ru две строки: двойной анкор.
LAYOUT = [
    ("photoset-msk.ru",    "Аренда фотобудок в Москве",                        'photobooth',  [4]),
    ("pre100l.ru",         "Фотобудки на мероприятиях в Москве",               'photobooth',  [6]),
    ("solkmsb.ru",         "Фотобудки в аренду на праздники",            'photobooth',  [8]),
    ("2semechki.ru",       "Event-фото в Москве",              'photobooth',  [10]),
    ("promplo.ru",         "Фотобудки с нейросетями",                          'ai',          [12]),
    ("elintel.ru",         "Искусственный интеллект в event-фотографии",       'ai',          [14]),
    ("dubrovinaphoto.com", "Аренда фотобудок в Екатеринбурге",                 'photobooth',  [15]),
    ("m-e-d-a-l.ru",       "Фотобудки для корпоративов в Екатеринбурге",       'photobooth',  [13]),
    ("sibertek.ru",        "Фотобудки в Екатеринбурге",'photobooth',  [17]),
    ("vsenamag.ru",        "Фотобудка на праздник в Екатеринбурге",            'photobooth',  [19]),
    ("ledpnz.ru",          "Неоновые фотозоны и LED-room",                     'led',         [2]),
    ("colorit-dv.ru",      "Угловые LED-фотозоны в Екатеринбурге",             'led',         [3]),
    ("studio-santech.ru",  "LED-фотозоны на мероприятиях в Екатеринбурге",     'led',         [5]),
    ("pro-covers.ru",      "Светодиодные фотозоны",       'led',         [7]),
    ("solbrasil.ru",       "Аренда светодиодных фотозон в Екатеринбурге",      'led',         [9]),
    ("yarfido.ru",         "Проекционные фотозоны и медиаконтент",             'led',         [11]),
    ("yellodigital.ru",    "Роботы на мероприятиях",                           'robots',      [20, 16]),
    ("avtogear62.ru",      "Аренда роботов для event-проектов",                'robots',      [18]),
    ("mybabyfoot.ru",      "Роботы-официанты на праздниках",                   'robots',      [22]),
    ("oybox.by",           "Роботы в аренду в Москве",                         'robots',      [24]),
    ("iscar-east.ru",      "Светодиодные экраны на мероприятиях в Екатеринбурге", 'interactive', [21]),
    ("edhall.ru",          "Визуальные интерактивы на событиях",               'interactive', [23]),
    ("pravo-or.org",       "Интерактивные форматы на мероприятиях в Москве",   'interactive', [25]),
    ("centr-audita.ru",    "Фотозоны на день рождения в Екатеринбурге",        'event',       [1]),
]


def cap(s: str) -> str:
    return s[0].upper() + s[1:] if s else s


def topics(category: str, anchors: list[str]) -> list[tuple[str, str, int]]:
    """Список (тема, слот, индекс анкора). Слоты: no / trust / client."""
    rows = [
        (f"{category}: что изменилось в 2026 году", 'no', -1),
        (f"{category}: оборудование, софт и расходники", 'trust', -1),
        (f"{cap(anchors[0])}: как выбрать подрядчика и не переплатить", 'client', 0),
        (f"{category}: разбор реальных кейсов", 'no', -1),
        (f"{category}: площадка, электрика и безопасность", 'trust', -1),
    ]
    if len(anchors) > 1:
        rows.append((f"{cap(anchors[1])}: из чего складывается цена", 'client', 1))
    rows.append((f"{category}: частые ошибки заказчиков", 'no', -1))
    return rows


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--anchors', default='month2.json',
                   help='JSON листа «Месяц 2» (поля №, Анкор, URL)')
    p.add_argument('--sites', default='campaign4_sites.json')
    p.add_argument('--out', default='content_plan_campaign4.csv')
    p.add_argument('--seed', type=int, default=4)
    args = p.parse_args()

    random.seed(args.seed)

    anchors = {int(r['№']): (r['Анкор'], r['URL']) for r in
               json.load(open(args.anchors, encoding='utf-8'))}
    site_ids = {s['domain']: s['id'] for s in json.load(open(args.sites, encoding='utf-8'))}

    if len(anchors) != 25:
        raise SystemExit(f"Ожидалось 25 анкоров, найдено {len(anchors)}")
    used = [n for _, _, _, nums in LAYOUT for n in nums]
    if sorted(used) != sorted(anchors):
        raise SystemExit(f"Раскладка покрывает {len(used)} анкоров из {len(anchors)}: "
                         f"пропущены {sorted(set(anchors) - set(used))}")
    missing = [d for d, _, _, _ in LAYOUT if d not in site_ids]
    if missing:
        raise SystemExit(f"Доноров нет в {args.sites}: {missing}")

    rows = [["Сайт", "Рубрика", "Тема статьи", "Анкор", "Ссылка", "Тип"]]
    for domain, category, theme, nums in LAYOUT:
        site_id = site_ids[domain]
        site_anchors = [anchors[n][0] for n in nums]
        site_urls = [anchors[n][1] for n in nums]
        trusts = iter(random.sample(TRUST[theme], 2))

        for topic, slot, idx in topics(category, site_anchors):
            if slot == 'no':
                rows.append([site_id, category, topic, '', '', ''])
            elif slot == 'trust':
                t_anchor, t_url = next(trusts)
                rows.append([site_id, category, topic, t_anchor, t_url, 'траст'])
            else:
                rows.append([site_id, category, topic, site_anchors[idx],
                             site_urls[idx], 'анкор клиента'])

    with open(args.out, 'w', encoding='utf-8', newline='') as f:
        csv.writer(f, delimiter=';').writerows(rows)

    body = rows[1:]
    print(f"Готово: {args.out}, строк: {len(body)}")
    print(f"  Сайтов:          {len({r[0] for r in body})}")
    print(f"  Анкоров клиента: {sum(1 for r in body if r[5] == 'анкор клиента')}")
    print(f"  Траст-ссылок:    {sum(1 for r in body if r[5] == 'траст')}")
    print(f"  Без анкоров:     {sum(1 for r in body if r[5] == '')}")


if __name__ == "__main__":
    main()
