#!/usr/bin/env python3
"""Проверка сервера для установки WordPress"""

import paramiko
import sys

# Credentials
HOST = "141.136.39.167"
PORT = 65002
USER = "u349788562"
PASSWORD = "Xk4oNrx3z3H#B?Qz"

def execute(client, command):
    """Выполнить команду и вернуть результат"""
    stdin, stdout, stderr = client.exec_command(command)
    exit_code = stdout.channel.recv_exit_status()
    output = stdout.read().decode('utf-8', errors='replace').strip()
    error = stderr.read().decode('utf-8', errors='replace').strip()
    return exit_code, output, error

def main():
    print(f"Подключение к {HOST}:{PORT}...")

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        client.connect(
            hostname=HOST,
            port=PORT,
            username=USER,
            password=PASSWORD,
            timeout=30
        )
        print("✓ Подключение успешно!\n")

        # Проверяем систему
        checks = [
            ("Система", "uname -a"),
            ("ОС", "cat /etc/*release 2>/dev/null | grep -E '^(NAME|VERSION)=' | head -2"),
            ("Домашняя директория", "pwd && ls -la"),
            ("PHP версия", "php -v 2>/dev/null | head -1 || echo 'PHP не найден'"),
            ("MySQL/MariaDB", "mysql --version 2>/dev/null || echo 'MySQL не найден'"),
            ("Nginx", "nginx -v 2>&1 || echo 'Nginx не найден'"),
            ("Apache", "apache2 -v 2>&1 || httpd -v 2>&1 || echo 'Apache не найден'"),
            ("WP-CLI", "wp --version 2>/dev/null || echo 'WP-CLI не найден'"),
            ("curl", "curl --version 2>/dev/null | head -1 || echo 'curl не найден'"),
            ("Disk space", "df -h ~ 2>/dev/null | tail -1"),
            ("Проверка public_html", "ls -la ~/public_html 2>/dev/null || ls -la ~/domains 2>/dev/null || echo 'Нет стандартных web директорий'"),
            ("Проверка прав sudo", "sudo -n true 2>/dev/null && echo 'sudo доступен' || echo 'sudo недоступен'"),
        ]

        for name, cmd in checks:
            code, out, err = execute(client, cmd)
            print(f"=== {name} ===")
            if out:
                print(out)
            if err and code != 0:
                print(f"(stderr: {err})")
            print()

        # Проверяем наличие панели управления
        print("=== Панель управления ===")
        code, out, err = execute(client, "ls -la /usr/local/cpanel 2>/dev/null && echo 'cPanel' || ls -la /usr/local/psa 2>/dev/null && echo 'Plesk' || echo 'Панель не обнаружена или shared hosting'")
        print(out or err)

    except Exception as e:
        print(f"✗ Ошибка подключения: {e}")
        return 1
    finally:
        client.close()

    return 0

if __name__ == "__main__":
    sys.exit(main())
