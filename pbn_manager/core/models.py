"""
Модели данных для PBN Manager
SQLAlchemy ORM модели
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import create_engine, Column, Integer, String, Text, Boolean, DateTime, Float, ForeignKey, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker

Base = declarative_base()


class Site(Base):
    """Модель сайта в PBN сети"""
    __tablename__ = "sites"

    id = Column(Integer, primary_key=True)

    # Основная информация
    name = Column(String(255), nullable=False)  # Название для удобства
    domain = Column(String(255), unique=True, nullable=False)
    url = Column(String(512), nullable=False)  # Полный URL с протоколом

    # WordPress credentials (зашифрованы)
    wp_username = Column(String(255))
    wp_app_password_encrypted = Column(Text)  # Зашифрованный пароль

    # Хостинг информация
    hosting_provider = Column(String(255))
    hosting_type = Column(String(50))  # shared, vps, dedicated
    server_ip = Column(String(45))
    ssh_host = Column(String(255))
    ssh_user = Column(String(255))
    ssh_key_path = Column(String(512))
    ssh_password_encrypted = Column(Text)

    # Панель управления
    control_panel = Column(String(50))  # cpanel, plesk, ispmanager, none
    panel_url = Column(String(512))
    panel_username = Column(String(255))
    panel_password_encrypted = Column(Text)

    # WordPress настройки
    wp_version = Column(String(20))
    wp_theme = Column(String(255))
    wp_plugins = Column(JSON)  # Список установленных плагинов
    wp_locale = Column(String(10), default="ru_RU")

    # Fingerprint / Разнообразие
    fingerprint_profile = Column(JSON)  # Настройки для уникальности
    content_style = Column(String(50))  # formal, casual, expert, etc.

    # Прокси для этого сайта
    proxy_http = Column(String(512))
    proxy_https = Column(String(512))

    # Статистика
    total_posts = Column(Integer, default=0)
    last_post_date = Column(DateTime)

    # Статус
    status = Column(String(20), default="pending")  # pending, active, paused, error
    status_message = Column(Text)
    last_check = Column(DateTime)

    # Метаданные
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    notes = Column(Text)

    # Отношения
    posts = relationship("Post", back_populates="site", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Site {self.domain}>"


class Post(Base):
    """Модель опубликованного поста"""
    __tablename__ = "posts"

    id = Column(Integer, primary_key=True)
    site_id = Column(Integer, ForeignKey("sites.id"), nullable=False)

    # WordPress данные
    wp_post_id = Column(Integer)
    title = Column(String(512))
    url = Column(String(1024))

    # Контент метаданные
    topic = Column(String(512))
    category = Column(String(255))
    word_count = Column(Integer)
    language = Column(String(10), default="ru")

    # Ссылки в посте
    anchor_text = Column(String(255))
    anchor_url = Column(String(1024))
    target_site_id = Column(Integer, ForeignKey("sites.id"))  # Если ссылка на сайт из сети

    # Изображения
    has_featured_image = Column(Boolean, default=False)
    image_prompt = Column(Text)

    # Статус
    status = Column(String(20), default="draft")  # draft, scheduled, published, error
    scheduled_date = Column(DateTime)
    published_date = Column(DateTime)

    # Метаданные
    created_at = Column(DateTime, default=datetime.utcnow)
    generation_time_seconds = Column(Float)
    error_message = Column(Text)

    # Отношения
    site = relationship("Site", back_populates="posts", foreign_keys=[site_id])

    def __repr__(self):
        return f"<Post {self.title[:50]}... on {self.site.domain if self.site else 'unknown'}>"


class ContentQueue(Base):
    """Очередь контента для публикации"""
    __tablename__ = "content_queue"

    id = Column(Integer, primary_key=True)
    site_id = Column(Integer, ForeignKey("sites.id"), nullable=False)

    # Задание на генерацию
    topic = Column(String(512), nullable=False)
    category = Column(String(255))
    anchor_text = Column(String(255))
    anchor_url = Column(String(1024))

    # Параметры генерации
    target_word_count = Column(Integer, default=1750)
    language = Column(String(10), default="ru")
    content_style = Column(String(50))
    generate_image = Column(Boolean, default=True)

    # Планирование
    priority = Column(Integer, default=0)  # Выше = приоритетнее
    scheduled_after = Column(DateTime)  # Не публиковать раньше этого времени

    # Статус
    status = Column(String(20), default="pending")  # pending, processing, completed, failed
    attempts = Column(Integer, default=0)
    last_error = Column(Text)

    # Метаданные
    created_at = Column(DateTime, default=datetime.utcnow)
    processed_at = Column(DateTime)
    result_post_id = Column(Integer, ForeignKey("posts.id"))

    def __repr__(self):
        return f"<ContentQueue {self.topic[:30]}... for site_id={self.site_id}>"


class LinkStrategy(Base):
    """Стратегия линкбилдинга"""
    __tablename__ = "link_strategies"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)

    # Целевой URL (money site)
    target_url = Column(String(1024), nullable=False)
    target_name = Column(String(255))

    # Параметры
    total_links_target = Column(Integer, default=50)
    links_created = Column(Integer, default=0)

    # Распределение анкоров (JSON: {"exact": 20, "brand": 30, "generic": 50})
    anchor_distribution = Column(JSON)

    # Список вариаций анкоров
    anchor_variations = Column(JSON)  # ["купить X", "X цена", "магазин X", ...]

    # Настройки
    min_days_between_links = Column(Integer, default=3)
    max_links_per_site = Column(Integer, default=2)

    # Статус
    status = Column(String(20), default="active")  # active, paused, completed

    # Метаданные
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<LinkStrategy {self.name} -> {self.target_url}>"


class ThemeProfile(Base):
    """Профиль темы WordPress для разнообразия"""
    __tablename__ = "theme_profiles"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)

    # Тема
    theme_slug = Column(String(255), nullable=False)
    theme_source = Column(String(50), default="wordpress.org")  # wordpress.org, custom, premium
    theme_url = Column(String(1024))  # Для кастомных тем

    # Плагины
    required_plugins = Column(JSON)  # ["yoast-seo", "classic-editor", ...]
    optional_plugins = Column(JSON)

    # Настройки темы (JSON)
    theme_settings = Column(JSON)

    # Использование
    times_used = Column(Integer, default=0)

    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<ThemeProfile {self.name}>"


def init_database(database_url: str):
    """Инициализация базы данных"""
    engine = create_engine(database_url, echo=False)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return engine, Session


def get_session(database_url: str):
    """Получение сессии базы данных"""
    engine = create_engine(database_url, echo=False)
    Session = sessionmaker(bind=engine)
    return Session()
