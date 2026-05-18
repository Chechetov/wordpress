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
