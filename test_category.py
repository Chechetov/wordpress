#!/usr/bin/env python3
"""
Проверка конкретной категории и публикация в неё
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

# API эндпоинты
api_base = f"{site_url}/wp-json/wp/v2"
categories_endpoint = f"{api_base}/categories"
posts_endpoint = f"{api_base}/posts"

def check_categories():
    """Проверяем все доступные категории"""
    try:
        response = requests.get(
            categories_endpoint,
            headers=headers,
            proxies=proxies,
            params={'per_page': 100},
            timeout=10
        )
        
        if response.status_code == 200:
            categories = response.json()
            print("Доступные категории:")
            for cat in categories:
                print(f"ID: {cat['id']} | {cat['name']} | slug: {cat.get('slug', 'N/A')}")
                if 'Технические решения' in cat['name']:
                    print(f"  → НАЙДЕНА: ID {cat['id']}")
                    return cat['id']
        else:
            print(f"Ошибка: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"Ошибка: {str(e)}")
    
    return None

def publish_test_article(category_id):
    """Публикуем тестовую статью"""
    try:
        test_data = {
            'title': 'Тестовая статья ISP прокси',
            'content': '<p>Это тестовая статья для проверки публикации в категории Технические решения.</p>',
            'status': 'draft',  # Сначала как черновик
            'categories': [category_id]
        }
        
        response = requests.post(
            posts_endpoint,
            headers=headers,
            json=test_data,
            proxies=proxies,
            timeout=30
        )
        
        if response.status_code == 201:
            post_info = response.json()
            print(f"✅ Тестовая статья создана: ID {post_info['id']}")
            print(f"   URL: {post_info.get('link', 'N/A')}")
            return post_info
        else:
            print(f"❌ Ошибка создания: {response.status_code}")
            print(f"   Ответ: {response.text}")
            return None
            
    except Exception as e:
        print(f"❌ Ошибка: {str(e)}")
        return None

# Основная логика
print("Проверка категорий...")
category_id = check_categories()

if category_id:
    print(f"\nПробуем опубликовать тестовую статью в категории ID: {category_id}")
    result = publish_test_article(category_id)
    
    if result:
        print("\n✅ Публикация работает! Можно запускать основной скрипт.")
    else:
        print("\n❌ Проблема с правами пользователя. Нужно проверить роль в WordPress.")
else:
    print("\n❌ Категория 'Технические решения' не найдена.")
    print("Используем существующую категорию 'Энергетическая инфраструктура' (ID: 2)")