"""
CLI команды для PBN Manager
"""

import argparse
import sys
import json
from pathlib import Path
from typing import Optional

# Добавляем корень проекта в путь
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from config.settings import settings, DATABASE_URL
from pbn_manager.core.site_registry import SiteRegistry
from pbn_manager.core.encryption import CredentialEncryption
from pbn_manager.core.fingerprint import FingerprintRandomizer, generate_site_fingerprint
from pbn_manager.wordpress.provisioner import provision_wordpress, WPInstallConfig


def cmd_init(args):
    """Инициализация системы"""
    print("Инициализация PBN Manager...")

    # Проверяем настройки
    errors = settings.validate()
    if errors:
        print("\nОшибки конфигурации:")
        for err in errors:
            print(f"  - {err}")

        if not args.force:
            print("\nИспользуйте --force для продолжения без полной настройки")
            return 1

    # Инициализируем базу данных
    registry = SiteRegistry(DATABASE_URL)
    print(f"База данных инициализирована: {DATABASE_URL}")

    print("\nPBN Manager готов к работе!")
    return 0


def cmd_generate_key(args):
    """Генерация ключа шифрования"""
    key = CredentialEncryption.generate_key()
    print("Новый ключ шифрования:")
    print(key)
    print("\nДобавьте в .env файл:")
    print(f"ENCRYPTION_KEY={key}")
    return 0


def cmd_site_add(args):
    """Добавление сайта в реестр"""
    registry = SiteRegistry(DATABASE_URL)

    try:
        site = registry.add_site(
            domain=args.domain,
            name=args.name,
            wp_username=args.wp_user,
            wp_app_password=args.wp_password,
            ssh_host=args.ssh_host,
            ssh_user=args.ssh_user,
            ssh_password=args.ssh_password,
            ssh_key_path=args.ssh_key,
            hosting_provider=args.hosting,
            content_style=args.style or "formal_expert",
        )

        print(f"Сайт добавлен: {site.domain} (ID: {site.id})")

        # Генерируем fingerprint
        if args.generate_fingerprint:
            fp = generate_site_fingerprint(args.domain)
            registry.update_site(site.id, fingerprint_profile=fp.__dict__)
            print(f"Fingerprint сгенерирован: тема={fp.theme}, стиль={fp.content_style}")

        return 0

    except Exception as e:
        print(f"Ошибка: {e}")
        return 1


def cmd_site_list(args):
    """Список сайтов"""
    registry = SiteRegistry(DATABASE_URL)
    sites = registry.get_all_sites(status=args.status)

    if not sites:
        print("Сайтов не найдено")
        return 0

    print(f"\n{'ID':<5} {'Домен':<30} {'Статус':<10} {'Постов':<8} {'Стиль':<15}")
    print("-" * 80)

    for site in sites:
        print(f"{site.id:<5} {site.domain:<30} {site.status:<10} {site.total_posts:<8} {site.content_style or '-':<15}")

    print(f"\nВсего: {len(sites)} сайтов")
    return 0


def cmd_site_info(args):
    """Информация о сайте"""
    registry = SiteRegistry(DATABASE_URL)

    site = registry.get_site(site_id=args.id, domain=args.domain)
    if not site:
        print("Сайт не найден")
        return 1

    print(f"\n=== {site.name} ===")
    print(f"ID: {site.id}")
    print(f"Домен: {site.domain}")
    print(f"URL: {site.url}")
    print(f"Статус: {site.status}")
    print(f"Хостинг: {site.hosting_provider or '-'}")
    print(f"WP Username: {site.wp_username or '-'}")
    print(f"SSH: {site.ssh_user}@{site.ssh_host}" if site.ssh_user else "SSH: не настроен")
    print(f"Стиль контента: {site.content_style or '-'}")
    print(f"Всего постов: {site.total_posts}")
    print(f"Последний пост: {site.last_post_date or '-'}")
    print(f"Создан: {site.created_at}")

    if site.fingerprint_profile:
        print(f"\nFingerprint:")
        fp = site.fingerprint_profile
        print(f"  Тема: {fp.get('theme', '-')}")
        print(f"  Плагины: {', '.join(fp.get('plugins', []))}")

    return 0


def cmd_site_provision(args):
    """Провизия WordPress на сайте"""
    print(f"Провизия WordPress для {args.domain}...")

    # Генерируем fingerprint для сайта
    fp = generate_site_fingerprint(args.domain, theme_type=args.theme_type or "blog")
    print(f"Сгенерирован профиль: тема={fp.theme}, плагины={len(fp.plugins)}")

    result = provision_wordpress(
        domain=args.domain,
        ssh_host=args.ssh_host or args.domain,
        ssh_user=args.ssh_user,
        ssh_password=args.ssh_password,
        ssh_key_path=args.ssh_key,
        mysql_root_password=args.mysql_root_password,
        site_title=args.title or args.domain,
        admin_email=args.admin_email or f"admin@{args.domain}",
        wp_locale=args.locale or "ru_RU",
        theme=fp.theme,
        plugins=fp.plugins,
    )

    if result.success:
        print("\n" + "=" * 50)
        print("WordPress успешно установлен!")
        print("=" * 50)
        print(f"URL сайта: {result.site_url}")
        print(f"Админка: {result.admin_url}")
        print(f"Логин: {result.admin_user}")
        print(f"Пароль: {result.admin_password}")
        print(f"Application Password: {result.app_password}")
        print("=" * 50)

        # Добавляем в реестр
        if args.add_to_registry:
            registry = SiteRegistry(DATABASE_URL)
            site = registry.add_site(
                domain=args.domain,
                wp_username=result.admin_user,
                wp_app_password=result.app_password,
                ssh_host=args.ssh_host or args.domain,
                ssh_user=args.ssh_user,
                ssh_password=args.ssh_password,
                content_style=fp.content_style,
            )
            registry.update_site(site.id, status="active", fingerprint_profile=fp.__dict__)
            print(f"\nСайт добавлен в реестр (ID: {site.id})")

        return 0
    else:
        print(f"\nОшибка: {result.error}")
        print("\nЛог установки:")
        for log in result.logs or []:
            print(f"  {log}")
        return 1


def cmd_fingerprint_generate(args):
    """Генерация fingerprint для сайта"""
    fp = generate_site_fingerprint(args.domain, theme_type=args.theme_type or "blog")

    print(f"\nFingerprint для {args.domain}:")
    print(f"  Тема: {fp.theme}")
    print(f"  Цветовая схема: {fp.color_scheme}")
    print(f"  Шрифт: {fp.font_family}")
    print(f"  Макет: {fp.layout_style}")
    print(f"  Плагины: {', '.join(fp.plugins)}")
    print(f"  Permalink: {fp.permalink_structure}")
    print(f"  Часовой пояс: {fp.timezone}")
    print(f"  Стиль контента: {fp.content_style}")
    print(f"  Среднее кол-во слов: {fp.avg_word_count}")
    print(f"  Частота постов: {fp.post_frequency_days:.1f} дней")
    print(f"  Время публикации: {fp.post_time_range[0]}:00 - {fp.post_time_range[1]}:00")

    if args.json:
        print(f"\nJSON:\n{json.dumps(fp.__dict__, indent=2, ensure_ascii=False)}")

    return 0


def cmd_stats(args):
    """Статистика по сети"""
    registry = SiteRegistry(DATABASE_URL)
    stats = registry.get_statistics()

    print("\n=== Статистика PBN сети ===")
    print(f"Всего сайтов: {stats['total_sites']}")
    print(f"  Активных: {stats['active_sites']}")
    print(f"  На паузе: {stats['paused_sites']}")
    print(f"  С ошибками: {stats['error_sites']}")
    print(f"  Ожидают настройки: {stats['pending_sites']}")
    print(f"\nВсего постов: {stats['total_posts']}")
    print(f"В очереди на генерацию: {stats['pending_content_queue']}")

    return 0


def main():
    """Главная функция CLI"""
    parser = argparse.ArgumentParser(
        description="PBN Manager - управление сетью WordPress сайтов",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    subparsers = parser.add_subparsers(dest="command", help="Команды")

    # init
    init_parser = subparsers.add_parser("init", help="Инициализация системы")
    init_parser.add_argument("--force", action="store_true", help="Принудительная инициализация")

    # generate-key
    subparsers.add_parser("generate-key", help="Генерация ключа шифрования")

    # site add
    site_add = subparsers.add_parser("site-add", help="Добавить сайт")
    site_add.add_argument("domain", help="Домен сайта")
    site_add.add_argument("--name", help="Название сайта")
    site_add.add_argument("--wp-user", help="WordPress username")
    site_add.add_argument("--wp-password", help="WordPress app password")
    site_add.add_argument("--ssh-host", help="SSH хост")
    site_add.add_argument("--ssh-user", help="SSH пользователь")
    site_add.add_argument("--ssh-password", help="SSH пароль")
    site_add.add_argument("--ssh-key", help="Путь к SSH ключу")
    site_add.add_argument("--hosting", help="Хостинг провайдер")
    site_add.add_argument("--style", help="Стиль контента")
    site_add.add_argument("--generate-fingerprint", action="store_true", help="Сгенерировать fingerprint")

    # site list
    site_list = subparsers.add_parser("site-list", help="Список сайтов")
    site_list.add_argument("--status", help="Фильтр по статусу")

    # site info
    site_info = subparsers.add_parser("site-info", help="Информация о сайте")
    site_info.add_argument("--id", type=int, help="ID сайта")
    site_info.add_argument("--domain", help="Домен сайта")

    # site provision
    provision = subparsers.add_parser("site-provision", help="Установить WordPress на сайт")
    provision.add_argument("domain", help="Домен сайта")
    provision.add_argument("--ssh-host", help="SSH хост (по умолчанию = домен)")
    provision.add_argument("--ssh-user", required=True, help="SSH пользователь")
    provision.add_argument("--ssh-password", help="SSH пароль")
    provision.add_argument("--ssh-key", help="Путь к SSH ключу")
    provision.add_argument("--mysql-root-password", help="MySQL root пароль")
    provision.add_argument("--title", help="Название сайта")
    provision.add_argument("--admin-email", help="Email админа")
    provision.add_argument("--locale", default="ru_RU", help="Локаль WordPress")
    provision.add_argument("--theme-type", choices=["blog", "business", "magazine"], help="Тип темы")
    provision.add_argument("--add-to-registry", action="store_true", help="Добавить в реестр после установки")

    # fingerprint
    fp_gen = subparsers.add_parser("fingerprint", help="Сгенерировать fingerprint")
    fp_gen.add_argument("domain", help="Домен для генерации")
    fp_gen.add_argument("--theme-type", choices=["blog", "business", "magazine"], help="Тип темы")
    fp_gen.add_argument("--json", action="store_true", help="Вывести в JSON")

    # stats
    subparsers.add_parser("stats", help="Статистика по сети")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    # Маппинг команд
    commands = {
        "init": cmd_init,
        "generate-key": cmd_generate_key,
        "site-add": cmd_site_add,
        "site-list": cmd_site_list,
        "site-info": cmd_site_info,
        "site-provision": cmd_site_provision,
        "fingerprint": cmd_fingerprint_generate,
        "stats": cmd_stats,
    }

    handler = commands.get(args.command)
    if handler:
        return handler(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
