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
