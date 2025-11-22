"""
Content Variations - вариативность контента для защиты от обнаружения сети
Разные стили, голоса, структуры для уникальности каждого сайта
"""

import random
from typing import Dict, List, Optional
from dataclasses import dataclass


@dataclass
class ContentStyle:
    """Стиль контента"""
    name: str
    description: str
    system_prompt: str
    structure_hints: str
    formatting_rules: Dict[str, any]


# Библиотека стилей контента
CONTENT_STYLES: Dict[str, ContentStyle] = {
    "formal_expert": ContentStyle(
        name="Формальный эксперт",
        description="Серьёзный экспертный стиль с академическим оттенком",
        system_prompt="""Ты - авторитетный эксперт в своей области. Пишешь серьёзные, глубокие статьи
с опорой на факты и исследования. Используешь профессиональную терминологию, но объясняешь
сложные концепции доступно. Избегаешь разговорных выражений и эмоциональных оценок.""",
        structure_hints="Введение с тезисом → Основные разделы с подзаголовками → Практические выводы → Заключение",
        formatting_rules={
            "use_lists": True,
            "use_quotes": False,
            "paragraph_length": "long",
            "heading_style": "informative"
        }
    ),

    "casual_friendly": ContentStyle(
        name="Дружеский разговорный",
        description="Лёгкий, дружелюбный стиль как беседа с другом",
        system_prompt="""Ты - дружелюбный блогер, который делится полезным опытом. Пишешь просто и понятно,
как будто рассказываешь другу. Используешь разговорные обороты, иногда шутишь. Обращаешься к читателю
на "ты". Делишься личными примерами и историями.""",
        structure_hints="Захватывающее начало → История/пример → Основной контент → Советы → Призыв к действию",
        formatting_rules={
            "use_lists": True,
            "use_quotes": True,
            "paragraph_length": "short",
            "heading_style": "catchy"
        }
    ),

    "practical_guide": ContentStyle(
        name="Практическое руководство",
        description="Чёткие пошаговые инструкции",
        system_prompt="""Ты - технический писатель, создающий чёткие практические руководства.
Твои статьи - это пошаговые инструкции с конкретными действиями. Минимум воды, максимум пользы.
Каждый шаг понятен и выполним. Используешь нумерованные списки и чек-листы.""",
        structure_hints="Что понадобится → Пошаговая инструкция → Возможные проблемы → Результат",
        formatting_rules={
            "use_lists": True,
            "use_quotes": False,
            "paragraph_length": "medium",
            "heading_style": "action"
        }
    ),

    "storyteller": ContentStyle(
        name="Рассказчик историй",
        description="Нарративный стиль с историями и примерами",
        system_prompt="""Ты - талантливый рассказчик. Каждую тему раскрываешь через истории,
примеры из жизни, кейсы. Вовлекаешь читателя эмоционально. Создаёшь интригу и удерживаешь внимание.
Полезная информация подаётся через призму историй.""",
        structure_hints="Захватывающая история → Мораль/урок → Развитие темы → Ещё примеры → Выводы",
        formatting_rules={
            "use_lists": False,
            "use_quotes": True,
            "paragraph_length": "varied",
            "heading_style": "intriguing"
        }
    ),

    "analytical": ContentStyle(
        name="Аналитический",
        description="Глубокий анализ с данными и сравнениями",
        system_prompt="""Ты - аналитик, который глубоко исследует темы. Приводишь статистику,
сравнения, анализируешь плюсы и минусы. Рассматриваешь тему с разных сторон. Делаешь
обоснованные выводы на основе фактов. Используешь таблицы и структурированные сравнения.""",
        structure_hints="Обзор проблемы → Анализ данных → Сравнение вариантов → Плюсы/минусы → Рекомендации",
        formatting_rules={
            "use_lists": True,
            "use_quotes": False,
            "paragraph_length": "medium",
            "heading_style": "analytical"
        }
    ),

    "news_reporter": ContentStyle(
        name="Новостной репортёр",
        description="Информационный стиль как в СМИ",
        system_prompt="""Ты - журналист информационного издания. Пишешь чётко, по существу,
отвечая на вопросы: что, где, когда, почему, как. Избегаешь личных оценок, придерживаешься
фактов. Структура - перевёрнутая пирамида: главное вначале.""",
        structure_hints="Лид (главное) → Детали → Контекст → Комментарии → Прогноз",
        formatting_rules={
            "use_lists": False,
            "use_quotes": True,
            "paragraph_length": "short",
            "heading_style": "informative"
        }
    ),
}

# Варианты структуры статей
ARTICLE_STRUCTURES = [
    {
        "name": "classic",
        "template": """
1. Введение (2-3 абзаца)
2. Основная часть:
   - Раздел 1 с H2
   - Раздел 2 с H2
   - Раздел 3 с H2
3. Заключение (1-2 абзаца)
"""
    },
    {
        "name": "listicle",
        "template": """
1. Краткое введение
2. Список из 5-7 пунктов, каждый с H2 заголовком
3. Краткое заключение с призывом к действию
"""
    },
    {
        "name": "problem_solution",
        "template": """
1. Описание проблемы (H2)
2. Почему это важно (H2)
3. Решение (H2) с подразделами (H3)
4. Практические шаги (H2)
5. Заключение
"""
    },
    {
        "name": "how_to",
        "template": """
1. Что вы узнаете / получите
2. Что понадобится (если применимо)
3. Пошаговая инструкция (шаги с H2)
4. Советы и подводные камни
5. FAQ (опционально)
"""
    },
    {
        "name": "comparison",
        "template": """
1. Введение: зачем сравнивать
2. Критерии сравнения
3. Вариант A (H2)
4. Вариант B (H2)
5. Сравнительная таблица
6. Рекомендации: что выбрать
"""
    },
]

# Варианты заголовков
TITLE_PATTERNS = {
    "ru": [
        "{topic}: полное руководство",
        "Как {action} - пошаговая инструкция",
        "{number} способов {action}",
        "{topic} в {year} году: что нужно знать",
        "Всё о {topic}: от А до Я",
        "{topic}: секреты и лайфхаки",
        "Почему {topic} важно и как это использовать",
        "{topic} для начинающих: простое объяснение",
        "Лучшие практики {topic}",
        "{topic}: мифы и реальность",
    ],
    "en": [
        "The Ultimate Guide to {topic}",
        "How to {action}: A Step-by-Step Guide",
        "{number} Ways to {action}",
        "{topic} in {year}: What You Need to Know",
        "Everything About {topic}: A to Z",
        "{topic}: Tips and Tricks",
        "Why {topic} Matters and How to Use It",
        "{topic} for Beginners: A Simple Explanation",
        "{topic} Best Practices",
        "{topic}: Myths vs Reality",
    ]
}


class ContentVariator:
    """Генератор вариаций контента"""

    def __init__(self, default_language: str = "ru"):
        self.default_language = default_language

    def get_random_style(self) -> ContentStyle:
        """Получение случайного стиля"""
        return random.choice(list(CONTENT_STYLES.values()))

    def get_style_by_name(self, name: str) -> Optional[ContentStyle]:
        """Получение стиля по имени"""
        return CONTENT_STYLES.get(name)

    def get_random_structure(self) -> dict:
        """Получение случайной структуры статьи"""
        return random.choice(ARTICLE_STRUCTURES)

    def generate_title_variations(self, topic: str, count: int = 5, language: str = None) -> List[str]:
        """
        Генерация вариаций заголовков

        Args:
            topic: Тема статьи
            count: Количество вариаций
            language: Язык (ru/en)

        Returns:
            Список вариантов заголовков
        """
        lang = language or self.default_language
        patterns = TITLE_PATTERNS.get(lang, TITLE_PATTERNS["ru"])

        import datetime
        year = datetime.datetime.now().year

        variations = []
        for pattern in random.sample(patterns, min(count, len(patterns))):
            title = pattern.format(
                topic=topic,
                action=topic.lower(),
                number=random.choice([3, 5, 7, 10]),
                year=year
            )
            variations.append(title)

        return variations

    def build_generation_prompt(
        self,
        topic: str,
        anchor: str,
        url: str,
        style: ContentStyle = None,
        structure: dict = None,
        word_count: int = 1750,
        language: str = None
    ) -> str:
        """
        Построение промпта для генерации с учётом стиля и структуры

        Args:
            topic: Тема статьи
            anchor: Анкорный текст
            url: URL для ссылки
            style: Стиль контента
            structure: Структура статьи
            word_count: Целевое количество слов
            language: Язык

        Returns:
            Готовый промпт для LLM
        """
        lang = language or self.default_language
        style = style or self.get_random_style()
        structure = structure or self.get_random_structure()

        lang_instruction = "на русском языке" if lang == "ru" else "in English"

        prompt = f"""
Напиши статью {lang_instruction} на тему: "{topic}"

СТИЛЬ НАПИСАНИЯ:
{style.system_prompt}

СТРУКТУРА СТАТЬИ:
{structure['template']}

ТРЕБОВАНИЯ:
1. Объём: примерно {word_count} слов
2. Формат: HTML (теги <h2>, <h3>, <p>, <ul>, <ol>, <li>, <strong>, <em>)
3. Естественно встрой ссылку <a href="{url}">{anchor}</a> в середину статьи
4. Ссылка должна органично вписываться в контекст
5. Заголовок H1 - привлекательный, до 60 символов

ФОРМАТИРОВАНИЕ:
- Используй списки: {'да' if style.formatting_rules.get('use_lists') else 'минимально'}
- Используй цитаты: {'да' if style.formatting_rules.get('use_quotes') else 'нет'}
- Длина абзацев: {style.formatting_rules.get('paragraph_length', 'средняя')}

Начни сразу с заголовка H1.
"""
        return prompt

    def get_system_prompt_for_style(self, style: ContentStyle = None) -> str:
        """Получение system prompt для стиля"""
        style = style or self.get_random_style()
        return style.system_prompt


# Синглтон для удобства
_variator: Optional[ContentVariator] = None


def get_variator(language: str = "ru") -> ContentVariator:
    """Получение экземпляра вариатора"""
    global _variator
    if _variator is None:
        _variator = ContentVariator(language)
    return _variator
