#!/usr/bin/env python3
"""
Проверка информации о текущем пользователе
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

# Аутентификация
credentials = f"{username}:{app_password}"
encoded_credentials = base64.b64encode(credentials.encode()).decode()
headers = {
    'Authorization': f'Basic {encoded_credentials}',
    'Content-Type': 'application/json'
}

# API эндпоинт
users_endpoint = f"{site_url}/wp-json/wp/v2/users/me"

try:
    print(f"Проверка пользователя: {username}")
    response = requests.get(
        users_endpoint,
        headers=headers,
        proxies=proxies,
        timeout=10
    )
    
    if response.status_code == 200:
        user_info = response.json()
        print("✅ Пользователь найден:")
        print(f"   ID: {user_info['id']}")
        print(f"   Имя: {user_info['name']}")
        print(f"   Email: {user_info['email']}")
        print(f"   Роль: {user_info.get('roles', ['N/A'])}")
        print(f"  _capabilities: {list(user_info.get('capabilities', {}).keys())}")
    else:
        print(f"❌ Ошибка: {response.status_code}")
        print(f"   Ответ: {response.text}")
        
except Exception as e:
    print(f"❌ Ошибка: {str(e)}")

print("\n" + "="*50)
print("ИНСТРУКЦИЯ ПО ИЗМЕНЕНИЮ ПРАВ:")
print("1. Зайдите в админку WordPress")
print("2. Перейдите: Пользователи → Все пользователи")
print("3. Найдите пользователя 'posting'")
print("4. Нажмите 'Изменить'")
print("5. В разделе 'Роль' выберите 'Автор' или 'Редактор'")
print("6. Нажмите 'Обновить пользователя'")
print("="*50)