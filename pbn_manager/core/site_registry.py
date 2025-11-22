"""
Site Registry - управление реестром сайтов PBN сети
"""

import logging
from datetime import datetime
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from .models import Site, Post, ContentQueue, init_database
from .encryption import CredentialEncryption, get_encryptor

logger = logging.getLogger(__name__)


class SiteRegistry:
    """Класс для управления реестром сайтов"""

    def __init__(self, database_url: str, encryption_key: Optional[str] = None):
        """
        Инициализация реестра сайтов

        Args:
            database_url: URL базы данных (sqlite:///path или postgresql://...)
            encryption_key: Ключ шифрования для credentials
        """
        self.database_url = database_url
        self.engine, self.SessionClass = init_database(database_url)

        try:
            self.encryptor = CredentialEncryption(encryption_key)
        except ValueError:
            logger.warning("Шифрование не настроено. Credentials будут храниться в открытом виде!")
            self.encryptor = None

        logger.info(f"SiteRegistry инициализирован. БД: {database_url}")

    def _get_session(self) -> Session:
        """Получение сессии БД"""
        return self.SessionClass()

    def _encrypt(self, value: str) -> str:
        """Шифрование значения если доступно"""
        if self.encryptor and value:
            return self.encryptor.encrypt(value)
        return value

    def _decrypt(self, value: str) -> str:
        """Дешифрование значения если доступно"""
        if self.encryptor and value:
            try:
                return self.encryptor.decrypt(value)
            except Exception:
                return value  # Возможно уже расшифровано или не было зашифровано
        return value

    # === CRUD операции для сайтов ===

    def add_site(
        self,
        domain: str,
        name: Optional[str] = None,
        wp_username: Optional[str] = None,
        wp_app_password: Optional[str] = None,
        hosting_provider: Optional[str] = None,
        ssh_host: Optional[str] = None,
        ssh_user: Optional[str] = None,
        ssh_password: Optional[str] = None,
        ssh_key_path: Optional[str] = None,
        control_panel: Optional[str] = None,
        panel_url: Optional[str] = None,
        panel_username: Optional[str] = None,
        panel_password: Optional[str] = None,
        proxy_http: Optional[str] = None,
        proxy_https: Optional[str] = None,
        content_style: str = "formal",
        wp_locale: str = "ru_RU",
        notes: Optional[str] = None,
        **kwargs
    ) -> Site:
        """
        Добавление нового сайта в реестр

        Args:
            domain: Домен сайта (например, example.com)
            name: Понятное название сайта
            wp_username: Логин WordPress
            wp_app_password: Application Password WordPress
            ... (остальные параметры)

        Returns:
            Созданный объект Site
        """
        session = self._get_session()

        try:
            # Проверяем, что домен ещё не добавлен
            existing = session.query(Site).filter_by(domain=domain).first()
            if existing:
                raise ValueError(f"Сайт с доменом {domain} уже существует (ID: {existing.id})")

            # Формируем URL
            url = f"https://{domain}" if not domain.startswith("http") else domain

            site = Site(
                domain=domain,
                name=name or domain,
                url=url,
                wp_username=wp_username,
                wp_app_password_encrypted=self._encrypt(wp_app_password) if wp_app_password else None,
                hosting_provider=hosting_provider,
                ssh_host=ssh_host or domain,
                ssh_user=ssh_user,
                ssh_password_encrypted=self._encrypt(ssh_password) if ssh_password else None,
                ssh_key_path=ssh_key_path,
                control_panel=control_panel,
                panel_url=panel_url,
                panel_username=panel_username,
                panel_password_encrypted=self._encrypt(panel_password) if panel_password else None,
                proxy_http=proxy_http,
                proxy_https=proxy_https,
                content_style=content_style,
                wp_locale=wp_locale,
                status="pending",
                notes=notes,
            )

            session.add(site)
            session.commit()

            logger.info(f"Сайт добавлен: {domain} (ID: {site.id})")
            return site

        except Exception as e:
            session.rollback()
            logger.error(f"Ошибка добавления сайта {domain}: {e}")
            raise
        finally:
            session.close()

    def get_site(self, site_id: int = None, domain: str = None) -> Optional[Site]:
        """
        Получение сайта по ID или домену

        Args:
            site_id: ID сайта
            domain: Домен сайта

        Returns:
            Объект Site или None
        """
        session = self._get_session()
        try:
            if site_id:
                return session.query(Site).filter_by(id=site_id).first()
            elif domain:
                return session.query(Site).filter_by(domain=domain).first()
            return None
        finally:
            session.close()

    def get_all_sites(self, status: Optional[str] = None) -> List[Site]:
        """
        Получение всех сайтов

        Args:
            status: Фильтр по статусу (active, pending, paused, error)

        Returns:
            Список сайтов
        """
        session = self._get_session()
        try:
            query = session.query(Site)
            if status:
                query = query.filter_by(status=status)
            return query.order_by(Site.created_at.desc()).all()
        finally:
            session.close()

    def update_site(self, site_id: int, **kwargs) -> Optional[Site]:
        """
        Обновление данных сайта

        Args:
            site_id: ID сайта
            **kwargs: Поля для обновления

        Returns:
            Обновлённый объект Site
        """
        session = self._get_session()
        try:
            site = session.query(Site).filter_by(id=site_id).first()
            if not site:
                return None

            # Шифруем пароли если обновляются
            password_fields = {
                'wp_app_password': 'wp_app_password_encrypted',
                'ssh_password': 'ssh_password_encrypted',
                'panel_password': 'panel_password_encrypted'
            }

            for plain_field, encrypted_field in password_fields.items():
                if plain_field in kwargs:
                    kwargs[encrypted_field] = self._encrypt(kwargs.pop(plain_field))

            for key, value in kwargs.items():
                if hasattr(site, key):
                    setattr(site, key, value)

            site.updated_at = datetime.utcnow()
            session.commit()

            logger.info(f"Сайт обновлён: {site.domain} (ID: {site_id})")
            return site

        except Exception as e:
            session.rollback()
            logger.error(f"Ошибка обновления сайта {site_id}: {e}")
            raise
        finally:
            session.close()

    def delete_site(self, site_id: int) -> bool:
        """
        Удаление сайта из реестра

        Args:
            site_id: ID сайта

        Returns:
            True если успешно удалён
        """
        session = self._get_session()
        try:
            site = session.query(Site).filter_by(id=site_id).first()
            if not site:
                return False

            domain = site.domain
            session.delete(site)
            session.commit()

            logger.info(f"Сайт удалён: {domain} (ID: {site_id})")
            return True

        except Exception as e:
            session.rollback()
            logger.error(f"Ошибка удаления сайта {site_id}: {e}")
            raise
        finally:
            session.close()

    def get_site_credentials(self, site_id: int) -> Dict[str, str]:
        """
        Получение расшифрованных credentials сайта

        Args:
            site_id: ID сайта

        Returns:
            Словарь с credentials
        """
        session = self._get_session()
        try:
            site = session.query(Site).filter_by(id=site_id).first()
            if not site:
                return {}

            return {
                'wp_username': site.wp_username,
                'wp_app_password': self._decrypt(site.wp_app_password_encrypted),
                'ssh_user': site.ssh_user,
                'ssh_password': self._decrypt(site.ssh_password_encrypted),
                'ssh_key_path': site.ssh_key_path,
                'panel_username': site.panel_username,
                'panel_password': self._decrypt(site.panel_password_encrypted),
            }
        finally:
            session.close()

    # === Статистика и отчёты ===

    def get_statistics(self) -> Dict[str, Any]:
        """Получение общей статистики по сети"""
        session = self._get_session()
        try:
            total_sites = session.query(Site).count()
            active_sites = session.query(Site).filter_by(status="active").count()
            total_posts = session.query(Post).count()
            pending_queue = session.query(ContentQueue).filter_by(status="pending").count()

            return {
                'total_sites': total_sites,
                'active_sites': active_sites,
                'paused_sites': session.query(Site).filter_by(status="paused").count(),
                'error_sites': session.query(Site).filter_by(status="error").count(),
                'pending_sites': session.query(Site).filter_by(status="pending").count(),
                'total_posts': total_posts,
                'pending_content_queue': pending_queue,
            }
        finally:
            session.close()

    def set_site_status(self, site_id: int, status: str, message: str = None) -> bool:
        """
        Установка статуса сайта

        Args:
            site_id: ID сайта
            status: Новый статус (active, pending, paused, error)
            message: Сообщение о статусе

        Returns:
            True если успешно
        """
        valid_statuses = ['active', 'pending', 'paused', 'error']
        if status not in valid_statuses:
            raise ValueError(f"Недопустимый статус. Разрешены: {valid_statuses}")

        return self.update_site(site_id, status=status, status_message=message) is not None


# Singleton для глобального доступа
_registry_instance: Optional[SiteRegistry] = None


def get_registry(database_url: str = None) -> SiteRegistry:
    """Получение singleton экземпляра реестра"""
    global _registry_instance

    if _registry_instance is None:
        from config.settings import DATABASE_URL
        _registry_instance = SiteRegistry(database_url or DATABASE_URL)

    return _registry_instance
