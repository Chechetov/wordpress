"""
Основной скрипт для автоматизации создания и публикации статей в WordPress
"""

import os
import logging
import time
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

from src.data_reader import ArticleDataReader
from src.content_generator import ContentGenerator
from src.openai_image_generator import OpenAIImageGenerator
from src.wordpress_publisher import WordPressPublisher

# Загружаем переменные окружения
load_dotenv()

# Настраиваем логирование
def setup_logging():
    """Настройка логирования"""
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    
    log_filename = f"wordpress_automation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    log_path = log_dir / log_filename
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_path, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    
    return logging.getLogger(__name__)

logger = setup_logging()


class WordPressAutomation:
    """Основной класс автоматизации WordPress"""
    
    def __init__(self):
        """Инициализация системы автоматизации"""
        
        # Загружаем конфигурацию
        self.config = self._load_config()
        
        # Инициализируем модули
        try:
            self.content_generator = ContentGenerator(
                api_key=self.config['openai_api_key'],
                model=self.config.get('openai_model', 'gpt-4')
            )
            
            self.image_generator = OpenAIImageGenerator(
                api_key=self.config['openai_api_key'],
                model=self.config.get('openai_image_model', 'gpt-image-2'),
                quality=self.config.get('image_quality', 'low')
            )
            
            self.wordpress_publisher = WordPressPublisher(
                site_url=self.config['wordpress_url'],
                username=self.config['wordpress_username'],
                app_password=self.config['wordpress_app_password'],
                proxies=self.config['proxies']
            )
            
            logger.info("Все модули успешно инициализированы")
            
        except Exception as e:
            logger.error(f"Ошибка при инициализации модулей: {str(e)}")
            raise
    
    def _load_config(self) -> dict:
        """Загрузка конфигурации из переменных окружения"""
        
        required_vars = [
            'WORDPRESS_URL', 'WORDPRESS_USERNAME', 'WORDPRESS_APP_PASSWORD',
            'OPENAI_API_KEY'
        ]
        
        config = {}
        missing_vars = []
        
        for var in required_vars:
            value = os.getenv(var)
            if not value:
                missing_vars.append(var)
            else:
                # Конвертируем имя переменной в ключ конфигурации
                config_key = var.lower()
                config[config_key] = value
        
        if missing_vars:
            raise ValueError(f"Отсутствуют обязательные переменные окружения: {', '.join(missing_vars)}")
        
        # Опциональные параметры
        config.update({
            'openai_model': os.getenv('OPENAI_MODEL', 'gpt-5.4'),
            'openai_image_model': os.getenv('OPENAI_IMAGE_MODEL', 'gpt-image-2'),
            'image_quality': os.getenv('IMAGE_QUALITY', 'low'),
            'target_word_count': int(os.getenv('TARGET_WORD_COUNT', '1750')),
            'delay_between_posts': int(os.getenv('DELAY_BETWEEN_POSTS', '60')),
            'publish_status': os.getenv('PUBLISH_STATUS', 'publish'),  # или 'draft'
            'generate_images': os.getenv('GENERATE_IMAGES', 'true').lower() == 'true',
            'save_locally': os.getenv('SAVE_LOCALLY', 'true').lower() == 'true',
            'schedule_mode': os.getenv('SCHEDULE_MODE', 'false').lower() == 'true',
            'schedule_interval': float(os.getenv('SCHEDULE_INTERVAL_HOURS', '52.0'))  # 52 часа по умолчанию
        })
        
        # Настройка прокси если указан
        proxies = None
        if os.getenv('PROXY_HTTP') or os.getenv('PROXY_HTTPS'):
            proxies = {}
            if os.getenv('PROXY_HTTP'):
                proxies['http'] = os.getenv('PROXY_HTTP')
            if os.getenv('PROXY_HTTPS'):
                proxies['https'] = os.getenv('PROXY_HTTPS')
            config['proxies'] = proxies
            logger.info(f"Настроен прокси: {proxies}")
        else:
            config['proxies'] = None
        
        return config
    
    def process_articles(self, input_file: str) -> list:
        """
        Обработка статей из файла
        
        Args:
            input_file: Путь к файлу с данными статей
            
        Returns:
            Список результатов обработки
        """
        
        logger.info(f"Начинаю обработку файла: {input_file}")
        
        # Читаем данные о статьях
        try:
            reader = ArticleDataReader(input_file)
            articles = reader.read_data()
            
            if not reader.validate_data(articles):
                raise ValueError("Данные не прошли валидацию")
            
            logger.info(f"Загружено {len(articles)} статей для обработки")
            
        except Exception as e:
            logger.error(f"Ошибка при чтении файла: {str(e)}")
            return []
        
        # Режим отложенной публикации
        if self.config['schedule_mode']:
            return self._schedule_and_publish(articles)
        
        # Обрабатываем каждую статью немедленно
        results = []
        
        for i, article_data in enumerate(articles, 1):
            try:
                logger.info(f"Обработка статьи {i}/{len(articles)}: {article_data['topic']}")
                
                result = self._process_single_article(article_data, i)
                results.append(result)
                
                # Задержка между публикациями
                if i < len(articles):
                    delay = self.config['delay_between_posts']
                    logger.info(f"Задержка {delay} секунд перед следующей статьей...")
                    time.sleep(delay)
                
            except Exception as e:
                logger.error(f"Ошибка при обработке статьи '{article_data['topic']}': {str(e)}")
                results.append({
                    'article_data': article_data,
                    'status': 'error',
                    'error': str(e),
                    'timestamp': datetime.now().isoformat()
                })
        
        # Сохраняем результаты
        self._save_results(results)
        
        logger.info(f"Обработка завершена. Успешно: {sum(1 for r in results if r['status'] == 'success')}/{len(results)}")
        
        return results
    
    def _schedule_and_publish(self, articles: list) -> list:
        """
        Создание статей с отложенной публикацией в WordPress
        
        Args:
            articles: Список статей
            
        Returns:
            Список результатов создания
        """
        
        logger.info("Режим отложенной публикации")
        
        # Расчет времени публикаций
        interval_hours = self.config['schedule_interval']
        start_time = datetime.now() + timedelta(hours=1)  # Первая публикация через час
        
        results = []
        
        for i, article_data in enumerate(articles, 1):
            try:
                # Рассчитываем время публикации
                publish_time = start_time + timedelta(hours=interval_hours * i)
                publish_time_iso = publish_time.isoformat()
                
                logger.info(f"Создание статьи {i}/{len(articles)} с публикацией {publish_time.strftime('%Y-%m-%d %H:%M')}")
                
                result = self._process_single_article(
                    article_data, 
                    i, 
                    scheduled_date=publish_time_iso
                )
                
                # Добавляем информацию о дате публикации
                if result and result.get('status') == 'success':
                    result['scheduled_date'] = publish_time_iso
                    result['scheduled_date_formatted'] = publish_time.strftime('%Y-%m-%d %H:%M')
                
                results.append(result)
                
                # Небольшая задержка между созданием постов
                time.sleep(2)
                
            except Exception as e:
                logger.error(f"Ошибка при создании статьи '{article_data['topic']}': {str(e)}")
                results.append({
                    'article_data': article_data,
                    'status': 'error',
                    'error': str(e),
                    'timestamp': datetime.now().isoformat()
                })
        
        # Показываем информацию о планировании
        successful_scheduled = sum(1 for r in results if r.get('status') == 'success')
        
        print(f"\nСоздано статей с отложенной публикацией: {successful_scheduled}/{len(articles)}")
        print(f"Интервал между публикациями: {interval_hours} часов")
        
        if successful_scheduled > 0:
            first_time = start_time.strftime('%Y-%m-%d %H:%M')
            last_time = (start_time + timedelta(hours=interval_hours * (len(articles) - 1))).strftime('%Y-%m-%d %H:%M')
            print(f"Первая публикация: {first_time}")
            print(f"Последняя публикация: {last_time}")
        
        print("\nWordPress автоматически опубликует статьи в указанное время.")
        print("Нет необходимости держать скрипт запущенным.")
        
        # Сохраняем результаты
        self._save_results(results)
        
        logger.info(f"Запланировано {successful_scheduled} статей")
        
        return results
    
    def _process_single_article(self, article_data: dict, article_number: int, scheduled_date: Optional[str] = None) -> dict:
        """
        Обработка одной статьи
        
        Args:
            article_data: Данные о статье
            article_number: Номер статьи
            scheduled_date: Дата публикации (для отложенной публикации)
            
        Returns:
            Результат обработки
        """
        
        start_time = datetime.now()
        
        try:
            # 1. Генерируем контент
            logger.info("Генерация контента статьи...")
            content_result = self.content_generator.generate_article_content(
                topic=article_data['topic'],
                anchor=article_data['anchor'],
                url=article_data['url'],
                target_words=self.config['target_word_count']
            )
            
            # 2. Генерируем изображение если включено
            image_data = None
            image_filename = ""
            
            if self.config['generate_images']:
                logger.info("Генерация изображения для обложки...")
                image_result = self.image_generator.generate_featured_image(
                    topic=article_data['topic'],
                    article_title=content_result['title']
                )
                
                if image_result:
                    image_data = image_result['data']
                    image_filename = f"article_{article_number}_{int(time.time())}.{image_result.get('ext', 'jpg')}"
                    
                    # Сохраняем локально если включено
                    if self.config['save_locally']:
                        local_path = self.image_generator.save_image_locally(
                            image_data, 
                            image_filename
                        )
                        if local_path:
                            logger.info(f"Изображение сохранено локально: {local_path}")
            
            # 3. Публикуем в WordPress
            logger.info("Публикация статьи в WordPress...")
            publish_result = self.wordpress_publisher.publish_article(
                title=content_result['title'],
                content=content_result['content'],
                category_name=article_data['category'],
                image_data=image_data,
                image_filename=image_filename,
                image_alt_text=f"Изображение для статьи: {content_result['title']}",
                status=self.config['publish_status'],
                scheduled_date=scheduled_date
            )
            
            end_time = datetime.now()
            processing_time = (end_time - start_time).total_seconds()
            
            if publish_result:
                status_text = "опубликована"
                if scheduled_date:
                    status_text = "запланирована"
                logger.info(f"Статья успешно {status_text}: {publish_result['url']}")
                
                return {
                    'article_data': article_data,
                    'status': 'success',
                    'post_id': publish_result['post_id'],
                    'post_url': publish_result['url'],
                    'content_title': content_result['title'],
                    'word_count': content_result['word_count'],
                    'has_image': image_data is not None,
                    'processing_time': processing_time,
                    'scheduled_date': scheduled_date,
                    'timestamp': end_time.isoformat()
                }
            else:
                raise Exception("Не удалось опубликовать статью")
                
        except Exception as e:
            end_time = datetime.now()
            processing_time = (end_time - start_time).total_seconds()
            
            logger.error(f"Ошибка при обработке статьи: {str(e)}")
            
            return {
                'article_data': article_data,
                'status': 'error',
                'error': str(e),
                'processing_time': processing_time,
                'scheduled_date': scheduled_date,
                'timestamp': end_time.isoformat()
            }
    
    def _save_results(self, results: list):
        """Сохранение результатов обработки"""
        
        reports_dir = Path("reports")
        reports_dir.mkdir(exist_ok=True)
        
        # Имя файла с отчетом
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        report_filename = f"wordpress_automation_report_{timestamp}.json"
        report_path = reports_dir / report_filename
        
        # Сохраняем детальный отчет в JSON
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        
        # Создаем краткий отчет в текстовом формате
        summary_filename = f"summary_report_{timestamp}.txt"
        summary_path = reports_dir / summary_filename
        
        with open(summary_path, 'w', encoding='utf-8') as f:
            f.write("WordPress Automation Report\n")
            f.write("=" * 50 + "\n\n")
            f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Total articles: {len(results)}\n")
            f.write(f"Successful: {sum(1 for r in results if r['status'] == 'success')}\n")
            f.write(f"Failed: {sum(1 for r in results if r['status'] == 'error')}\n\n")
            
            f.write("Results:\n")
            f.write("-" * 50 + "\n")
            
            for i, result in enumerate(results, 1):
                if result['status'] == 'success':
                    f.write(f"✓ {i}. {result['content_title']}\n")
                    f.write(f"  URL: {result['post_url']}\n")
                    f.write(f"  Category: {result['article_data']['category']}\n")
                    f.write(f"  Words: {result['word_count']}\n")
                    f.write(f"  Image: {'Yes' if result['has_image'] else 'No'}\n")
                else:
                    f.write(f"✗ {i}. {result['article_data']['topic']}\n")
                    f.write(f"  Error: {result['error']}\n")
                f.write("\n")
        
        logger.info(f"Отчеты сохранены:")
        logger.info(f"  Детальный: {report_path}")
        logger.info(f"  Краткий: {summary_path}")


def main():
    """Главная функция"""
    
    import argparse
    
    parser = argparse.ArgumentParser(description='WordPress Article Automation System')
    parser.add_argument('input_file', nargs='?', help='Путь к файлу с данными статей (CSV или Excel)')
    parser.add_argument('--dry-run', action='store_true', help='Тестовый режим без публикации')
    parser.add_argument('--config-check', action='store_true', help='Проверка конфигурации')
    parser.add_argument('--schedule', action='store_true', help='Включить режим отложенной публикации')
    
    args = parser.parse_args()
    
    try:
        # Инициализируем систему
        automation = WordPressAutomation()
        
        if args.config_check:
            print("✓ Конфигурация загружена успешно")
            print(f"  WordPress URL: {automation.config['wordpress_url']}")
            print(f"  WordPress Username: {automation.config['wordpress_username']}")
            print(f"  OpenAI Model: {automation.config['openai_model']}")
            print(f"  Image Model: {automation.config['openai_image_model']} "
                  f"({automation.config['image_quality']})")
            print(f"  Target Word Count: {automation.config['target_word_count']}")
            print(f"  Publish Status: {automation.config['publish_status']}")
            print(f"  Generate Images: {automation.config['generate_images']}")
            print(f"  Schedule Mode: {automation.config['schedule_mode']}")
            print(f"  Schedule Interval: {automation.config['schedule_interval']} часов")
            return
        
        # Проверяем наличие файла
        if not args.input_file:
            parser.print_help()
            print("\nОшибка: необходимо указать файл с данными статей")
            return 1
        
        if args.dry_run:
            print("Режим тестирования - проверяем только чтение данных...")
            reader = ArticleDataReader(args.input_file)
            articles = reader.read_data()
            reader.validate_data(articles)
            print(f"✓ Файл {args.input_file} успешно прочитан")
            print(f"✓ Найдено {len(articles)} статей")
            for i, article in enumerate(articles, 1):
                print(f"  {i}. {article['topic']} ({article['category']})")
            return
        
        # Включаем режим отложенной публикации если указан флаг
        if args.schedule:
            automation.config['schedule_mode'] = True
            print("Включен режим отложенной публикации")
        
        # Обрабатываем статьи
        results = automation.process_articles(args.input_file)
        
        # Анализируем результаты
        successful = sum(1 for r in results if r['status'] == 'success')
        scheduled = sum(1 for r in results if r.get('scheduled_date'))
        errors = sum(1 for r in results if r['status'] == 'error')
        total = len(results)
        
        print(f"\nОбработка завершена!")
        
        if scheduled > 0:
            print(f"Запланировано к публикации: {scheduled}/{total}")
            print("WordPress автоматически опубликует статьи в указанное время.")
            print("Нет необходимости держать скрипт запущенным.")
        else:
            print(f"Успешно: {successful}/{total}")
            
            if errors > 0:
                print("Ошибки:")
                for result in results:
                    if result['status'] == 'error':
                        print(f"  - {result['article_data']['topic']}: {result['error']}")
    
    except Exception as e:
        logger.error(f"Критическая ошибка: {str(e)}")
        print(f"Ошибка: {str(e)}")
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())