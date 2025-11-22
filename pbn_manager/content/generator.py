"""
Улучшенный Content Generator с вариативностью стилей
Интеграция с существующим генератором контента
"""

import logging
import re
import random
from typing import Dict, Optional, List
from dataclasses import dataclass

import openai

from .variations import ContentVariator, ContentStyle, get_variator

logger = logging.getLogger(__name__)


@dataclass
class GeneratedArticle:
    """Результат генерации статьи"""
    title: str
    content: str
    word_count: int
    style_used: str
    structure_used: str
    language: str
    has_anchor_link: bool


class PBNContentGenerator:
    """
    Генератор контента для PBN с вариативностью стилей
    Расширяет функциональность базового ContentGenerator
    """

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4",
        default_language: str = "ru"
    ):
        """
        Инициализация генератора

        Args:
            api_key: OpenAI API ключ
            model: Модель для генерации
            default_language: Язык по умолчанию
        """
        self.client = openai.OpenAI(api_key=api_key)
        self.model = model
        self.default_language = default_language
        self.variator = ContentVariator(default_language)

    def generate_article(
        self,
        topic: str,
        anchor: str = None,
        url: str = None,
        style: str = None,
        word_count: int = 1750,
        language: str = None,
        site_fingerprint: dict = None
    ) -> GeneratedArticle:
        """
        Генерация статьи с учётом вариативности

        Args:
            topic: Тема статьи
            anchor: Анкорный текст для ссылки
            url: URL для ссылки
            style: Стиль контента (если None - случайный)
            word_count: Целевое количество слов
            language: Язык статьи
            site_fingerprint: Профиль сайта (для консистентности стиля)

        Returns:
            GeneratedArticle с результатом
        """
        lang = language or self.default_language

        # Определяем стиль
        if site_fingerprint and 'content_style' in site_fingerprint:
            style_name = site_fingerprint['content_style']
            content_style = self.variator.get_style_by_name(style_name)
        elif style:
            content_style = self.variator.get_style_by_name(style)
        else:
            content_style = self.variator.get_random_style()

        if not content_style:
            content_style = self.variator.get_random_style()

        # Выбираем структуру
        structure = self.variator.get_random_structure()

        # Корректируем word_count если есть fingerprint
        if site_fingerprint and 'avg_word_count' in site_fingerprint:
            # Добавляем вариацию ±15%
            base_count = site_fingerprint['avg_word_count']
            word_count = int(base_count * random.uniform(0.85, 1.15))

        # Строим промпт
        prompt = self.variator.build_generation_prompt(
            topic=topic,
            anchor=anchor or "",
            url=url or "",
            style=content_style,
            structure=structure,
            word_count=word_count,
            language=lang
        )

        logger.info(f"Генерация статьи: {topic} (стиль: {content_style.name}, структура: {structure['name']})")

        try:
            # Генерируем контент
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": content_style.system_prompt
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.7,
                max_tokens=4000
            )

            raw_content = response.choices[0].message.content

            # Парсим результат
            title, body = self._parse_content(raw_content, topic)

            # Проверяем наличие ссылки
            has_link = False
            if anchor and url:
                has_link = self._check_link_present(body, anchor, url)
                if not has_link:
                    body = self._insert_link(body, anchor, url)
                    has_link = True

            # Считаем слова
            actual_word_count = len(body.split())

            logger.info(f"Статья сгенерирована: {title[:50]}... ({actual_word_count} слов)")

            return GeneratedArticle(
                title=title,
                content=body,
                word_count=actual_word_count,
                style_used=content_style.name,
                structure_used=structure['name'],
                language=lang,
                has_anchor_link=has_link
            )

        except Exception as e:
            logger.error(f"Ошибка генерации для темы '{topic}': {e}")
            raise

    def generate_batch(
        self,
        topics: List[dict],
        site_fingerprint: dict = None,
        language: str = None
    ) -> List[GeneratedArticle]:
        """
        Генерация нескольких статей

        Args:
            topics: Список словарей с topic, anchor, url
            site_fingerprint: Профиль сайта
            language: Язык

        Returns:
            Список сгенерированных статей
        """
        results = []

        for i, topic_data in enumerate(topics, 1):
            logger.info(f"Генерация {i}/{len(topics)}: {topic_data.get('topic', 'N/A')}")

            try:
                article = self.generate_article(
                    topic=topic_data['topic'],
                    anchor=topic_data.get('anchor'),
                    url=topic_data.get('url'),
                    site_fingerprint=site_fingerprint,
                    language=language
                )
                results.append(article)

            except Exception as e:
                logger.error(f"Ошибка при генерации статьи {i}: {e}")
                # Продолжаем со следующей

        return results

    def _parse_content(self, content: str, fallback_title: str) -> tuple:
        """Парсинг сгенерированного контента"""
        lines = content.strip().split('\n')

        title = None
        body_lines = []

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Ищем H1
            h1_match = re.match(r'<h1[^>]*>(.*?)</h1>', line, re.IGNORECASE)
            if h1_match and not title:
                title = h1_match.group(1).strip()
                continue

            # Если H1 без тегов в начале
            if not title and not line.startswith('<') and len(line) < 100:
                title = line
                body_lines.append(f"<h1>{line}</h1>")
                continue

            body_lines.append(line)

        if not title:
            title = fallback_title

        body = '\n\n'.join(body_lines)
        return title, body

    def _check_link_present(self, content: str, anchor: str, url: str) -> bool:
        """Проверка наличия ссылки"""
        # Проверяем точное совпадение
        exact = f'<a href="{url}">{anchor}</a>'
        if exact in content:
            return True

        # Проверяем с вариациями
        if f'href="{url}"' in content and anchor in content:
            return True

        return False

    def _insert_link(self, content: str, anchor: str, url: str) -> str:
        """Вставка ссылки в контент"""
        # Разбиваем на абзацы
        paragraphs = re.split(r'(</?(?:h[1-6]|p|ul|ol|li)[^>]*>)', content)

        # Ищем подходящее место в середине
        p_tags = [i for i, p in enumerate(paragraphs) if '<p>' in p.lower()]

        if len(p_tags) < 3:
            # Мало абзацев - вставляем просто в середину
            link = f' <a href="{url}">{anchor}</a>'
            mid = len(content) // 2
            # Ищем конец предложения
            end_sentence = content.rfind('. ', 0, mid)
            if end_sentence > 0:
                content = content[:end_sentence+1] + link + content[end_sentence+1:]
            return content

        # Вставляем в абзац около середины
        target_idx = p_tags[len(p_tags) // 2]
        link_html = f' <a href="{url}">{anchor}</a>'

        # Ищем конец предложения в этом абзаце
        para = paragraphs[target_idx]
        sentence_end = para.rfind('. ')
        if sentence_end > 0:
            paragraphs[target_idx] = para[:sentence_end+1] + link_html + para[sentence_end+1:]
        else:
            paragraphs[target_idx] = para + link_html

        return ''.join(paragraphs)

    def generate_title_variations(self, topic: str, count: int = 5) -> List[str]:
        """Генерация вариаций заголовков"""
        return self.variator.generate_title_variations(
            topic,
            count=count,
            language=self.default_language
        )


# Обратная совместимость с существующим кодом
class ContentGenerator(PBNContentGenerator):
    """Алиас для обратной совместимости"""

    def generate_article_content(
        self,
        topic: str,
        anchor: str,
        url: str,
        target_words: int = 1750
    ) -> Dict[str, str]:
        """
        Метод для совместимости со старым API

        Returns:
            Словарь с title, content, word_count
        """
        article = self.generate_article(
            topic=topic,
            anchor=anchor,
            url=url,
            word_count=target_words
        )

        return {
            'title': article.title,
            'content': article.content,
            'word_count': article.word_count
        }
