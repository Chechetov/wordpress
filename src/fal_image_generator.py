"""Генерация изображений-обложек через fal.ai (модель nano-banana).

Интерфейс совместим с src.image_generator.ImageGenerator:
generate_featured_image(topic, article_title) -> dict | None
"""

from __future__ import annotations

import logging
import requests

logger = logging.getLogger(__name__)

FAL_BASE = "https://fal.run"


class FalImageGenerator:
    """Генератор обложек через fal.ai nano-banana."""

    def __init__(self, api_key: str, model: str = "fal-ai/nano-banana"):
        self.api_key = api_key
        self.model = model

    def generate_featured_image(self, topic: str, article_title: str = "") -> dict | None:
        """Сгенерировать обложку.

        Возвращает {'data': bytes, 'content_type': str, 'ext': str, 'prompt': str}
        либо None при ошибке.
        """
        prompt = self._create_image_prompt(topic, article_title)
        try:
            logger.info(f"Генерация изображения (fal nano-banana): {topic}")
            r = requests.post(
                f"{FAL_BASE}/{self.model}",
                headers={
                    'Authorization': f'Key {self.api_key}',
                    'Content-Type': 'application/json',
                },
                json={
                    'prompt': prompt,
                    'num_images': 1,
                    'aspect_ratio': '16:9',
                    'output_format': 'jpeg',
                },
                timeout=180,
            )
            if r.status_code != 200:
                logger.error(f"fal.ai вернул {r.status_code}: {r.text[:300]}")
                return None

            images = r.json().get('images') or []
            if not images:
                logger.warning("fal.ai не вернул изображений")
                return None

            img_resp = requests.get(images[0]['url'], timeout=120)
            if img_resp.status_code != 200:
                logger.error(f"Не удалось скачать изображение: {img_resp.status_code}")
                return None

            logger.info(f"Изображение получено: {len(img_resp.content)} байт")
            return {
                'data': img_resp.content,
                'content_type': 'image/jpeg',
                'ext': 'jpg',
                'prompt': prompt,
            }

        except Exception as e:
            logger.error(f"Ошибка генерации изображения '{topic}': {e}")
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
