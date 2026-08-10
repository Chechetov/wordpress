"""Генерация изображений-обложек через OpenAI Images API (gpt-image-*).

Интерфейс совместим с src.fal_image_generator.FalImageGenerator и
src.image_generator.ImageGenerator:
generate_featured_image(topic, article_title) -> dict | None

Цены за картинку 1536x1024 (16:9), август 2026:
    gpt-image-2       low $0.005 | medium $0.041 | high $0.165
    gpt-image-1-mini  low $0.006 | medium $0.015 | high $0.052
"""

from __future__ import annotations

import base64
import logging
import os
import time

import requests

logger = logging.getLogger(__name__)

API_URL = "https://api.openai.com/v1/images/generations"


class OpenAIImageGenerator:
    """Генератор обложек через OpenAI gpt-image-2."""

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-image-2",
        quality: str = "low",
        size: str = "1536x1024",
        max_retries: int = 3,
    ):
        self.api_key = api_key
        self.model = model
        self.quality = quality
        self.size = size
        self.max_retries = max_retries

    def generate_featured_image(self, topic: str, article_title: str = "") -> dict | None:
        """Сгенерировать обложку.

        Возвращает {'data': bytes, 'content_type': str, 'ext': str, 'prompt': str}
        либо None при ошибке.
        """
        prompt = self._create_image_prompt(topic, article_title)

        for attempt in range(1, self.max_retries + 1):
            try:
                logger.info(
                    f"Генерация изображения (OpenAI {self.model}/{self.quality}): {topic}"
                )
                r = requests.post(
                    API_URL,
                    headers={
                        'Authorization': f'Bearer {self.api_key}',
                        'Content-Type': 'application/json',
                    },
                    json={
                        'model': self.model,
                        'prompt': prompt,
                        'size': self.size,
                        'quality': self.quality,
                        'n': 1,
                        'output_format': 'jpeg',
                    },
                    timeout=300,
                )

                if r.status_code == 200:
                    data = r.json().get('data') or []
                    if not data:
                        logger.warning("OpenAI не вернул изображений")
                        return None

                    image_bytes = base64.b64decode(data[0]['b64_json'])
                    logger.info(f"Изображение получено: {len(image_bytes)} байт")
                    return {
                        'data': image_bytes,
                        'content_type': 'image/jpeg',
                        'ext': 'jpg',
                        'prompt': prompt,
                    }

                # 429 / 5xx — имеет смысл повторить
                if r.status_code == 429 or r.status_code >= 500:
                    if attempt < self.max_retries:
                        pause = 10 * attempt
                        logger.warning(
                            f"OpenAI вернул {r.status_code}, повтор через {pause}с "
                            f"(попытка {attempt}/{self.max_retries})"
                        )
                        time.sleep(pause)
                        continue

                logger.error(f"OpenAI вернул {r.status_code}: {r.text[:300]}")
                return None

            except Exception as e:
                if attempt < self.max_retries:
                    logger.warning(f"Ошибка запроса к OpenAI ({e}), повтор...")
                    time.sleep(10 * attempt)
                    continue
                logger.error(f"Ошибка генерации изображения '{topic}': {e}")
                return None

        return None

    def _create_image_prompt(self, topic: str, article_title: str = "") -> str:
        base = f"Professional, high-quality illustration related to: {topic}"
        if article_title and article_title != topic:
            base += f" - {article_title}"
        return (
            f"{base}.\n\n"
            "Style requirements:\n"
            "- Modern, clean, professional design\n"
            "- Bright, appealing colors\n"
            "- Suitable for blog/article featured image\n"
            "- No text or letters in the image\n"
            "- Web-safe, appropriate for professional blog\n"
            "- High resolution, detailed\n"
            "- Digital illustration style"
        )

    def save_image_locally(
        self, image_data: bytes, filename: str, save_dir: str = "images"
    ) -> str | None:
        """Сохранить изображение в локальную папку."""
        try:
            os.makedirs(save_dir, exist_ok=True)
            path = os.path.join(save_dir, filename)
            with open(path, 'wb') as f:
                f.write(image_data)
            return path
        except Exception as e:
            logger.error(f"Не удалось сохранить изображение локально: {e}")
            return None
