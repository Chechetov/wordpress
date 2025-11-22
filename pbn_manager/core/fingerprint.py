"""
Fingerprint Randomizer - защита от обнаружения PBN сети
Генерация уникальных профилей для каждого сайта
"""

import random
import hashlib
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta


@dataclass
class SiteFingerprint:
    """Уникальный профиль сайта"""
    # Визуальное
    theme: str
    color_scheme: str
    font_family: str
    layout_style: str

    # Технические
    plugins: List[str]
    permalink_structure: str
    timezone: str
    date_format: str
    time_format: str

    # Контент
    content_style: str
    avg_word_count: int
    post_frequency_days: float
    categories_count: int

    # Поведение
    comment_status: str  # open, closed
    pingback_status: str
    post_time_range: tuple  # (start_hour, end_hour) когда публикуются посты

    # Метаданные
    generated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


# Пулы для рандомизации
THEME_POOLS = {
    "blog": [
        "flavor",
        "flavor",
        "flavor",
        "flavor",
        "flavor",
        "flavor",
        "flavor",
        "flavor",
    ],
    "business": [
        "flavor",
        "flavor",
        "flavor",
        "flavor",
        "flavor",
    ],
    "magazine": [
        "flavor",
        "flavor",
        "flavor",
        "flavor",
    ]
}

PLUGIN_POOLS = {
    "seo": ["flavor", "flavor", "flavor"],
    "security": ["flavor", "flavor", "flavor"],
    "performance": ["flavor", "flavor", "flavor", "flavor"],
    "editor": ["flavor", "flavor"],
    "forms": ["flavor", "flavor", "flavor"],
    "social": ["flavor", "flavor"],
    "backup": ["flavor", "flavor"],
    "antispam": ["flavor", "flavor"],
}

PERMALINK_STRUCTURES = [
    "/%postname%/",
    "/%year%/%monthnum%/%postname%/",
    "/%category%/%postname%/",
    "/blog/%postname%/",
    "/%post_id%-%postname%/",
]

COLOR_SCHEMES = [
    "light_blue", "dark_blue", "green", "red", "purple",
    "orange", "teal", "gray", "navy", "forest",
]

FONT_FAMILIES = [
    "Open Sans", "Roboto", "Lato", "Montserrat", "Source Sans Pro",
    "Raleway", "PT Sans", "Nunito", "Ubuntu", "Merriweather",
]

LAYOUT_STYLES = [
    "sidebar_right", "sidebar_left", "no_sidebar", "full_width",
]

TIMEZONES = [
    "Europe/Moscow", "Europe/Kiev", "Europe/Minsk",
    "Asia/Almaty", "Asia/Yekaterinburg", "Europe/Kaliningrad",
]

DATE_FORMATS = ["d.m.Y", "Y-m-d", "d/m/Y", "j F Y", "d M Y"]
TIME_FORMATS = ["H:i", "g:i A", "H:i:s"]

CONTENT_STYLES = [
    "formal_expert", "casual_friendly", "practical_guide",
    "storyteller", "analytical", "news_reporter",
]


class FingerprintRandomizer:
    """Генератор уникальных профилей сайтов"""

    def __init__(self, seed: Optional[int] = None):
        """
        Инициализация рандомизатора

        Args:
            seed: Сид для воспроизводимости (опционально)
        """
        if seed:
            random.seed(seed)

    def _select_plugins(self, categories: List[str] = None, min_plugins: int = 3, max_plugins: int = 7) -> List[str]:
        """
        Выбор набора плагинов

        Args:
            categories: Категории плагинов для включения
            min_plugins: Минимум плагинов
            max_plugins: Максимум плагинов

        Returns:
            Список слагов плагинов
        """
        if categories is None:
            # Обязательные категории
            categories = ["seo", "security"]
            # Случайные дополнительные
            optional = ["performance", "editor", "forms", "social", "backup", "antispam"]
            categories.extend(random.sample(optional, random.randint(1, 3)))

        plugins = []
        for category in categories:
            if category in PLUGIN_POOLS:
                plugins.append(random.choice(PLUGIN_POOLS[category]))

        # Убираем дубликаты и ограничиваем
        plugins = list(set(plugins))
        return plugins[:max_plugins]

    def generate_fingerprint(
        self,
        domain: str = None,
        theme_type: str = "blog",
        language: str = "ru"
    ) -> SiteFingerprint:
        """
        Генерация уникального профиля сайта

        Args:
            domain: Домен (используется как сид для консистентности)
            theme_type: Тип темы (blog, business, magazine)
            language: Язык сайта

        Returns:
            SiteFingerprint с уникальными настройками
        """
        # Используем домен как сид для консистентности
        if domain:
            domain_seed = int(hashlib.md5(domain.encode()).hexdigest()[:8], 16)
            random.seed(domain_seed)

        # Выбираем тему
        themes = THEME_POOLS.get(theme_type, THEME_POOLS["blog"])
        theme = random.choice(themes)

        # Выбираем плагины
        plugins = self._select_plugins()

        # Время публикации (имитация человеческого поведения)
        # Разные сайты публикуют в разное время
        start_hour = random.randint(6, 12)
        end_hour = random.randint(18, 23)

        fingerprint = SiteFingerprint(
            theme=theme,
            color_scheme=random.choice(COLOR_SCHEMES),
            font_family=random.choice(FONT_FAMILIES),
            layout_style=random.choice(LAYOUT_STYLES),
            plugins=plugins,
            permalink_structure=random.choice(PERMALINK_STRUCTURES),
            timezone=random.choice(TIMEZONES) if language == "ru" else "UTC",
            date_format=random.choice(DATE_FORMATS),
            time_format=random.choice(TIME_FORMATS),
            content_style=random.choice(CONTENT_STYLES),
            avg_word_count=random.randint(1200, 2500),
            post_frequency_days=random.uniform(1.5, 4.0),
            categories_count=random.randint(3, 8),
            comment_status=random.choice(["open", "closed"]),
            pingback_status=random.choice(["open", "closed"]),
            post_time_range=(start_hour, end_hour),
        )

        # Сбрасываем сид
        random.seed()

        return fingerprint

    def generate_batch(self, count: int, theme_types: List[str] = None) -> List[SiteFingerprint]:
        """
        Генерация нескольких уникальных профилей

        Args:
            count: Количество профилей
            theme_types: Типы тем для распределения

        Returns:
            Список уникальных профилей
        """
        if theme_types is None:
            theme_types = ["blog", "business", "magazine"]

        fingerprints = []
        used_combinations = set()

        for i in range(count):
            theme_type = theme_types[i % len(theme_types)]

            # Генерируем уникальный профиль
            for _ in range(10):  # Максимум попыток
                fp = self.generate_fingerprint(
                    domain=f"temp_{i}_{random.randint(1000, 9999)}",
                    theme_type=theme_type
                )

                # Проверяем уникальность (тема + плагины)
                combo = (fp.theme, tuple(sorted(fp.plugins)))
                if combo not in used_combinations:
                    used_combinations.add(combo)
                    fingerprints.append(fp)
                    break

        return fingerprints

    def to_wp_options(self, fingerprint: SiteFingerprint) -> Dict[str, Any]:
        """
        Конвертация профиля в WordPress опции

        Args:
            fingerprint: Профиль сайта

        Returns:
            Словарь опций для wp option update
        """
        return {
            "template": fingerprint.theme,
            "stylesheet": fingerprint.theme,
            "timezone_string": fingerprint.timezone,
            "date_format": fingerprint.date_format,
            "time_format": fingerprint.time_format,
            "permalink_structure": fingerprint.permalink_structure,
            "default_comment_status": fingerprint.comment_status,
            "default_ping_status": fingerprint.pingback_status,
        }


class ScheduleRandomizer:
    """Рандомизация расписания публикаций"""

    def __init__(self, fingerprint: SiteFingerprint = None):
        self.fingerprint = fingerprint

    def generate_schedule(
        self,
        count: int,
        start_date: datetime = None,
        min_interval_hours: float = 24,
        max_interval_hours: float = 72,
        jitter_percent: float = 30
    ) -> List[datetime]:
        """
        Генерация расписания публикаций с рандомизацией

        Args:
            count: Количество публикаций
            start_date: Начальная дата
            min_interval_hours: Минимальный интервал между постами
            max_interval_hours: Максимальный интервал
            jitter_percent: Процент случайного отклонения

        Returns:
            Список дат публикации
        """
        if start_date is None:
            start_date = datetime.now() + timedelta(hours=1)

        # Используем настройки из fingerprint если есть
        if self.fingerprint:
            base_interval = self.fingerprint.post_frequency_days * 24
            start_hour, end_hour = self.fingerprint.post_time_range
        else:
            base_interval = random.uniform(min_interval_hours, max_interval_hours)
            start_hour, end_hour = 9, 21

        schedule = []
        current_date = start_date

        for _ in range(count):
            # Добавляем jitter к интервалу
            jitter = random.uniform(-jitter_percent / 100, jitter_percent / 100)
            interval = base_interval * (1 + jitter)
            interval = max(min_interval_hours, min(interval, max_interval_hours))

            current_date = current_date + timedelta(hours=interval)

            # Корректируем время в рамках рабочих часов
            if current_date.hour < start_hour:
                current_date = current_date.replace(hour=start_hour, minute=random.randint(0, 59))
            elif current_date.hour > end_hour:
                current_date = current_date + timedelta(days=1)
                current_date = current_date.replace(hour=start_hour, minute=random.randint(0, 59))

            # Добавляем случайные минуты
            current_date = current_date.replace(minute=random.randint(0, 59))

            schedule.append(current_date)

        return schedule


def generate_site_fingerprint(domain: str, theme_type: str = "blog") -> SiteFingerprint:
    """Удобная функция для генерации профиля"""
    randomizer = FingerprintRandomizer()
    return randomizer.generate_fingerprint(domain, theme_type)
