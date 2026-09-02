"""Генерация изображений-обложек через OpenAI Images API (gpt-image-*).

Интерфейс совместим с src.fal_image_generator.FalImageGenerator и
src.image_generator.ImageGenerator:
generate_featured_image(topic, article_title) -> dict | None

Цены за картинку 1536x1024 (16:9), август 2026:
    gpt-image-2       low $0.005 | medium $0.041 | high $0.165
    gpt-image-1-mini  low $0.006 | medium $0.015 | high $0.052

Отдаёт WebP. API возвращает его почти без сжатия (~1.1 МБ на картинку),
поэтому перед выдачей файл пережимается через Pillow: quality=90 даёт
~128 КБ при том же разрешении и без заметной потери. Нет Pillow — вернём
как есть, но в лог уйдёт предупреждение.
"""

from __future__ import annotations

import base64
import io
import logging
import os
import time

import requests

try:
    from PIL import Image
except ImportError:  # пережатия не будет, но генерация продолжит работать
    Image = None

logger = logging.getLogger(__name__)

API_URL = "https://api.openai.com/v1/images/generations"

FORMATS = {
    'webp': ('image/webp', 'webp'),
    'jpeg': ('image/jpeg', 'jpg'),
    'png': ('image/png', 'png'),
}

# Свой стиль иллюстраций на каждого донора: одинаковые картинки по всей
# сети — такой же отпечаток, как одинаковая тема.
STYLES = {
    'flat':        "flat vector illustration, bold simple shapes, minimal detail",
    'isometric':   "isometric 3D illustration, soft shadows, muted palette",
    'photo':       "realistic photograph, natural light, shallow depth of field",
    'line':        "clean line art with a single accent colour, lots of white space",
    'collage':     "paper-cut collage style, layered textures, warm tones",
    'gradient':    "soft gradient mesh illustration, abstract shapes, airy",
    'sketch':      "hand-drawn sketch style, pencil texture, understated colour",
    'editorial':   "editorial magazine illustration, strong composition, limited palette",
}


class OpenAIImageGenerator:
    """Генератор обложек через OpenAI gpt-image-2."""

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-image-2",
        quality: str = "low",
        size: str = "1536x1024",
        max_retries: int = 3,
        output_format: str = "webp",
        recompress_quality: int = 90,
        style: str | None = None,
        max_bytes: int = 200_000,
    ):
        self.api_key = api_key
        self.model = model
        self.quality = quality
        self.size = size
        self.max_retries = max_retries
        if output_format not in FORMATS:
            raise ValueError(f"формат {output_format!r} не поддерживается: {sorted(FORMATS)}")
        self.output_format = output_format
        self.recompress_quality = recompress_quality
        self.style = STYLES.get(style, style)
        self.max_bytes = max_bytes

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
                        'output_format': self.output_format,
                    },
                    timeout=300,
                )

                if r.status_code == 200:
                    data = r.json().get('data') or []
                    if not data:
                        logger.warning("OpenAI не вернул изображений")
                        return None

                    image_bytes = base64.b64decode(data[0]['b64_json'])
                    raw_size = len(image_bytes)
                    image_bytes = self._recompress(image_bytes)
                    content_type, ext = FORMATS[self.output_format]
                    logger.info(
                        f"Изображение получено: {raw_size} байт"
                        + (f" -> {len(image_bytes)} после пережатия"
                           if len(image_bytes) != raw_size else "")
                    )
                    return {
                        'data': image_bytes,
                        'content_type': content_type,
                        'ext': ext,
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

    def _recompress(self, image_bytes: bytes) -> bytes:
        """Пережать картинку, сохранив разрешение. Не вышло — вернуть исходник.

        API отдаёт почти несжатый файл (1–2 МБ). Фактурные стили — коллаж,
        фотография — жмутся заметно хуже плоских, поэтому качество подбираем
        под потолок max_bytes, а не берём фиксированное.
        """
        if not self.recompress_quality:
            return image_bytes
        if Image is None:
            logger.warning("Pillow не установлен — картинка уйдёт без пережатия")
            return image_bytes
        try:
            im = Image.open(io.BytesIO(image_bytes))
            if self.output_format == 'webp':
                target = 'WEBP'
            elif self.output_format == 'jpeg':
                target = 'JPEG'
            else:
                target = 'PNG'
            # JPEG не умеет альфу, PNG и WebP умеют
            if target == 'JPEG' and im.mode != 'RGB':
                im = im.convert('RGB')
            elif im.mode not in ('RGB', 'RGBA'):
                im = im.convert('RGB')

            def pack(q):
                buf = io.BytesIO()
                if target == 'WEBP':
                    im.save(buf, target, quality=q, method=6)
                elif target == 'JPEG':
                    im.save(buf, target, quality=q, optimize=True)
                else:
                    im.save(buf, target, optimize=True)
                return buf.getvalue()

            packed = pack(self.recompress_quality)
            if self.max_bytes and target != 'PNG':
                for q in (82, 75, 68, 60):
                    if len(packed) <= self.max_bytes or q >= self.recompress_quality:
                        break
                    packed = pack(q)
            return packed if len(packed) < len(image_bytes) else image_bytes
        except Exception as e:
            logger.warning(f"Пережать не удалось ({e}) — картинка уйдёт как есть")
            return image_bytes

    def _create_image_prompt(self, topic: str, article_title: str = "") -> str:
        base = f"Professional, high-quality illustration related to: {topic}"
        if article_title and article_title != topic:
            base += f" - {article_title}"
        style = self.style or "modern clean digital illustration, bright appealing colours"
        return (
            f"{base}.\n\n"
            "Style requirements:\n"
            f"- {style}\n"
            "- Suitable for blog/article featured image\n"
            "- No text or letters in the image\n"
            "- Web-safe, appropriate for professional blog\n"
            "- High resolution, detailed"
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
