"""
Модуль для генерации изображений через Google Gemini API
"""

import io
import logging
import time
from typing import Optional, Dict
from pathlib import Path
from PIL import Image
from google import genai
from google.genai import types

logger = logging.getLogger(__name__)


class ImageGenerator:
    """Класс для генерации изображений через Google Gemini API"""

    def __init__(self, api_key: str, model: str = "gemini-3.1-flash-image-preview"):
        """
        Инициализация генератора изображений

        Args:
            api_key: Google API ключ
            model: Модель для генерации
        """
        self.client = genai.Client(api_key=api_key)
        self.model = model

    def generate_featured_image(self, topic: str, article_title: str) -> Optional[Dict[str, str]]:
        """
        Генерация изображения для обложки статьи

        Args:
            topic: Тема статьи
            article_title: Заголовок статьи

        Returns:
            Словарь с информацией об изображении или None в случае ошибки
        """
        try:
            prompt = self._create_image_prompt(topic, article_title)

            logger.info(f"Генерация изображения для темы: {topic}")

            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_modalities=['IMAGE'],
                )
            )

            for part in response.candidates[0].content.parts:
                if part.inline_data is not None:
                    raw_data = part.inline_data.data
                    webp_data = self._convert_to_webp(raw_data)
                    logger.info(f"Изображение: {len(raw_data)} -> {len(webp_data)} байт (WebP)")
                    return {
                        'data': webp_data,
                        'prompt': prompt,
                        'size': 'auto'
                    }

            logger.warning("Gemini не вернул изображений")
            return None

        except Exception as e:
            logger.error(f"Ошибка при генерации изображения для темы '{topic}': {str(e)}")
            return None

    def _convert_to_webp(self, image_data: bytes, quality: int = 80) -> bytes:
        """Конвертация изображения в WebP"""
        img = Image.open(io.BytesIO(image_data))
        output = io.BytesIO()
        img.save(output, format='WebP', quality=quality)
        return output.getvalue()

    def _create_image_prompt(self, topic: str, article_title: str) -> str:
        """
        Создание промпта для генерации изображения
        """
        base_prompt = f"Professional, high-quality illustration related to: {topic}"

        if article_title and article_title != topic:
            base_prompt += f" - {article_title}"

        prompt = f"""{base_prompt}.

Style requirements:
- Modern, clean, professional design
- Bright, appealing colors
- Suitable for blog/article featured image
- No text or letters in the image
- Web-safe, appropriate for professional blog
- High resolution, detailed
- Digital illustration style"""

        return prompt.strip()

    def save_image_locally(self, image_data: bytes, filename: str, save_dir: str = "images") -> Optional[str]:
        """
        Сохранение изображения в локальный файл
        """
        try:
            save_path = Path(save_dir)
            save_path.mkdir(exist_ok=True)

            if not filename.lower().endswith(('.png', '.jpg', '.jpeg')):
                filename += '.jpg'

            file_path = save_path / filename

            with open(file_path, 'wb') as f:
                f.write(image_data)

            logger.info(f"Изображение сохранено: {file_path}")
            return str(file_path)

        except Exception as e:
            logger.error(f"Ошибка при сохранении изображения: {str(e)}")
            return None
