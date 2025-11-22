"""
WordPress Provisioner - автоматическая установка и настройка WordPress
Поддерживает установку через SSH на VPS/выделенные серверы
"""

import logging
import secrets
import string
import time
from dataclasses import dataclass
from typing import Optional, Dict, List, Tuple
from pathlib import Path

import paramiko

logger = logging.getLogger(__name__)


@dataclass
class WPInstallConfig:
    """Конфигурация установки WordPress"""
    # Домен и пути
    domain: str
    web_root: str = "/var/www"  # Корневая директория веб-сервера
    site_path: Optional[str] = None  # Если None, будет {web_root}/{domain}

    # WordPress
    wp_version: str = "latest"
    wp_locale: str = "ru_RU"
    site_title: str = "My Blog"
    admin_user: str = "admin"
    admin_password: Optional[str] = None  # Если None, сгенерируем
    admin_email: str = "admin@example.com"

    # База данных
    db_name: Optional[str] = None  # Если None, сгенерируем из домена
    db_user: Optional[str] = None
    db_password: Optional[str] = None
    db_host: str = "localhost"
    db_prefix: str = "wp_"

    # Тема и плагины
    theme: str = "flavor"  # flavor или flavor
    plugins: List[str] = None  # Список плагинов для установки

    # Дополнительно
    multisite: bool = False
    ssl: bool = True
    debug: bool = False


@dataclass
class ProvisioningResult:
    """Результат провизии"""
    success: bool
    domain: str
    site_url: str = ""
    admin_url: str = ""
    admin_user: str = ""
    admin_password: str = ""
    app_password: str = ""  # Application Password для REST API
    db_name: str = ""
    db_user: str = ""
    db_password: str = ""
    error: str = ""
    logs: List[str] = None


class SSHExecutor:
    """Выполнение команд через SSH"""

    def __init__(
        self,
        host: str,
        username: str,
        password: Optional[str] = None,
        key_path: Optional[str] = None,
        port: int = 22
    ):
        self.host = host
        self.username = username
        self.password = password
        self.key_path = key_path
        self.port = port
        self.client: Optional[paramiko.SSHClient] = None

    def connect(self) -> bool:
        """Установка SSH соединения"""
        try:
            self.client = paramiko.SSHClient()
            self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            connect_kwargs = {
                'hostname': self.host,
                'port': self.port,
                'username': self.username,
            }

            if self.key_path:
                connect_kwargs['key_filename'] = self.key_path
            elif self.password:
                connect_kwargs['password'] = self.password

            self.client.connect(**connect_kwargs)
            logger.info(f"SSH подключение установлено: {self.username}@{self.host}")
            return True

        except Exception as e:
            logger.error(f"Ошибка SSH подключения: {e}")
            return False

    def execute(self, command: str, sudo: bool = False) -> Tuple[int, str, str]:
        """
        Выполнение команды

        Args:
            command: Команда для выполнения
            sudo: Выполнить с sudo

        Returns:
            Кортеж (код возврата, stdout, stderr)
        """
        if not self.client:
            raise RuntimeError("SSH соединение не установлено")

        if sudo:
            command = f"sudo {command}"

        logger.debug(f"Выполнение: {command}")

        stdin, stdout, stderr = self.client.exec_command(command)

        exit_code = stdout.channel.recv_exit_status()
        stdout_text = stdout.read().decode('utf-8', errors='replace')
        stderr_text = stderr.read().decode('utf-8', errors='replace')

        if exit_code != 0:
            logger.warning(f"Команда вернула код {exit_code}: {command}")
            if stderr_text:
                logger.warning(f"stderr: {stderr_text}")

        return exit_code, stdout_text, stderr_text

    def file_exists(self, path: str) -> bool:
        """Проверка существования файла"""
        code, _, _ = self.execute(f"test -e {path}")
        return code == 0

    def upload_file(self, local_path: str, remote_path: str):
        """Загрузка файла на сервер"""
        if not self.client:
            raise RuntimeError("SSH соединение не установлено")

        sftp = self.client.open_sftp()
        sftp.put(local_path, remote_path)
        sftp.close()
        logger.info(f"Файл загружен: {local_path} -> {remote_path}")

    def close(self):
        """Закрытие соединения"""
        if self.client:
            self.client.close()
            logger.info("SSH соединение закрыто")


class WordPressProvisioner:
    """Автоматическая установка WordPress"""

    def __init__(self, ssh_executor: SSHExecutor):
        """
        Инициализация провизионера

        Args:
            ssh_executor: Экземпляр SSHExecutor для выполнения команд
        """
        self.ssh = ssh_executor
        self.logs: List[str] = []

    def _log(self, message: str):
        """Добавление записи в лог"""
        logger.info(message)
        self.logs.append(f"{time.strftime('%H:%M:%S')} - {message}")

    def _generate_password(self, length: int = 24) -> str:
        """Генерация безопасного пароля"""
        alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
        return ''.join(secrets.choice(alphabet) for _ in range(length))

    def _sanitize_db_name(self, domain: str) -> str:
        """Создание имени БД из домена"""
        # Убираем точки, заменяем на подчёркивания, берём первые 16 символов
        name = domain.replace('.', '_').replace('-', '_')
        name = ''.join(c for c in name if c.isalnum() or c == '_')
        return f"wp_{name[:12]}"

    def check_requirements(self) -> Dict[str, bool]:
        """Проверка наличия необходимых компонентов на сервере"""
        self._log("Проверка требований...")

        requirements = {
            'php': False,
            'mysql': False,
            'nginx_or_apache': False,
            'wp_cli': False,
            'curl': False,
        }

        # PHP
        code, out, _ = self.ssh.execute("php -v")
        requirements['php'] = code == 0 and 'PHP' in out

        # MySQL/MariaDB
        code, _, _ = self.ssh.execute("which mysql")
        requirements['mysql'] = code == 0

        # Веб-сервер
        code_nginx, _, _ = self.ssh.execute("which nginx")
        code_apache, _, _ = self.ssh.execute("which apache2 || which httpd")
        requirements['nginx_or_apache'] = code_nginx == 0 or code_apache == 0

        # WP-CLI
        code, _, _ = self.ssh.execute("which wp")
        requirements['wp_cli'] = code == 0

        # curl
        code, _, _ = self.ssh.execute("which curl")
        requirements['curl'] = code == 0

        for req, status in requirements.items():
            self._log(f"  {req}: {'✓' if status else '✗'}")

        return requirements

    def install_wp_cli(self) -> bool:
        """Установка WP-CLI если отсутствует"""
        self._log("Установка WP-CLI...")

        commands = [
            "curl -O https://raw.githubusercontent.com/wp-cli/builds/gh-pages/phar/wp-cli.phar",
            "chmod +x wp-cli.phar",
            "sudo mv wp-cli.phar /usr/local/bin/wp",
        ]

        for cmd in commands:
            code, _, err = self.ssh.execute(cmd)
            if code != 0:
                self._log(f"Ошибка установки WP-CLI: {err}")
                return False

        # Проверяем
        code, out, _ = self.ssh.execute("wp --info")
        if code == 0:
            self._log("WP-CLI успешно установлен")
            return True

        return False

    def create_database(self, db_name: str, db_user: str, db_password: str, root_password: str = None) -> bool:
        """Создание базы данных MySQL"""
        self._log(f"Создание базы данных: {db_name}")

        # Команды для создания БД
        mysql_commands = f"""
        CREATE DATABASE IF NOT EXISTS {db_name} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
        CREATE USER IF NOT EXISTS '{db_user}'@'localhost' IDENTIFIED BY '{db_password}';
        GRANT ALL PRIVILEGES ON {db_name}.* TO '{db_user}'@'localhost';
        FLUSH PRIVILEGES;
        """

        if root_password:
            cmd = f'mysql -u root -p"{root_password}" -e "{mysql_commands}"'
        else:
            # Пробуем без пароля (sudo mysql) - типично для Ubuntu
            cmd = f'sudo mysql -e "{mysql_commands}"'

        code, _, err = self.ssh.execute(cmd)

        if code != 0:
            self._log(f"Ошибка создания БД: {err}")
            return False

        self._log("База данных создана успешно")
        return True

    def download_wordpress(self, path: str, locale: str = "ru_RU", version: str = "latest") -> bool:
        """Скачивание WordPress"""
        self._log(f"Скачивание WordPress ({version}, {locale}) в {path}")

        # Создаём директорию
        self.ssh.execute(f"sudo mkdir -p {path}", sudo=True)

        # Скачиваем WordPress через WP-CLI
        cmd = f"cd {path} && sudo wp core download --locale={locale} --version={version} --allow-root"
        code, _, err = self.ssh.execute(cmd)

        if code != 0:
            self._log(f"Ошибка скачивания WordPress: {err}")
            return False

        self._log("WordPress скачан успешно")
        return True

    def configure_wordpress(self, config: WPInstallConfig) -> bool:
        """Настройка wp-config.php"""
        site_path = config.site_path or f"{config.web_root}/{config.domain}"
        self._log(f"Настройка wp-config.php в {site_path}")

        cmd = (
            f"cd {site_path} && sudo wp config create "
            f"--dbname={config.db_name} "
            f"--dbuser={config.db_user} "
            f"--dbpass='{config.db_password}' "
            f"--dbhost={config.db_host} "
            f"--dbprefix={config.db_prefix} "
            f"--locale={config.wp_locale} "
            f"--allow-root"
        )

        code, _, err = self.ssh.execute(cmd)

        if code != 0:
            self._log(f"Ошибка создания wp-config: {err}")
            return False

        # Добавляем дополнительные настройки
        if config.debug:
            self.ssh.execute(
                f"cd {site_path} && sudo wp config set WP_DEBUG true --raw --allow-root"
            )

        self._log("wp-config.php создан успешно")
        return True

    def install_wordpress(self, config: WPInstallConfig) -> bool:
        """Установка WordPress (создание таблиц, админа)"""
        site_path = config.site_path or f"{config.web_root}/{config.domain}"
        protocol = "https" if config.ssl else "http"
        url = f"{protocol}://{config.domain}"

        self._log(f"Установка WordPress: {url}")

        cmd = (
            f"cd {site_path} && sudo wp core install "
            f"--url='{url}' "
            f"--title='{config.site_title}' "
            f"--admin_user='{config.admin_user}' "
            f"--admin_password='{config.admin_password}' "
            f"--admin_email='{config.admin_email}' "
            f"--skip-email "
            f"--allow-root"
        )

        code, out, err = self.ssh.execute(cmd)

        if code != 0:
            self._log(f"Ошибка установки WordPress: {err}")
            return False

        self._log("WordPress установлен успешно")
        return True

    def install_theme(self, site_path: str, theme: str) -> bool:
        """Установка и активация темы"""
        self._log(f"Установка темы: {theme}")

        # Устанавливаем
        cmd = f"cd {site_path} && sudo wp theme install {theme} --activate --allow-root"
        code, _, err = self.ssh.execute(cmd)

        if code != 0:
            self._log(f"Ошибка установки темы: {err}")
            return False

        self._log(f"Тема {theme} установлена и активирована")
        return True

    def install_plugins(self, site_path: str, plugins: List[str]) -> Dict[str, bool]:
        """Установка плагинов"""
        results = {}

        for plugin in plugins:
            self._log(f"Установка плагина: {plugin}")

            cmd = f"cd {site_path} && sudo wp plugin install {plugin} --activate --allow-root"
            code, _, err = self.ssh.execute(cmd)

            results[plugin] = code == 0

            if code != 0:
                self._log(f"Ошибка установки плагина {plugin}: {err}")
            else:
                self._log(f"Плагин {plugin} установлен")

        return results

    def create_application_password(self, site_path: str, admin_user: str, app_name: str = "PBN Manager") -> Optional[str]:
        """Создание Application Password для REST API"""
        self._log("Создание Application Password для REST API...")

        cmd = f"cd {site_path} && sudo wp user application-password create {admin_user} '{app_name}' --porcelain --allow-root"
        code, out, err = self.ssh.execute(cmd)

        if code != 0:
            self._log(f"Ошибка создания Application Password: {err}")
            return None

        # Парсим вывод - пароль в первой строке
        app_password = out.strip().split('\n')[0].strip()
        self._log("Application Password создан успешно")
        return app_password

    def set_permissions(self, site_path: str, web_user: str = "www-data") -> bool:
        """Установка правильных прав доступа"""
        self._log(f"Установка прав доступа для {web_user}")

        commands = [
            f"sudo chown -R {web_user}:{web_user} {site_path}",
            f"sudo find {site_path} -type d -exec chmod 755 {{}} \\;",
            f"sudo find {site_path} -type f -exec chmod 644 {{}} \\;",
        ]

        for cmd in commands:
            code, _, err = self.ssh.execute(cmd)
            if code != 0:
                self._log(f"Ошибка установки прав: {err}")
                return False

        self._log("Права доступа установлены")
        return True

    def provision(self, config: WPInstallConfig, mysql_root_password: str = None) -> ProvisioningResult:
        """
        Полная установка WordPress

        Args:
            config: Конфигурация установки
            mysql_root_password: Пароль root MySQL (если требуется)

        Returns:
            ProvisioningResult с результатами установки
        """
        self.logs = []
        result = ProvisioningResult(
            success=False,
            domain=config.domain,
            logs=self.logs
        )

        try:
            # Генерируем недостающие данные
            if not config.admin_password:
                config.admin_password = self._generate_password(16)
            if not config.db_name:
                config.db_name = self._sanitize_db_name(config.domain)
            if not config.db_user:
                config.db_user = config.db_name[:16]
            if not config.db_password:
                config.db_password = self._generate_password(24)
            if not config.site_path:
                config.site_path = f"{config.web_root}/{config.domain}"

            # Плагины по умолчанию
            if config.plugins is None:
                config.plugins = [
                    "flavor",  # flavor
                    "flavor",  # flavor
                ]

            # 1. Проверка требований
            reqs = self.check_requirements()
            if not all([reqs['php'], reqs['mysql']]):
                result.error = "Не установлены необходимые компоненты (PHP, MySQL)"
                return result

            # Устанавливаем WP-CLI если нет
            if not reqs['wp_cli']:
                if not self.install_wp_cli():
                    result.error = "Не удалось установить WP-CLI"
                    return result

            # 2. Создание базы данных
            if not self.create_database(config.db_name, config.db_user, config.db_password, mysql_root_password):
                result.error = "Не удалось создать базу данных"
                return result

            # 3. Скачивание WordPress
            if not self.download_wordpress(config.site_path, config.wp_locale, config.wp_version):
                result.error = "Не удалось скачать WordPress"
                return result

            # 4. Настройка wp-config.php
            if not self.configure_wordpress(config):
                result.error = "Не удалось настроить wp-config.php"
                return result

            # 5. Установка WordPress
            if not self.install_wordpress(config):
                result.error = "Не удалось установить WordPress"
                return result

            # 6. Установка темы
            if config.theme:
                self.install_theme(config.site_path, config.theme)

            # 7. Установка плагинов
            if config.plugins:
                self.install_plugins(config.site_path, config.plugins)

            # 8. Создание Application Password
            app_password = self.create_application_password(config.site_path, config.admin_user)

            # 9. Установка прав
            self.set_permissions(config.site_path)

            # Формируем результат
            protocol = "https" if config.ssl else "http"
            result.success = True
            result.site_url = f"{protocol}://{config.domain}"
            result.admin_url = f"{protocol}://{config.domain}/wp-admin"
            result.admin_user = config.admin_user
            result.admin_password = config.admin_password
            result.app_password = app_password or ""
            result.db_name = config.db_name
            result.db_user = config.db_user
            result.db_password = config.db_password

            self._log("=" * 50)
            self._log("WordPress успешно установлен!")
            self._log(f"URL сайта: {result.site_url}")
            self._log(f"Админка: {result.admin_url}")
            self._log(f"Логин: {result.admin_user}")
            self._log("=" * 50)

            return result

        except Exception as e:
            self._log(f"Критическая ошибка: {e}")
            result.error = str(e)
            return result


def provision_wordpress(
    domain: str,
    ssh_host: str,
    ssh_user: str,
    ssh_password: str = None,
    ssh_key_path: str = None,
    mysql_root_password: str = None,
    **kwargs
) -> ProvisioningResult:
    """
    Удобная функция для быстрой установки WordPress

    Args:
        domain: Домен сайта
        ssh_host: SSH хост
        ssh_user: SSH пользователь
        ssh_password: SSH пароль
        ssh_key_path: Путь к SSH ключу
        mysql_root_password: Пароль root MySQL
        **kwargs: Дополнительные параметры WPInstallConfig

    Returns:
        ProvisioningResult
    """
    # Создаём SSH соединение
    ssh = SSHExecutor(
        host=ssh_host,
        username=ssh_user,
        password=ssh_password,
        key_path=ssh_key_path
    )

    if not ssh.connect():
        return ProvisioningResult(
            success=False,
            domain=domain,
            error="Не удалось установить SSH соединение"
        )

    try:
        # Создаём конфигурацию
        config = WPInstallConfig(domain=domain, **kwargs)

        # Запускаем установку
        provisioner = WordPressProvisioner(ssh)
        result = provisioner.provision(config, mysql_root_password)

        return result

    finally:
        ssh.close()
