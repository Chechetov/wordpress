"""
Модуль для генерации контента с использованием OpenAI API
"""

import openai
import logging
import time
from typing import Dict, Optional
import re

logger = logging.getLogger(__name__)


class ContentGenerator:
    """Класс для генерации контента статей через OpenAI API"""
    
    def __init__(self, api_key: str, model: str = "gpt-4"):
        """
        Инициализация генератора контента
        
        Args:
            api_key: OpenAI API ключ
            model: Модель для генерации (gpt-3.5-turbo, gpt-4)
        """
        self.client = openai.OpenAI(api_key=api_key)
        self.model = model
        
    def generate_article_content(
        self, 
        topic: str, 
        anchor: str, 
        url: str, 
        target_words: int = 1750
    ) -> Dict[str, str]:
        """
        Генерация контента статьи с встраиванием анкорной ссылки
        
        Args:
            topic: Тема статьи
            anchor: Анкор для ссылки
            url: URL для ссылки
            target_words: Целевое количество слов
            
        Returns:
            Словарь с заголовком и содержанием статьи в HTML формате
        """
        try:
            # Создаем промпт для генерации статьи
            prompt = self._create_content_prompt(topic, anchor, url, target_words)
            
            logger.info(f"Генерация контента для темы: {topic}")
            
            # Генерируем контент через OpenAI API
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system", 
                        "content": "Ты - профессиональный копирайтер, который создает качественные SEO-оптимизированные статьи для WordPress."
                    },
                    {
                        "role": "user", 
                        "content": prompt
                    }
                ],
                temperature=0.7,
                max_tokens=3500  # Примерно 2500-3000 слов
            )
            
            content = response.choices[0].message.content
            
            # Парсим заголовок и содержание
            title, body = self._parse_content(content, topic)
            
            # Проверяем, что ссылка встроена корректно
            if not self._validate_link_insertion(body, anchor, url):
                # Если ссылка не встроена, встраиваем ее принудительно
                body = self._insert_link_manually(body, anchor, url)
            
            logger.info(f"Контент успешно сгенерирован. Длина: {len(body)} символов")
            
            return {
                'title': title,
                'content': body,
                'word_count': len(body.split())
            }
            
        except Exception as e:
            logger.error(f"Ошибка при генерации контента для темы '{topic}': {str(e)}")
            raise
    
    def _create_content_prompt(self, topic: str, anchor: str, url: str, target_words: int) -> str:
        """Создание промпта для генерации контента"""
        
        return f"""
Напиши качественную, SEO-оптимизированную статью на тему "{topic}".

ТРЕБОВАНИЯ:
1. Объем статьи: ~{target_words} слов
2. Структура: заголовок H1 + несколько подзаголовков H2/H3
3. Тон: информативный, экспертный, но доступный для понимания
4. Формат: HTML (с тегами <h2>, <h3>, <p>, <strong>, <em>, <ul>, <ol>, <li>)
5. Естественное встраивание анкорной ссылки: "<a href="{url}">{anchor}</a>" в середину статьи (не в начале и не в конце)
6. Ссылка должна выглядеть естественно и быть релевантной контексту

СТРУКТУРА СТАТЬИ:
- Привлекательный заголовок H1 (не более 60 символов)
- Краткое вступление (2-3 предложения)
- Основная часть с 3-4 подзаголовками
- Практические советы или примеры
- Заключение с выводами

ВАЖНО:
- Ссылка должна быть встроена органично в релевантный контекст
- Избегай ключевого спама
- Контент должен быть уникальным и полезным для читателей
- Используй HTML форматирование для улучшения читаемости

Начни сразу с заголовка H1, без дополнительного текста перед ним.
"""
    
    def _parse_content(self, content: str, topic: str) -> tuple:
        """
        Парсинг сгенерированного контента
        
        Args:
            content: Сырой контент от OpenAI
            topic: Оригинальная тема
            
        Returns:
            Кортеж (заголовок, содержание)
        """
        lines = content.strip().split('\n')
        
        # Ищем заголовок H1
        title = None
        body_lines = []
        
        for line in lines:
            line = line.strip()
            if line.startswith('<h1>') or (not title and not line.startswith('<') and len(line) < 100):
                if line.startswith('<h1>'):
                    title = re.sub(r'<h1.*?>(.*?)</h1>', r'\1', line)
                else:
                    title = line
                    body_lines.append(f"<h1>{line}</h1>")
            else:
                if line:  # Пропускаем пустые строки
                    body_lines.append(line)
        
        # Если заголовок не найден, создаем из темы
        if not title:
            title = topic
            body_lines.insert(0, f"<h1>{topic}</h1>")
        
        # Формируем тело статьи
        body = '\n\n'.join(body_lines)
        
        return title, body
    
    def _validate_link_insertion(self, content: str, anchor: str, url: str) -> bool:
        """Проверка корректности встраивания ссылки"""
        
        # Проверяем наличие ссылки в контенте
        link_pattern = f'<a href="{url}">{anchor}</a>'
        return link_pattern in content
    
    def _insert_link_manually(self, content: str, anchor: str, url: str) -> str:
        """Принудительное встраивание ссылки в середину контента"""
        
        # Разделяем контент на предложения
        sentences = re.split(r'(?<=[.!?])\s+', content)
        
        if len(sentences) < 3:
            return content  # Too short to insert naturally
        
        # Находим середину контента
        middle_index = len(sentences) // 2
        
        # Ищем подходящее место для вставки (не в заголовке)
        insert_index = middle_index
        for i in range(middle_index, min(middle_index + 5, len(sentences))):
            if '<h' not in sentences[i] and len(sentences[i]) > 20:
                insert_index = i
                break
        
        # Вставляем ссылку
        link_html = f' <a href="{url}">{anchor}</a> '
        sentences[insert_index] = sentences[insert_index] + link_html
        
        return ' '.join(sentences)
    
    def generate_article_title(self, topic: str) -> str:
        """
        Генерация привлекательного заголовка для статьи
        
        Args:
            topic: Тема статьи
            
        Returns:
            Заголовок статьи
        """
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "Ты - специалист по SEO и созданию заголовков. Создавай короткие, привлекательные заголовки до 60 символов."
                    },
                    {
                        "role": "user",
                        "content": f"Придумай привлекательный SEO-заголовок для статьи на тему: {topic}"
                    }
                ],
                temperature=0.7,
                max_tokens=50
            )
            
            title = response.choices[0].message.content.strip()
            
            # Удаляем возможные HTML теги и кавычки
            title = re.sub(r'<[^>]+>', '', title)
            title = title.strip('"\'')
            
            return title if title else topic
            
        except Exception as e:
            logger.warning(f"Не удалось сгенерировать заголовок, использую исходную тему: {str(e)}")
            return topic