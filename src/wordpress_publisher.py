"""
Модуль для работы с WordPress REST API
"""

import requests
import logging
import base64
import mimetypes
from typing import Dict, Optional, List
from urllib.parse import urljoin

logger = logging.getLogger(__name__)


class WordPressPublisher:
    """Класс для публикации контента в WordPress через REST API"""
    
    def __init__(self, site_url: str, username: str, app_password: str, proxies: Optional[Dict[str, str]] = None):
        """
        Инициализация издателя WordPress
        
        Args:
            site_url: URL сайта WordPress
            username: Имя пользователя WordPress
            app_password: Application Password для аутентификации
            proxies: Словарь с настройками прокси (опционально)
        """
        self.site_url = site_url.rstrip('/')
        self.username = username
        self.app_password = app_password
        self.proxies = proxies
        
        # Формируем заголовки авторизации
        credentials = f"{username}:{app_password}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        
        self.auth_headers = {
            'Authorization': f'Basic {encoded_credentials}',
            'Content-Type': 'application/json'
        }
        
        # API эндпоинты
        self.api_base = f"{self.site_url}/wp-json/wp/v2"
        self.media_endpoint = f"{self.api_base}/media"
        self.posts_endpoint = f"{self.api_base}/posts"
        self.categories_endpoint = f"{self.api_base}/categories"
        
        # Проверяем соединение
        self._test_connection()
    
    def _test_connection(self):
        """Проверка соединения с WordPress API"""
        try:
            # Проверяем доступность API через простой GET запрос к постам
            response = requests.get(
                self.posts_endpoint,
                headers=self.auth_headers,
                proxies=self.proxies,
                timeout=10
            )
            
            if response.status_code == 200:
                logger.info(f"Успешное подключение к WordPress API: {self.site_url}")
            elif response.status_code == 401:
                logger.error("Ошибка авторизации (401). Проверьте правильность имени пользователя и application password")
                raise requests.exceptions.RequestException(f"Ошибка авторизации: {response.status_code}")
            elif response.status_code == 403:
                logger.error("Доступ запрещен (403). Проверьте права пользователя и application password")
                logger.error(f"Ответ сервера: {response.text}")
                raise requests.exceptions.RequestException(f"Доступ запрещен: {response.status_code}")
            else:
                logger.error(f"Ошибка подключения к WordPress: {response.status_code}")
                logger.error(f"Ответ сервера: {response.text}")
                raise requests.exceptions.RequestException(f"Ошибка подключения: {response.status_code}")
                
        except Exception as e:
            logger.error(f"Не удалось подключиться к WordPress API: {str(e)}")
            raise
        
    def upload_image(self, image_data: bytes, filename: str, alt_text: str = "") -> Optional[Dict[str, int]]:
        """
        Загрузка изображения в медиабиблиотеку WordPress
        
        Args:
            image_data: Данные изображения в байтах
            filename: Имя файла
            alt_text: Alt-текст для изображения
            
        Returns:
            Словарь с ID загруженного медиа или None в случае ошибки
        """
        try:
            logger.info(f"Загрузка изображения: {filename}")
            
            # Определяем MIME тип
            mime_type, _ = mimetypes.guess_type(filename)
            if not mime_type:
                mime_type = 'image/png'  # по умолчанию
            
            # Формируем заголовки для загрузки медиа
            headers = self.auth_headers.copy()
            headers['Content-Type'] = mime_type
            headers['Content-Disposition'] = f'attachment; filename="{filename}"'
            
            # Загружаем изображение
            response = requests.post(
                self.media_endpoint,
                headers=headers,
                data=image_data,
                proxies=self.proxies,
                timeout=30
            )
            
            if response.status_code == 201:
                media_data = response.json()
                media_id = media_data['id']
                
                logger.info(f"Изображение успешно загружено. Media ID: {media_id}")
                
                # Обновляем alt-текст если указан
                if alt_text:
                    self._update_media_alt_text(media_id, alt_text)
                
                return {
                    'media_id': media_id,
                    'url': media_data.get('source_url', ''),
                    'title': media_data.get('title', {}).get('rendered', '')
                }
            else:
                logger.error(f"Ошибка загрузки изображения: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"Исключение при загрузке изображения: {str(e)}")
            return None
    
    def _update_media_alt_text(self, media_id: int, alt_text: str):
        """Обновление alt-текса для загруженного медиа"""
        try:
            response = requests.post(
                f"{self.media_endpoint}/{media_id}",
                headers=self.auth_headers,
                json={'alt_text': alt_text},
                proxies=self.proxies,
                timeout=10
            )
            
            if response.status_code == 200:
                logger.info(f"Alt-текст обновлен для media ID: {media_id}")
            else:
                logger.warning(f"Не удалось обновить alt-текст: {response.status_code}")
                
        except Exception as e:
            logger.warning(f"Ошибка при обновлении alt-текста: {str(e)}")
    
    def get_or_create_category(self, category_name: str) -> Optional[int]:
        """
        Получение ID категории по имени или создание новой
        
        Args:
            category_name: Название категории
            
        Returns:
            ID категории или None в случае ошибки
        """
        try:
            # Сначала ищем существующую категорию
            response = requests.get(
                self.categories_endpoint,
                headers=self.auth_headers,
                params={'search': category_name},
                proxies=self.proxies,
                timeout=10
            )
            
            if response.status_code == 200:
                categories = response.json()
                
                # Ищем точное совпадение
                for category in categories:
                    if category['name'].lower() == category_name.lower():
                        logger.info(f"Найдена существующая категория: {category_name} (ID: {category['id']})")
                        return category['id']
            
            # Если категория не найдена, создаем новую
            logger.info(f"Создание новой категории: {category_name}")
            
            create_response = requests.post(
                self.categories_endpoint,
                headers=self.auth_headers,
                json={'name': category_name},
                proxies=self.proxies,
                timeout=10
            )
            
            if create_response.status_code == 201:
                new_category = create_response.json()
                category_id = new_category['id']
                logger.info(f"Категория успешно создана: {category_name} (ID: {category_id})")
                return category_id
            else:
                logger.error(f"Ошибка создания категории: {create_response.status_code} - {create_response.text}")
                return None
                
        except Exception as e:
            logger.error(f"Ошибка при работе с категориями: {str(e)}")
            return None
    
    def create_post(
        self, 
        title: str, 
        content: str, 
        category_id: int, 
        featured_media_id: Optional[int] = None,
        status: str = 'publish',
        scheduled_date: Optional[str] = None
    ) -> Optional[Dict[str, int]]:
        """
        Создание поста в WordPress
        
        Args:
            title: Заголовок поста
            content: Содержание поста в HTML формате
            category_id: ID категории
            featured_media_id: ID изображения для обложки
            status: Статус поста ('publish', 'draft' или 'future')
            scheduled_date: Дата публикации в формате ISO 8601 (YYYY-MM-DDTHH:MM:SS)
            
        Returns:
            Словарь с информацией о созданном посте или None в случае ошибки
        """
        try:
            logger.info(f"Создание поста: {title}")
            if scheduled_date:
                logger.info(f"Запланирована публикация: {scheduled_date}")
            
            # Формируем данные поста
            post_data = {
                'title': title,
                'content': content,
                'status': status,
                'categories': [category_id],
                'featured_media': featured_media_id if featured_media_id else 0
            }
            
            # Добавляем дату публикации если указана
            if scheduled_date:
                post_data['date'] = scheduled_date
                # Для отложенной публикации WordPress должен использовать статус 'future'
                if status == 'publish' and scheduled_date:
                    post_data['status'] = 'future'
            
            # Создаем пост
            response = requests.post(
                self.posts_endpoint,
                headers=self.auth_headers,
                json=post_data,
                proxies=self.proxies,
                timeout=30
            )
            
            if response.status_code == 201:
                post_info = response.json()
                post_id = post_info['id']
                post_url = post_info.get('link', '')
                
                # Получаем фактическую дату публикации
                pub_date = post_info.get('date', '')
                if pub_date:
                    # Конвертируем в читаемый формат
                    from datetime import datetime
                    try:
                        dt = datetime.fromisoformat(pub_date.replace('Z', '+00:00'))
                        pub_date_formatted = dt.strftime('%Y-%m-%d %H:%M:%S')
                    except:
                        pub_date_formatted = pub_date
                else:
                    pub_date_formatted = 'Не указана'
                
                logger.info(f"Пост успешно создан. ID: {post_id}, URL: {post_url}")
                logger.info(f"Дата публикации: {pub_date_formatted}")
                
                return {
                    'post_id': post_id,
                    'url': post_url,
                    'status': post_info.get('status', ''),
                    'title': post_info.get('title', {}).get('rendered', ''),
                    'date': pub_date_formatted
                }
            else:
                logger.error(f"Ошибка создания поста: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"Исключение при создании поста: {str(e)}")
            return None
    
    def publish_article(
        self,
        title: str,
        content: str,
        category_name: str,
        image_data: Optional[bytes] = None,
        image_filename: str = "featured-image.png",
        image_alt_text: str = "",
        status: str = 'publish',
        scheduled_date: Optional[str] = None
    ) -> Optional[Dict[str, any]]:
        """
        Полный цикл публикации статьи с изображением
        
        Args:
            title: Заголовок статьи
            content: Содержание статьи
            category_name: Название категории
            image_data: Данные изображения для обложки
            image_filename: Имя файла изображения
            image_alt_text: Alt-текст для изображения
            status: Статус поста
            scheduled_date: Дата публикации в формате ISO 8601
            
        Returns:
            Словарь с результатом публикации
        """
        try:
            # 1. Получаем или создаем категорию
            category_id = self.get_or_create_category(category_name)
            if not category_id:
                logger.error(f"Не удалось получить/создать категорию: {category_name}")
                return None
            
            # 2. Загружаем изображение если предоставлено
            featured_media_id = None
            if image_data:
                media_info = self.upload_image(image_data, image_filename, image_alt_text)
                if media_info:
                    featured_media_id = media_info['media_id']
                else:
                    logger.warning("Не удалось загрузить изображение, продолжаю без обложки")
            
            # 3. Создаем пост
            post_info = self.create_post(
                title=title,
                content=content,
                category_id=category_id,
                featured_media_id=featured_media_id,
                status=status,
                scheduled_date=scheduled_date
            )
            
            if post_info:
                return {
                    'post_id': post_info['post_id'],
                    'url': post_info['url'],
                    'category_id': category_id,
                    'media_id': featured_media_id,
                    'status': post_info['status'],
                    'scheduled_date': post_info.get('date', scheduled_date)
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Ошибка при публикации статьи: {str(e)}")
            return None
    
    def get_post_info(self, post_id: int) -> Optional[Dict]:
        """Получение информации о посте"""
        try:
            response = requests.get(
                f"{self.posts_endpoint}/{post_id}",
                headers=self.auth_headers,
                proxies=self.proxies,
                timeout=10
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Ошибка получения информации о посте {post_id}: {response.status_code}")
                return None
                
        except Exception as e:
            logger.error(f"Ошибка при получении информации о посте: {str(e)}")
            return None