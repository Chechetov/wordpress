#!/usr/bin/env python3
"""
Скрипт для публикации готовых изображений в WordPress без генерации контента
"""

import os
import logging
import base64
import requests
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime, timedelta

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
media_endpoint = f"{api_base}/media"
posts_endpoint = f"{api_base}/posts"
categories_endpoint = f"{api_base}/categories"

# Настройки логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Данные для публикации
articles_data = [
    {
        "title": "ISP прокси: преимущества и сценарии использования",
        "content": """<h2>Что такое ISP прокси</h2>
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
<p>ISP прокси идеально подходят для парсинга сайтов, работы с социальными сетями, проверки позиций сайтов и других задач, где важна надежность и минимальный риск блокировки.</p>""",
        "anchor": "isp прокси",
        "url": "https://proxywing.com/ru/proxies-isp"
    },
    {
        "title": "В чем разница между ISP и другими видами прокси?",
        "content": """<h2>Основные отличия ISP прокси</h2>
<p>ISP прокси принципиально отличаются от других видов прокси-серверов своим происхождением и характеристиками. Если обычные прокси-серверы часто используют датацентрские IP-адреса, то ISP прокси предоставляют реальные IP-адреса интернет-провайдеров.</p>

<h2>Сравнение с датацентрскими прокси</h2>
<p>Датацентрские прокси легко распознаются веб-сервисами и часто блокируются. ISP прокси, напротив, выглядят как обычные пользователи интернета, что обеспечивает высокий уровень доверия со стороны сайтов.</p>

<h2>Преимущества перед резидентными прокси</h2>
<p>По сравнению с резидентными прокси, ISP прокси обеспечивают более стабильное соединение и высокую скорость, при этом сохраняя все преимущества реальных IP-адресов.</p>

<h2>Когда выбирать ISP прокси</h2>
<p>ISP прокси — лучший выбор для задач, требующих максимальной анонимности и надежности соединения.</p>""",
        "anchor": "",
        "url": ""
    },
    {
        "title": "Почему ISP прокси пользуются спросом у бизнеса?",
        "content": """<h2>Бизнес-преимущества ISP прокси</h2>
<p>Современный бизнес все активнее использует ISP прокси для решения различных задач. Этот спрос обусловлен уникальными характеристиками, которые отличают ISP прокси от других решений.</p>

<h2>Маркетинговые исследования</h2>
<p>Для проведения маркетинговых исследований и мониторинга конкурентов ISP прокси незаменимы. Они позволяют собирать данные без риска блокировки, обеспечивая точную и актуальную информацию.</p>

<h2>SEO-оптимизация</h2>
<p>Специалисты по SEO используют ISP прокси для проверки позиций сайтов в разных регионах, анализа поисковой выдачи и мониторинга конкуренции.</p>

<h2>Автоматизация бизнес-процессов</h2>
<p>При автоматизации рутинных задач, таких как размещение объявлений или работа с социальными сетями, ISP прокси обеспечивают стабильную работу без блокировок.</p>

<h2>Инвестиция в эффективность</h2>
<p>Использование ISP прокси становится стратегической инвестицией для бизнеса, ориентированного на цифровые технологии.</p>""",
        "anchor": "",
        "url": ""
    },
    {
        "title": "Как настроить ISP прокси для максимальной эффективности",
        "content": """<h2>Правильная настройка ISP прокси</h2>
<p>Максимальная эффективность ISP прокси достигается не только за счет их качественных характеристик, но и благодаря правильной настройке и использованию.</p>

<h2>Выбор провайдера и типа прокси</h2>
<p>При выборе ISP прокси важно учитывать репутацию провайдера, географическое расположение IP-адресов и технические характеристики. Надежный провайдер гарантирует стабильную работу и поддержку.</p>

<h2>Настройка ротации IP</h2>
<p>Правильная настройка ротации IP-адресов помогает избежать блокировок и обеспечивает равномерное распределение нагрузки. Некоторые задачи требуют статичных IP, другие — частой смены адресов.</p>

<h2>Оптимизация скорости соединения</h2>
<p>Для достижения максимальной скорости работы необходимо правильно настроить таймауты, количество одновременных подключений и выбрать оптимальное географическое расположение прокси.</p>

<h2>Мониторинг и аналитика</h2>
<p>Регулярный мониторинг работы прокси позволяет оперативно выявлять проблемы и оптимизировать производительность системы.</p>""",
        "anchor": "",
        "url": ""
    },
    {
        "title": "Советы по выбору лучшего ISP прокси",
        "content": """<h2>Критерии выбора ISP прокси</h2>
<p>Выбор качественного ISP прокси требует внимательного подхода и анализа нескольких ключевых факторов. Правильно выбранный прокси станет надежным инструментом для ваших задач.</p>

<h2>Надежность провайдера</h2>
<p>Основной критерий — репутация и надежность провайдера. Изучите отзывы, проверьте, как долго компания работает на рынке, какие гарантии предоставляет.</p>

<h2>Качество IP-адресов</h2>
<p>Обратите внимание на происхождение IP-адресов. Качественные ISP прокси используют адреса авторитетных провайдеров с хорошей репутацией в интернете.</p>

<h2>Техническая поддержка</h2>
<p>Наличие круглосуточной технической поддержки особенно важно при работе с критически важными задачами.</p>

<h2>Гибкость тарифных планов</h2>
<p>Выбирайте провайдеров, предлагающих гибкие условия оплаты и возможность масштабирования сервиса в соответствии с вашими потребностями.</p>

<h2>Тестовый период</h2>
<p>Возможность протестировать прокси перед покупкой поможет оценить их реальное качество и пригодность для ваших задач.</p>""",
        "anchor": "",
        "url": ""
    },
    {
        "title": "Использование ISP прокси в маркетинге и аналитике",
        "content": """<h2>Маркетинговый потенциал ISP прокси</h2>
<p>ISP прокси открывают широкие возможности для маркетологов и аналитиков, позволяя получать точные данные и эффективно автоматизировать рабочие процессы.</p>

<h2>Сбор конкурентной информации</h2>
<p>С помощью ISP прокси можно безопасно собирать информацию о конкурентах: цены, акции, маркетинговые стратегии. Высокий уровень доверия со стороны сайтов обеспечивает беспрепятственный доступ к данным.</p>

<h2>Парсинг маркетплейсов</h2>
<p>Для анализа товарных предложений, ценообразования и мониторинга продаж на маркетплейсах ISP прокси незаменимы. Они позволяют собирать большие объемы данных без блокировок.</p>

<h2>SMM-маркетинг</h2>
<p>В социальных сетях ISP прокси используются для управления несколькими аккаунтами, автоматизации публикации и анализа активности аудитории.</p>

<h2>SEO-аналитика</h2>
<p>Специалисты по SEO используют ISP прокси для проверки позиций, анализа поисковой выдачи в разных регионах и мониторинга алгоритмов поисковых систем.</p>

<h2>Веб-аналитика</h2>
<p>Для сбора данных о посещаемости сайтов, анализа пользовательского поведения и исследования конверсий ISP прокси обеспечивают точную и объективную информацию.</p>""",
        "anchor": "",
        "url": ""
    }
]

def get_or_create_category(category_name):
    """Получить ID существующей категории или создать новую"""
    try:
        # Ищем существующую категорию
        response = requests.get(
            categories_endpoint,
            headers=headers,
            params={'search': category_name},
            proxies=proxies,
            timeout=10
        )
        
        if response.status_code == 200:
            categories = response.json()
            for category in categories:
                if category['name'].lower() == category_name.lower():
                    logger.info(f"Найдена категория: {category_name} (ID: {category['id']})")
                    return category['id']
        
        # Пробуем создать новую категорию
        logger.info(f"Попытка создать категорию: {category_name}")
        create_response = requests.post(
            categories_endpoint,
            headers=headers,
            json={'name': category_name},
            proxies=proxies,
            timeout=10
        )
        
        if create_response.status_code == 201:
            new_category = create_response.json()
            logger.info(f"Категория создана: {category_name} (ID: {new_category['id']})")
            return new_category['id']
        else:
            logger.warning(f"Не удалось создать категорию {category_name}: {create_response.status_code}")
            # Используем категорию по умолчанию "Без рубрики" (ID: 1)
            return 1
            
    except Exception as e:
        logger.error(f"Ошибка при работе с категориями: {str(e)}")
        return 1

def upload_image(image_path, filename):
    """Загрузить изображение в WordPress"""
    try:
        with open(image_path, 'rb') as f:
            image_data = f.read()
        
        upload_headers = headers.copy()
        upload_headers['Content-Type'] = 'image/png'
        upload_headers['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        response = requests.post(
            media_endpoint,
            headers=upload_headers,
            data=image_data,
            proxies=proxies,
            timeout=30
        )
        
        if response.status_code == 201:
            media_data = response.json()
            logger.info(f"Изображение загружено: {filename} (Media ID: {media_data['id']})")
            return media_data['id']
        else:
            logger.error(f"Ошибка загрузки изображения: {response.status_code}")
            return None
            
    except Exception as e:
        logger.error(f"Ошибка при загрузке изображения: {str(e)}")
        return None

def publish_article(title, content, category_id, media_id=None, scheduled_date=None):
    """Опубликовать статью в WordPress"""
    try:
        post_data = {
            'title': title,
            'content': content,
            'status': 'future' if scheduled_date else 'publish',
            'categories': [category_id],
            'featured_media': media_id if media_id else 0
        }
        
        if scheduled_date:
            post_data['date'] = scheduled_date
        
        response = requests.post(
            posts_endpoint,
            headers=headers,
            json=post_data,
            proxies=proxies,
            timeout=30
        )
        
        if response.status_code == 201:
            post_info = response.json()
            logger.info(f"Статья опубликована: {title} (ID: {post_info['id']})")
            return post_info
        else:
            logger.error(f"Ошибка публикации статьи: {response.status_code} - {response.text}")
            return None
            
    except Exception as e:
        logger.error(f"Ошибка при публикации статьи: {str(e)}")
        return None

def main():
    """Главная функция"""
    logger.info("Начинаю публикацию готовых статей...")
    
    images_dir = Path("images")
    if not images_dir.exists():
        logger.error("Папка с изображениями не найдена")
        return
    
    # Получаем список изображений
    image_files = sorted(list(images_dir.glob("article_*.png")))
    
    if len(image_files) == 0:
        logger.error("Изображения не найдены")
        return
    
    logger.info(f"Найдено {len(image_files)} изображений")
    
    # Получаем ID категории (используем существующую категорию Технические решения)
    category_id = get_or_create_category("Технические решения")
    
    # Расчет времени для отложенной публикации
    interval_hours = 52.0
    start_time = datetime.now() + timedelta(hours=1)
    
    published_count = 0
    
    for i, (image_file, article_data) in enumerate(zip(image_files, articles_data)):
        try:
            logger.info(f"Публикация статьи {i+1}/{len(image_files)}: {article_data['title']}")
            
            # Загружаем изображение
            media_id = upload_image(image_file, image_file.name)
            
            # Рассчитываем время публикации
            publish_time = start_time + timedelta(hours=interval_hours * i)
            scheduled_date = publish_time.isoformat()
            
            logger.info(f"Запланирована публикация: {publish_time.strftime('%Y-%m-%d %H:%M')}")
            
            # Публикуем статью
            result = publish_article(
                title=article_data['title'],
                content=article_data['content'],
                category_id=category_id,
                media_id=media_id,
                scheduled_date=scheduled_date
            )
            
            if result:
                published_count += 1
                logger.info(f"Статья успешно запланирована: {result.get('link', 'URL недоступен')}")
            
            # Небольшая задержка между запросами
            import time
            time.sleep(2)
            
        except Exception as e:
            logger.error(f"Ошибка при обработке статьи {i+1}: {str(e)}")
    
    logger.info(f"Публикация завершена. Запланировано статей: {published_count}/{len(image_files)}")
    
    if published_count > 0:
        first_time = start_time.strftime('%Y-%m-%d %H:%M')
        last_time = (start_time + timedelta(hours=interval_hours * (published_count - 1))).strftime('%Y-%m-%d %H:%M')
        logger.info(f"Первая публикация: {first_time}")
        logger.info(f"Последняя публикация: {last_time}")
        logger.info("WordPress автоматически опубликует статьи в указанное время.")

if __name__ == "__main__":
    main()