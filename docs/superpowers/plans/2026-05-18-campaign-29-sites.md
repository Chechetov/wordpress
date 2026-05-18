# Кампания «29 сайтов × 6 статей» — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Опубликовать на 29 новых сайтах по 6 статей (174 статьи) с расписанием, продолжающим таймлайн прошлой кампании, и бэкдейтингом прошедших дат.

**Architecture:** Логика расписания выносится в отдельный модуль `schedule_builder.py` (чистые функции, тестируются изолированно). `publish_all.py` дорабатывается: импортирует расписание, принимает `--sites-file`, выбирает статус `publish`/`future` по дате, прогоняет сайты параллельно через пул потоков (`--workers`). Данные кампании — `campaign2_sites.json` (29 сайтов) и новый `content_plan.csv` (174 строки).

**Tech Stack:** Python 3, `requests`, `python-dotenv`, OpenAI API (текст), Google Imagen (обложки), WordPress REST API.

**Спецификация:** `docs/superpowers/specs/2026-05-18-campaign-30-sites-design.md`

---

## File Structure

- **Create** `schedule_builder.py` — `REF_DATE`, `build_schedule()`, `pick_status()`. Чистая логика, без сетевых вызовов.
- **Create** `test_schedule.py` — тесты `schedule_builder`, запуск `python test_schedule.py`.
- **Create** `campaign2_sites.json` — конфиг 29 новых сайтов (НЕ коммитится — содержит пароли).
- **Create** `content_plan.csv` — 174 строки контент-плана (старый переименовывается в `content_plan_campaign1.csv`).
- **Modify** `publish_all.py` — импорт `schedule_builder`, аргумент `--sites-file`, статус по дате, маркеры в dry-run, параллельный прогон по сайтам (`--workers`).
- **Modify** `.gitignore` — добавить `campaign2_sites.json` и `sites.json`.

---

## Task 1: Конфиг 29 новых сайтов

**Files:**
- Create: `campaign2_sites.json`
- Modify: `.gitignore`

Заказчик прислал 49 сайтов; 20 — из прошлой кампании (есть в `sites.json`), 29 — новые. Список сохранён в `/tmp/sites_raw.txt` (формат: `username<TAB>password<TAB>domain`). Кампания — только на 29 новых.

- [ ] **Step 1: Защитить пароли от попадания в git**

Добавить в конец `.gitignore`:

```
sites.json
campaign2_sites.json
```

- [ ] **Step 2: Сгенерировать `campaign2_sites.json`**

Запустить:

```python
python3 - <<'PY'
import json, re
old = {s['domain'] for s in json.load(open('sites.json'))}
sites, sid = [], 1
for line in open('/tmp/sites_raw.txt', encoding='utf-8'):
    line = line.strip()
    if not line:
        continue
    user, pw, dom = re.split(r'\t+|\s{2,}', line)
    if dom in old:                       # пропустить 20 старых сайтов
        continue
    sites.append({'id': sid, 'domain': dom, 'url': f'https://{dom}',
                  'username': user, 'password': pw})
    sid += 1
json.dump(sites, open('campaign2_sites.json', 'w', encoding='utf-8'),
          ensure_ascii=False, indent=2)
print(f'{len(sites)} сайтов записано в campaign2_sites.json')
PY
```

Expected: `29 сайтов записано в campaign2_sites.json`

- [ ] **Step 3: Проверить конфиг**

```python
python3 - <<'PY'
import json
old = {s['domain'] for s in json.load(open('sites.json'))}
c = json.load(open('campaign2_sites.json'))
assert len(c) == 29, len(c)
assert [s['id'] for s in c] == list(range(1, 30))
for s in c:
    assert set(s) == {'id', 'domain', 'url', 'username', 'password'}, s
    assert s['domain'] not in old, s['domain']
    assert all(s.values())
print('campaign2_sites.json OK: 29 новых сайтов, id 1-29')
PY
```

Expected: `campaign2_sites.json OK: 29 новых сайтов, id 1-29`

- [ ] **Step 4: Commit** (только `.gitignore` — `campaign2_sites.json` игнорируется)

```bash
git add .gitignore
git commit -m "chore: игнорировать файлы с паролями сайтов"
```

---

## Task 2: Модуль расписания `schedule_builder.py`

**Files:**
- Create: `schedule_builder.py`
- Test: `test_schedule.py`

Расписание продолжает таймлайн прошлой кампании. Опорная точка — последний анкор прошлого захода `2026-04-22 16:53` (`reports/anchors_audit.md`). Старт каждого сайта смещён на 28–52 ч относительно предыдущего; внутри сайта 6 статей идут с интервалом 28–52 ч; время суток 8:00–21:00.

- [ ] **Step 1: Написать тесты `test_schedule.py`**

```python
"""Тесты schedule_builder. Запуск: python test_schedule.py"""
from datetime import datetime, timedelta
from schedule_builder import REF_DATE, build_schedule, pick_status


def test_ref_date():
    assert REF_DATE == datetime(2026, 4, 22, 16, 53)


def test_count_and_shape():
    sched = build_schedule(29)
    assert len(sched) == 29
    for i in range(29):
        assert len(sched[i]) == 6


def test_all_dates_after_ref():
    sched = build_schedule(29)
    for i in range(29):
        for dt in sched[i]:
            assert dt > REF_DATE


def test_articles_monotonic():
    sched = build_schedule(29)
    for i in range(29):
        days = sched[i]
        for k in range(1, 6):
            assert days[k] > days[k - 1]


def test_within_site_gap_about_1_2_days():
    sched = build_schedule(29)
    for i in range(29):
        days = sched[i]
        for k in range(1, 6):
            gap_h = (days[k] - days[k - 1]).total_seconds() / 3600
            assert 11 <= gap_h <= 62, gap_h


def test_site_starts_staggered():
    sched = build_schedule(29)
    for i in range(1, 29):
        assert sched[i][0] > sched[i - 1][0]


def test_hours_in_daytime():
    sched = build_schedule(29)
    for i in range(29):
        for dt in sched[i]:
            assert 8 <= dt.hour <= 21


def test_pick_status():
    assert pick_status(REF_DATE) == 'publish'
    assert pick_status(datetime.now() - timedelta(days=1)) == 'publish'
    assert pick_status(datetime.now() + timedelta(days=10)) == 'future'


if __name__ == '__main__':
    import sys
    tests = [v for k, v in sorted(globals().items()) if k.startswith('test_')]
    failed = 0
    for t in tests:
        try:
            t()
            print(f'PASS {t.__name__}')
        except AssertionError as e:
            failed += 1
            print(f'FAIL {t.__name__}: {e}')
    sys.exit(1 if failed else 0)
```

- [ ] **Step 2: Запустить тесты — убедиться, что падают**

Run: `python test_schedule.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'schedule_builder'`

- [ ] **Step 3: Реализовать `schedule_builder.py`**

```python
"""Построение расписания публикаций для кампании №2.

Расписание продолжает таймлайн прошлой кампании: отсчёт от REF_DATE,
старты сайтов смещены на 1-2 дня, внутри сайта статьи идут с интервалом
1-2 дня. Время суток 8:00-21:00.
"""
import random
from datetime import datetime, timedelta

# Последний анкор прошлой кампании (reports/anchors_audit.md)
REF_DATE = datetime(2026, 4, 22, 16, 53)


def _normalize_time(dt):
    """Время суток 8:00-21:00, минуты случайные, секунды обнулены."""
    return dt.replace(hour=random.randint(8, 21),
                      minute=random.randint(5, 55),
                      second=0, microsecond=0)


def build_schedule(num_sites, articles_per_site=6):
    """Расписание для num_sites сайтов.

    Возвращает {site_index: [datetime, ...]} — по articles_per_site дат.
    Старт сайта смещён на 1-2 дня относительно старта предыдущего;
    внутри сайта статьи разнесены на 1-2 календарных дня.
    """
    schedules = {}
    site_start = REF_DATE
    for i in range(num_sites):
        site_start = site_start + timedelta(days=random.randint(1, 2))
        cursor = site_start
        site_schedule = []
        for _ in range(articles_per_site):
            site_schedule.append(_normalize_time(cursor))
            cursor = cursor + timedelta(days=random.randint(1, 2))
        schedules[i] = site_schedule
    return schedules


def pick_status(pub_time, now=None):
    """'publish' для прошедшей даты (бэкдейт), 'future' для будущей."""
    now = now or datetime.now()
    return 'publish' if pub_time <= now else 'future'
```

- [ ] **Step 4: Запустить тесты — убедиться, что проходят**

Run: `python test_schedule.py`
Expected: 7 строк `PASS ...`, код выхода 0

- [ ] **Step 5: Commit**

```bash
git add schedule_builder.py test_schedule.py
git commit -m "feat: модуль расписания кампании от таймлайна прошлого захода"
```

---

## Task 3: Контент-план `content_plan.csv` (174 строки)

**Files:**
- Create: `content_plan.csv` (старый переименовывается)

Формат (разделитель `;`): `Сайт;Рубрика;Тема статьи;Анкор;Ссылка;Тип`

**Привязка анкоров к сайтам (id 1-29):**

| id | Город | Анкор | Целевая ссылка |
|----|-------|-------|----------------|
| 1 | Красноярск | лаборант химического анализа обучение | https://aso-cdo.ru/krasnoyarsk/rabochie-professii/laborant-himicheskogo-analiza/ |
| 2 | Красноярск | профессиональная переподготовка | https://aso-cdo.ru/krasnoyarsk/professionalnaya-perepodgotovka/ |
| 3 | Красноярск | лаборант химического анализа обучение красноярск | https://aso-cdo.ru/krasnoyarsk/rabochie-professii/laborant-himicheskogo-analiza/ |
| 4 | Красноярск | обучение по охране труда красноярск | https://aso-cdo.ru/krasnoyarsk/obuchenie-po-ohrane-truda/ |
| 5 | Красноярск | электрогазосварщик обучение красноярск | https://aso-cdo.ru/krasnoyarsk/rabochie-professii/elektrogazosvarshhik/ |
| 6 | Красноярск | обучение на дезинфектора дистанционно | https://aso-cdo.ru/krasnoyarsk/rabochie-professii/mediczinskij-dezinfektor/ |
| 7 | Красноярск | обучение рабочим профессиям | https://aso-cdo.ru/krasnoyarsk/rabochie-professii/ |
| 8 | Красноярск | обучение на водителя погрузчика | https://aso-cdo.ru/krasnoyarsk/rabochie-professii/voditel-pogruzchika/ |
| 9 | Красноярск | обучение по охране труда красноярск | https://aso-cdo.ru/krasnoyarsk/obuchenie-po-ohrane-truda/ |
| 10 | Красноярск | оценщик недвижимости обучение | https://aso-cdo.ru/krasnoyarsk/professionalnaya-perepodgotovka/ocenochnaya-deyatelnost-pp/oczenka-nedvizhimosti/ |
| 11 | Москва | отучиться на погрузчик в москве | https://aso-cdo.ru/moskva/rabochie-professii/voditel-pogruzchika/ |
| 12 | Москва | дистанционное обучение водитель погрузчика | https://aso-cdo.ru/moskva/rabochie-professii/voditel-pogruzchika/ |
| 13 | Москва | обучение на водителя погрузчика в москве | https://aso-cdo.ru/moskva/rabochie-professii/voditel-pogruzchika/ |
| 14 | Москва | дистанционное обучение на погрузчик | https://aso-cdo.ru/moskva/rabochie-professii/voditel-pogruzchika/ |
| 15 | Москва | курсы водителя погрузчика в москве | https://aso-cdo.ru/moskva/rabochie-professii/voditel-pogruzchika/ |
| 16 | Москва | обучение на водителя погрузчика в москве цена | https://aso-cdo.ru/moskva/rabochie-professii/voditel-pogruzchika/ |
| 17 | Москва | обучение на погрузчик в москве цена | https://aso-cdo.ru/moskva/rabochie-professii/voditel-pogruzchika/ |
| 18 | Москва | учиться на водителя погрузчика в москве | https://aso-cdo.ru/moskva/rabochie-professii/voditel-pogruzchika/ |
| 19 | Москва | https://aso-cdo.ru/moskva/rabochie-professii/voditel-pogruzchika/ | https://aso-cdo.ru/moskva/rabochie-professii/voditel-pogruzchika/ |
| 20 | Тюмень | профпереподготовка в Тюмени | https://aso-cdo.ru/tyumen/professionalnaya-perepodgotovka/ |
| 21 | Тюмень | профессиональная переподготовка | https://aso-cdo.ru/tyumen/professionalnaya-perepodgotovka/ |
| 22 | Тюмень | профессиональная переподготовка в Тюмени | https://aso-cdo.ru/tyumen/professionalnaya-perepodgotovka/ |
| 23 | Тюмень | переподготовка на базе высшего образования в Тюмени | https://aso-cdo.ru/tyumen/professionalnaya-perepodgotovka/ |
| 24 | Тюмень | переподготовка | https://aso-cdo.ru/tyumen/professionalnaya-perepodgotovka/ |
| 25 | Тюмень | курсы профессиональной переподготовки | https://aso-cdo.ru/tyumen/professionalnaya-perepodgotovka/ |
| 26 | Тюмень | курсы переподготовки | https://aso-cdo.ru/tyumen/professionalnaya-perepodgotovka/ |
| 27 | Тюмень | курсы переподготовки в Тюмени | https://aso-cdo.ru/tyumen/professionalnaya-perepodgotovka/ |
| 28 | Тюмень | проф переподготовка | https://aso-cdo.ru/tyumen/professionalnaya-perepodgotovka/ |
| 29 | Тюмень | профессиональная переподготовка | https://aso-cdo.ru/tyumen/professionalnaya-perepodgotovka/ |

**Правила формирования блока сайта (6 строк):**
- Одна `Рубрика` на сайт — уникальная, тематически под город и анкор (не повторять дословно у соседних сайтов).
- 6 статей в порядке публикации. Позиции (1-based): анкорная статья — случайно 2, 3 или 4; 2 трастовых и 3 тематических — по остальным позициям.
- **Анкорная** (`Тип`=`анкор клиента`): тема естественно раскрывает анкор; `Анкор` и `Ссылка` — из таблицы выше.
- **Трастовая** (`Тип`=`траст`): тема — смежная; `Анкор` — короткое слово/фраза, `Ссылка` — авторитетный ресурс из пула ниже, релевантный теме.
- **Тематическая** (`Тип` пустой): `Анкор` и `Ссылка` пустые.

**Пул трастовых ресурсов** (выбирать 2 на сайт по контексту): `ru.wikipedia.org` (тематическая статья), `rosstat.gov.ru` (Росстат), `mintrud.gov.ru` (Минтруд), `gosnadzor.ru` (Ростехнадзор), `mchs.gov.ru` (МЧС), `rospotrebnadzor.ru` (Роспотребнадзор), `minzdrav.gov.ru` (Минздрав), `profstandart.rosmintrud.ru` (профстандарты), `hh.ru` (HeadHunter), `trudvsem.ru` (Работа России), `consultant.ru` (КонсультантПлюс), `obrnadzor.gov.ru` (Рособрнадзор).

- [ ] **Step 1: Сохранить старый контент-план**

```bash
git mv content_plan.csv content_plan_campaign1.csv 2>/dev/null || mv content_plan.csv content_plan_campaign1.csv
```

- [ ] **Step 2: Создать новый `content_plan.csv`**

Заголовок: `Сайт;Рубрика;Тема статьи;Анкор;Ссылка;Тип`

Авторски написать 29 блоков по 6 строк (174 строки данных) по правилам выше. Эталон — блок сайта 1 (анкорная статья на позиции 3, трастовые на 2 и 5):

```
1;Профессии и обучение в Красноярске;Рабочие профессии Красноярска: какие специальности можно освоить с нуля;;;
1;Профессии и обучение в Красноярске;Кто такой лаборант химического анализа и чем он занимается;химический анализ;https://ru.wikipedia.org/wiki/Химический_анализ;траст
1;Профессии и обучение в Красноярске;Лаборант химического анализа: как пройти обучение и начать карьеру;лаборант химического анализа обучение;https://aso-cdo.ru/krasnoyarsk/rabochie-professii/laborant-himicheskogo-analiza/;анкор клиента
1;Профессии и обучение в Красноярске;Где работают лаборанты химического анализа: отрасли и предприятия Красноярского края;;;
1;Профессии и обучение в Красноярске;Зарплаты рабочих специальностей в Красноярске: обзор рынка труда;Росстат;https://rosstat.gov.ru/;траст
1;Профессии и обучение в Красноярске;Как выбрать учебный центр для получения рабочей профессии;;;
```

Для сайтов 11-19 (Москва, все про водителя погрузчика) и 20-29 (Тюмень, все про профпереподготовку) разнообразить темы статей и рубрики, чтобы блоки не были одинаковыми. Для сайта 19 анкор — «голый» URL: в столбце `Анкор` указать сам URL `https://aso-cdo.ru/moskva/rabochie-professii/voditel-pogruzchika/`.

- [ ] **Step 3: Проверить структуру**

```python
python3 - <<'PY'
import csv
from collections import defaultdict
rows = list(csv.DictReader(open('content_plan.csv', encoding='utf-8'), delimiter=';'))
assert len(rows) == 174, len(rows)
by_site = defaultdict(list)
for r in rows:
    by_site[int(r['Сайт'])].append(r)
assert sorted(by_site) == list(range(1, 30)), sorted(by_site)
for sid, arts in by_site.items():
    assert len(arts) == 6, (sid, len(arts))
    types = [a['Тип'] for a in arts]
    assert types.count('анкор клиента') == 1, (sid, types)
    assert types.count('траст') == 2, (sid, types)
    assert types.count('') == 3, (sid, types)
    pos = [i for i, a in enumerate(arts) if a['Тип'] == 'анкор клиента'][0]
    assert pos in (1, 2, 3), (sid, 'анкор на позиции', pos + 1)
print('content_plan.csv OK: 174 строки, 29 сайтов, структура верна')
PY
```

Expected: `content_plan.csv OK: 174 строки, 29 сайтов, структура верна`

- [ ] **Step 4: Commit**

```bash
git add content_plan.csv content_plan_campaign1.csv
git commit -m "feat: контент-план кампании №2 (29 сайтов, 174 статьи)"
```

---

## Task 4: Доработка `publish_all.py`

**Files:**
- Modify: `publish_all.py`

- [ ] **Step 1: Подключить `schedule_builder`**

Заменить блок импортов:

```python
# Импорт модулей
from src.content_generator import ContentGenerator
from src.image_generator import ImageGenerator
```

на:

```python
# Импорт модулей
from src.content_generator import ContentGenerator
from src.image_generator import ImageGenerator
from schedule_builder import build_schedule, pick_status
```

- [ ] **Step 2: Удалить старую функцию `build_schedule`**

Удалить из `publish_all.py` всю функцию `build_schedule` целиком — от строки `def build_schedule(num_sites, articles_per_site=6):` до её завершающей строки `    return schedules` (вместе с docstring). Теперь используется импортированная версия.

- [ ] **Step 3: Добавить аргумент `--sites-file`**

Заменить:

```python
    parser = argparse.ArgumentParser(description='Мультисайтовая публикация статей')
    parser.add_argument('--site', type=str, help='ID сайтов через запятую (1,2,3)')
```

на:

```python
    parser = argparse.ArgumentParser(description='Мультисайтовая публикация статей')
    parser.add_argument('--sites-file', default='sites.json', help='JSON-файл с сайтами')
    parser.add_argument('--site', type=str, help='ID сайтов через запятую (1,2,3)')
```

- [ ] **Step 4: Использовать `--sites-file` при загрузке**

Заменить:

```python
    # Загрузка данных
    sites = load_sites()
    plan = load_content_plan()
```

на:

```python
    # Загрузка данных
    sites = load_sites(args.sites_file)
    plan = load_content_plan()
```

- [ ] **Step 5: Статус публикации по дате (бэкдейт / отложенная)**

В функции `publish_to_site`, в словаре `post_data`, заменить:

```python
                'status': 'future',
```

на:

```python
                'status': pick_status(pub_time),
```

- [ ] **Step 6: Маркер бэкдейт/отложенная в выводе расписания**

В `main()`, в блоке вывода расписания, заменить строку:

```python
                print(f"  {j+1}. {pub_time.strftime('%d.%m.%Y %H:%M')} — {article['topic']}{type_mark}")
```

на:

```python
                mark = 'задним числом' if pick_status(pub_time) == 'publish' else 'отложенная'
                print(f"  {j+1}. {pub_time.strftime('%d.%m.%Y %H:%M')} [{mark}] — {article['topic']}{type_mark}")
```

- [ ] **Step 7: Проверить, что расписание строится**

Run: `python publish_all.py --sites-file campaign2_sites.json --schedule-only`
Expected: вывод расписания 29 сайтов по 6 статей, у каждой пометка `[задним числом]` или `[отложенная]`, без ошибок и трейсбэков.

- [ ] **Step 8: Commit**

```bash
git add publish_all.py
git commit -m "feat: publish_all поддерживает --sites-file и бэкдейтинг по дате"
```

---

## Task 5: Параллельный прогон по сайтам

**Files:**
- Modify: `publish_all.py`

Последовательный прогон 174 статей — несколько часов. Распараллеливаем по сайтам: пул потоков обрабатывает несколько сайтов одновременно, в каждом потоке идёт своя генерация текста и обложек. Расписание считается один раз глобально (`build_schedule(len(sites))`) — порядок дат не меняется. SDK-клиенты OpenAI/Imagen потокобезопасны для конкурентных запросов; при ошибках rate limit достаточно снизить `--workers`.

- [ ] **Step 1: Импорт и аргумент `--workers`**

Добавить в блок импортов `publish_all.py` строку (после `from dotenv import load_dotenv`):

```python
from concurrent.futures import ThreadPoolExecutor, as_completed
```

В `main()` добавить аргумент перед `args = parser.parse_args()`:

```python
    parser.add_argument('--workers', type=int, default=5,
                        help='Сколько сайтов обрабатывать параллельно')
```

- [ ] **Step 2: Заменить последовательный цикл публикации на пул потоков**

Заменить блок:

```python
    # Публикация
    all_results = []
    for idx, site in enumerate(sites):
        site_id = site['id']
        if site_id not in plan:
            logger.warning(f"Нет плана для сайта #{site_id} ({site['domain']})")
            continue

        logger.info(f"\n{'='*60}")
        logger.info(f"Сайт #{site_id}: {site['domain']}")
        logger.info(f"{'='*60}")

        results = publish_to_site(
            site_config=site,
            articles=plan[site_id],
            schedule=schedules[idx],
            content_gen=content_gen,
            image_gen=image_gen,
            dry_run=args.dry_run
        )
        all_results.extend(results)

        # Пауза между сайтами
        if idx < len(sites) - 1:
            logger.info("Пауза 5 сек перед следующим сайтом...")
            time.sleep(5)
```

на:

```python
    # Публикация — параллельно по сайтам
    jobs = []
    for idx, site in enumerate(sites):
        if site['id'] not in plan:
            logger.warning(f"Нет плана для сайта #{site['id']} ({site['domain']})")
            continue
        jobs.append((idx, site))

    logger.info(f"Параллельная публикация: {len(jobs)} сайтов, "
                f"{args.workers} потоков")

    all_results = []
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(publish_to_site, site, plan[site['id']],
                            schedules[idx], content_gen, image_gen,
                            args.dry_run): site['domain']
            for idx, site in jobs
        }
        for future in as_completed(futures):
            domain = futures[future]
            try:
                all_results.extend(future.result())
                logger.info(f"[{domain}] сайт завершён")
            except Exception as e:
                logger.error(f"[{domain}] сбой обработки сайта: {e}")
```

- [ ] **Step 3: Проверка**

Run: `python publish_all.py --help`
Expected: в выводе присутствует `--workers`.

Run: `python publish_all.py --sites-file campaign2_sites.json --dry-run`
Expected: печатается расписание и `[DRY RUN] Публикация не выполнялась.`, без трейсбэков (пул потоков в dry-run не задействуется — `main()` выходит раньше).

- [ ] **Step 4: Commit**

```bash
git add publish_all.py
git commit -m "feat: параллельная публикация по сайтам (--workers)"
```

---

## Task 6: Предпросмотр расписания и согласование (ГЕЙТ)

**Files:** нет (только проверка и согласование)

- [ ] **Step 1: Полный dry-run**

Run: `python publish_all.py --sites-file campaign2_sites.json --dry-run`
Expected: расписание всех 174 статей, без публикации.

- [ ] **Step 2: Сводка по расписанию**

```python
python3 - <<'PY'
import json
from schedule_builder import build_schedule, pick_status
sched = build_schedule(29)
back = fut = 0
first = last = None
for i in range(29):
    for dt in sched[i]:
        if pick_status(dt) == 'publish':
            back += 1
        else:
            fut += 1
        first = dt if first is None or dt < first else first
        last = dt if last is None or dt > last else last
print(f'Всего статей: {back + fut}')
print(f'Задним числом (publish): {back}')
print(f'Отложенных (future):     {fut}')
print(f'Окно кампании: {first:%d.%m.%Y} - {last:%d.%m.%Y}')
PY
```

- [ ] **Step 3: СТОП — согласование с заказчиком**

Показать заказчику: сводку расписания (Step 2), окно кампании, число бэкдейт/отложенных, и `content_plan.csv` (рубрики + темы). **Не переходить к Task 7 без явного «запускай».**

---

## Task 7: Реальный запуск публикации

**Files:** нет (запуск + проверка)

⚠️ Выполнять только после явного согласования в Task 6. Запуск создаёт 174 статьи через платные API (OpenAI, Imagen) и публикует на 29 живых сайтов; бэкдейт-статьи становятся видимыми сразу.

- [ ] **Step 1: Проверить ключи API**

```bash
grep -E 'OPENAI_API_KEY|GOOGLE_API_KEY' .env
```

Expected: обе переменные присутствуют и непустые.

- [ ] **Step 2: Запуск в фоне**

Run (в фоне — прогон длительный): `python publish_all.py --sites-file campaign2_sites.json --workers 5`

При ошибках rate limit от OpenAI/Imagen перезапустить с меньшим `--workers`; при стабильной работе можно поднять до 8–10 для ускорения.

- [ ] **Step 3: Контроль выполнения**

Следить за свежим логом `logs/publish_all_*.log`. Дождаться итоговой строки `ИТОГО: N/174 статей запланировано`.

- [ ] **Step 4: Проверить отчёт**

```python
python3 - <<'PY'
import json, glob, os
rep = max(glob.glob('reports/publish_all_*.json'), key=os.path.getmtime)
data = json.load(open(rep))
ok = sum(1 for r in data if r['status'] == 'success')
err = sum(1 for r in data if r['status'] == 'error')
print(f'Отчёт: {rep}')
print(f'Успешно: {ok} / {len(data)}   Ошибок: {err}')
for r in data:
    if r['status'] == 'error':
        print(f"  ОШИБКА {r['domain']} | {r['topic'][:40]} | {r.get('error','')[:120]}")
PY
```

Expected: `Успешно: 174 / 174   Ошибок: 0` (либо разобрать перечисленные ошибки).

- [ ] **Step 5: Доложить итог заказчику** — число опубликованных статей, ошибки (если есть), путь к отчёту.

---

## Self-Review

- **Покрытие спеки:** структура контента (Task 3), привязка анкоров (Task 3, таблица), расписание от таймлайна + бэкдейтинг (Task 2, 4), исключение дубля Москвы (Task 3, сайтов 19 вместо 20 московских), `--sites-file` (Task 4), dry-run с пометками (Task 4, 6), запуск (Task 7) — покрыто. Параллельный прогон (Task 5) — добавлен сверх спеки по запросу заказчика для ускорения, на дизайн расписания не влияет.
- **Плейсхолдеры:** код приведён полностью; `content_plan.csv` авторски пишется по правилам + эталонный блок — для контентного файла это деливерабл задачи, не плейсхолдер.
- **Согласованность типов:** `build_schedule(num_sites, articles_per_site=6)` и `pick_status(pub_time, now=None)` — сигнатуры совпадают в `schedule_builder.py`, `test_schedule.py`, `publish_all.py`.
