#!/usr/bin/env python3
"""
Тестирование Application Password
"""

import requests
import base64
import os
from dotenv import load_dotenv

load_dotenv()

# Настройки подключения
site_url = os.getenv('WORDPRESS_URL')
username = os.getenv('WORDPRESS_USERNAME') 
app_password = os.getenv('WORDPRESS_APP_PASSWORD')

# Настройка прокси
proxies = None
if os.getenv('PROXY_HTTP') or os.getenv('PROXY_HTTPS'):
    proxies = {}
    if os.getenv('PROXY_HTTP'):
        proxies['http'] = os.getenv('PROXY_HTTP')
    if os.getenv('PROXY_HTTPS'):
        proxies['https'] = os.getenv('PROXY_HTTPS')

print(f"Тестирую подключение для пользователя: {username}")
print(f"Сайт: {site_url}")
print(f"Прокси: {proxies}")
print(f"Длина пароля: {len(app_password) if app_password else 0}")
print()

# Тестируем базовое подключение
credentials = f"{username}:{app_password}"
encoded_credentials = base64.b64encode(credentials.encode()).decode()
headers = {
    'Authorization': f'Basic {encoded_credentials}',
    'Content-Type': 'application/json'
}

# Тест 1: Проверка постов
try:
    print("Тест 1: Проверка доступа к постам...")
    response = requests.get(
        f"{site_url}/wp-json/wp/v2/posts?per_page=1",
        headers=headers,
        proxies=proxies,
        timeout=10
    )
    print(f"Статус: {response.status_code}")
    if response.status_code == 200:
        print("✅ Доступ к постам есть")
    else:
        print(f"❌ Ошибка: {response.text}")
except Exception as e:
    print(f"❌ Исключение: {str(e)}")

print()

# Тест 2: Проверка пользователей
try:
    print("Тест 2: Проверка доступа к пользователям...")
    response = requests.get(
        f"{site_url}/wp-json/wp/v2/users/me",
        headers=headers,
        proxies=proxies,
        timeout=10
    )
    print(f"Статус: {response.status_code}")
    if response.status_code == 200:
        user_info = response.json()
        print(f"✅ Пользователь: {user_info['name']}")
        print(f"   Роли: {user_info.get('roles', [])}")
    else:
        print(f"❌ Ошибка: {response.text}")
except Exception as e:
    print(f"❌ Исключение: {str(e)}")

print()
print("ИНСТРУКЦИЯ:")
print("1. Зайдите в WordPress админку")
print("2. Профиль пользователя → Application Passwords")
print("3. Создайте новый Application Password с именем 'API'")
print("4. Скопируйте новый пароль")
print("5. Обновите переменную WORDPRESS_APP_PASSWORD в .env файле")
print("6. Новый пароль будет выглядеть как: xxxx xxxx xxxx xxxx xxxx xxxx")