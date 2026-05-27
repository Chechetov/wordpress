"""Построение расписания публикаций.

По умолчанию (кампания №2) расписание продолжает таймлайн прошлой кампании
от REF_DATE. Параметризовано для кампании №3: можно задать start_date и
шаги между сайтами/статьями, чтобы уместить 25 сайтов в 2-3 недели.
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


def build_schedule(num_sites, articles_per_site=6,
                   start_date=None,
                   site_step=(1, 2),
                   article_step=(1, 2)):
    """Расписание для num_sites сайтов.

    Возвращает {site_index: [datetime, ...]} — по articles_per_site дат.

    Args:
        start_date: точка отсчёта (по умолчанию REF_DATE).
        site_step: диапазон сдвига (в днях) между стартами соседних сайтов.
        article_step: диапазон между статьями внутри сайта.
    """
    if start_date is None:
        start_date = REF_DATE
    site_lo, site_hi = site_step
    art_lo, art_hi = article_step

    schedules = {}
    site_start = start_date
    for i in range(num_sites):
        site_start = site_start + timedelta(days=random.randint(site_lo, site_hi))
        cursor = site_start
        site_schedule = []
        for _ in range(articles_per_site):
            site_schedule.append(_normalize_time(cursor))
            cursor = cursor + timedelta(days=random.randint(art_lo, art_hi))
        schedules[i] = site_schedule
    return schedules


def pick_status(pub_time, now=None):
    """'publish' для прошедшей даты (бэкдейт), 'future' для будущей."""
    now = now or datetime.now()
    return 'publish' if pub_time <= now else 'future'
