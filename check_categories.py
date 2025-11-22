#!/usr/bin/env python3
"""
Скрипт для проверки существующих категорий в WordPress
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
categories_endpoint = f"{site_url}/wp-json/wp/v2/categories"

print(f"Проверка категорий на сайте: {site_url}")
print(f"Использую прокси: {proxies}")

try:
    # Получаем все категории
    response = requests.get(
        categories_endpoint,
        headers=headers,
        proxies=proxies,
        params={'per_page': 100},  # Получаем до 100 категорий
        timeout=10
    )
    
    if response.status_code == 200:
        categories = response.json()
        print(f"\nНайдено {len(categories)} категорий:")
        print("-" * 50)
        
        for cat in categories:
            print(f"ID: {cat['id']} | {cat['name']}")
            print(f"  Количество постов: {cat['count']}")
            print(f"  Описание: {cat.get('description', 'Нет описания')}")
            print()
            
    else:
        print(f"Ошибка получения категорий: {response.status_code}")
        print(f"Ответ: {response.text}")
        
except Exception as e:
    print(f"Исключение: {str(e)}")