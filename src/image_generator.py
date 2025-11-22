"""
Модуль для генерации изображений через DALL-E API
"""

import openai
import logging
import requests
import time
from typing import Optional, Dict
from pathlib import Path
import io
import base64

logger = logging.getLogger(__name__)


class ImageGenerator:
    """Класс для генерации изображений через DALL-E API"""
    
    def __init__(self, api_key: str, model: str = "dall-e-3"):
        """
        Инициализация генератора изображений
        
        Args:
            api_key: OpenAI API ключ
            model: Модель для генерации (dall-e-2, dall-e-3)
        """
        self.client = openai.OpenAI(api_key=api_key)
        self.model = model
        self.size = "1024x1024" if model == "dall-e-3" else "512x512"
        
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
            # Создаем промпт для генерации изображения
            prompt = self._create_image_prompt(topic, article_title)
            
            logger.info(f"Генерация изображения для темы: {topic}")
            
            # Генерируем изображение через DALL-E
            response = self.client.images.generate(
                model=self.model,
                prompt=prompt,
                n=1,
                size=self.size,
                quality="standard" if self.model == "dall-e-3" else None
            )
            
            image_url = response.data[0].url
            revised_prompt = response.data[0].revised_prompt if hasattr(response.data[0], 'revised_prompt') else prompt
            
            logger.info(f"Изображение успешно сгенерировано: {image_url}")
            
            # Скачиваем изображение
            image_data = self._download_image(image_url)
            
            if image_data:
                return {
                    'url': image_url,
                    'data': image_data,
                    'prompt': prompt,
                    'revised_prompt': revised_prompt,
                    'size': self.size
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Ошибка при генерации изображения для темы '{topic}': {str(e)}")
            return None
    
    def _create_image_prompt(self, topic: str, article_title: str) -> str:
        """
        Создание промпта для генерации изображения
        
        Args:
            topic: Тема статьи
            article_title: Заголовок статьи
            
        Returns:
            Промпт для DALL-E
        """
        
        # Создаем описательный промпт на основе темы и заголовка
        base_prompt = f"Professional, high-quality illustration related to: {topic}"
        
        if article_title and article_title != topic:
            base_prompt += f" - {article_title}"
        
        # Добавляем стилистические инструкции
        prompt = f"""
{base_prompt}.

Style requirements:
- Modern, clean, professional design
- Bright, appealing colors
- Suitable for blog/article featured image
- No text or letters in the image
- Web-safe, appropriate for professional blog
- High resolution, detailed
- Digital illustration style
"""

        return prompt.strip()
    
    def _download_image(self, image_url: str) -> Optional[bytes]:
        """
        Скачивание изображения по URL
        
        Args:
            image_url: URL изображения
            
        Returns:
            Данные изображения в байтах или None в случае ошибки
        """
        try:
            logger.info(f"Скачивание изображения: {image_url}")
            
            response = requests.get(image_url, timeout=30)
            response.raise_for_status()
            
            logger.info(f"Изображение успешно скачано. Размер: {len(response.content)} байт")
            
            return response.content
            
        except Exception as e:
            logger.error(f"Ошибка при скачивании изображения: {str(e)}")
            return None
    
    def save_image_locally(self, image_data: bytes, filename: str, save_dir: str = "images") -> Optional[str]:
        """
        Сохранение изображения в локальный файл
        
        Args:
            image_data: Данные изображения
            filename: Имя файла
            save_dir: Директория для сохранения
            
        Returns:
            Путь к сохраненному файлу или None в случае ошибки
        """
        try:
            # Создаем директорию если она не существует
            save_path = Path(save_dir)
            save_path.mkdir(exist_ok=True)
            
            # Добавляем расширение если его нет
            if not filename.lower().endswith(('.png', '.jpg', '.jpeg')):
                filename += '.png'
            
            file_path = save_path / filename
            
            # Сохраняем изображение
            with open(file_path, 'wb') as f:
                f.write(image_data)
            
            logger.info(f"Изображение сохранено: {file_path}")
            return str(file_path)
            
        except Exception as e:
            logger.error(f"Ошибка при сохранении изображения: {str(e)}")
            return None
    
    def generate_multiple_variants(
        self, 
        topic: str, 
        article_title: str, 
        num_variants: int = 1
    ) -> list:
        """
        Генерация нескольких вариантов изображений
        
        Args:
            topic: Тема статьи
            article_title: Заголовок статьи
            num_variants: Количество вариантов
            
        Returns:
            Список словарей с информацией об изображениях
        """
        images = []
        
        for i in range(num_variants):
            try:
                logger.info(f"Генерация варианта изображения #{i+1}")
                
                image_info = self.generate_featured_image(topic, article_title)
                
                if image_info:
                    images.append(image_info)
                
                # Небольшая задержка между запросами
                if i < num_variants - 1:
                    time.sleep(1)
                    
            except Exception as e:
                logger.error(f"Ошибка при генерации варианта #{i+1}: {str(e)}")
                continue
        
        logger.info(f"Сгенерировано {len(images)} из {num_variants} изображений")
        return images
    
    def get_image_info(self, image_data: bytes) -> Dict[str, str]:
        """
        Получение информации об изображении
        
        Args:
            image_data: Данные изображения
            
        Returns:
            Словарь с информацией об изображении
        """
        try:
            from PIL import Image
            import io
            
            # Открываем изображение
            img = Image.open(io.BytesIO(image_data))
            
            return {
                'format': img.format,
                'size': f"{img.width}x{img.height}",
                'mode': img.mode,
                'file_size': len(image_data)
            }
            
        except Exception as e:
            logger.warning(f"Не удалось получить информацию об изображении: {str(e)}")
            return {
                'format': 'unknown',
                'size': 'unknown',
                'mode': 'unknown',
                'file_size': len(image_data)
            }