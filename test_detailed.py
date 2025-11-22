#!/usr/bin/env python3
"""
Проверка возможности создания записей с автором
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
posts_endpoint = f"{api_base}/posts"
users_endpoint = f"{api_base}/users"

print("Проверка возможных вариантов публикации...")

# Сначала получим ID пользователя
try:
    print("1. Поиск ID пользователя...")
    users_response = requests.get(
        users_endpoint,
        headers=headers,
        params={'search': username},
        proxies=proxies,
        timeout=10
    )
    
    if users_response.status_code == 200:
        users = users_response.json()
        user_id = None
        for user in users:
            if user['slug'] == username or user['name'] == username:
                user_id = user['id']
                print(f"   Найден ID пользователя: {user_id}")
                break
        
        if not user_id:
            print("   Пользователь не найден, пробуем без указания автора")
            user_id = None
    else:
        print(f"   Ошибка поиска пользователя: {users_response.status_code}")
        user_id = None
        
except Exception as e:
    print(f"   Ошибка: {str(e)}")
    user_id = None

# Теперь пробуем создать статью
print("\n2. Попытка создания статьи...")

test_article = {
    'title': 'ISP прокси: преимущества и сценарии использования',
    'content': '''<h2>Что такое ISP прокси</h2>
<p>ISP прокси — это уникальный тип прокси-серверов, которые предоставляются интернет-провайдерами. В отличие от обычных прокси, ISP прокси используют реальные IP-адреса, выделенные провайдерами, что делает их практически неотличимыми от обычных пользовательских подключений.</p>

<h2>Преимущества ISP прокси</h2>
<p>Основные преимущества ISP прокси включают:</p>
<ul>
<li>Высокий уровень доверия со стороны веб-сервисов</li>
<li>Минимальный риск блокировки</li>
<li>Стабильное соединение</li>
<li>Высокая скорость работы</li>
</ul>

<p><a href="https://proxywing.com/ru/proxies-isp">ISP прокси</a> являются идеальным решением для задач, требующих максимальной анонимности и надежности.</p>

<h2>Сценарии использования</h2>
<p>ISP прокси идеально подходят для парсинга сайтов, работы с социальными сетями, проверки позиций сайтов и других задач, где важна надежность и минимальный риск блокировки.</p>''',
    'status': 'draft',
    'categories': [10]  # Категория "Технические решения"
}

# Добавляем автора если найден
if user_id:
    test_article['author'] = user_id
    print(f"   Указываем автора: ID {user_id}")
else:
    print("   Без указания автора")

try:
    response = requests.post(
        posts_endpoint,
        headers=headers,
        json=test_article,
        proxies=proxies,
        timeout=30
    )
    
    print(f"Статус: {response.status_code}")
    
    if response.status_code == 201:
        post_info = response.json()
        print("✅ СТАТЬЯ СОЗДАНА УСПЕШНО!")
        print(f"   ID: {post_info['id']}")
        print(f"   Заголовок: {post_info['title']['rendered']}")
        print(f"   Ссылка: {post_info['link']}")
        print(f"   Статус: {post_info['status']}")
        print(f"   Автор: {post_info.get('author', 'Не указан')}")
        
        # Пробуем опубликовать
        print("\n3. Публикация статьи...")
        publish_response = requests.post(
            f"{posts_endpoint}/{post_info['id']}",
            headers=headers,
            json={'status': 'publish'},
            proxies=proxies,
            timeout=30
        )
        
        if publish_response.status_code == 200:
            print("✅ СТАТЬЯ ОПУБЛИКОВАНА!")
            published_info = publish_response.json()
            print(f"   Финальная ссылка: {published_info['link']}")
            print(f"   Статус: {published_info['status']}")
        else:
            print(f"❌ Ошибка публикации: {publish_response.status_code}")
            print(f"   Ответ: {publish_response.text}")
            
    else:
        print(f"❌ Ошибка: {response.status_code}")
        print(f"   Ответ: {response.text}")
        
        # Анализ ошибки
        if "не разрешено создавать записи от лица этого пользователя" in response.text:
            print("\n💡 ПРОБЛЕМА: Ограничение WordPress на создание записей")
            print("РЕШЕНИЕ:")
            print("1. Проверьте плагины безопасности в WordPress")
            print("2. Отключите плагины, ограничивающие REST API")
            print("3. Или создайте нового пользователя с правами администратора")
        
except Exception as e:
    print(f"❌ Исключение: {str(e)}")