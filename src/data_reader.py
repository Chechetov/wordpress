"""
Модуль для чтения входных данных из CSV/Excel файлов
"""

import pandas as pd
import logging
from typing import List, Dict, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class ArticleDataReader:
    """Класс для чтения данных о статьях из CSV/Excel файлов"""
    
    REQUIRED_COLUMNS = ['Рубрика', 'Тема статьи', 'Анкор', 'Ссылка']
    
    def __init__(self, file_path: str):
        """
        Инициализация читателя данных
        
        Args:
            file_path: Путь к файлу с данными (CSV или Excel)
        """
        self.file_path = Path(file_path)
        if not self.file_path.exists():
            raise FileNotFoundError(f"Файл не найден: {file_path}")
    
    def read_data(self) -> List[Dict[str, str]]:
        """
        Чтение данных из файла
        
        Returns:
            Список словарей с данными о статьях
        """
        try:
            # Определяем тип файла по расширению
            if self.file_path.suffix.lower() in ['.xlsx', '.xls']:
                df = pd.read_excel(self.file_path)
            elif self.file_path.suffix.lower() == '.csv':
                # Сначала пробуем точку с запятой (стандарт для Excel в русской локали)
                try:
                    df = pd.read_csv(self.file_path, sep=';')
                except:
                    try:
                        df = pd.read_csv(self.file_path)
                    except:
                        # Если все еще не работает, пробуем определить разделитель автоматически
                        with open(self.file_path, 'r', encoding='utf-8') as f:
                            first_line = f.readline()
                            if ';' in first_line:
                                df = pd.read_csv(self.file_path, sep=';')
                            elif ',' in first_line:
                                df = pd.read_csv(self.file_path, sep=',')
                            else:
                                raise ValueError("Не удалось определить разделитель в CSV файле")
            else:
                raise ValueError(f"Неподдерживаемый формат файла: {self.file_path.suffix}")
            
            # Проверяем наличие необходимых столбцов (игнорируя пустые столбцы)
            df_columns = [col.strip() for col in df.columns if col.strip()]
            missing_columns = set(self.REQUIRED_COLUMNS) - set(df_columns)
            if missing_columns:
                raise ValueError(f"Отсутствуют необходимые столбцы: {', '.join(missing_columns)}")
            
            # Переименовываем столбцы если нужно (убираем лишние пробелы)
            df.columns = [col.strip() for col in df.columns]
            
            # Удаляем пустые столбцы
            df = df.loc[:, df.columns.str.strip() != '']
            
            # Удаляем только строки с пустой рубрикой или темой (остальные поля могут быть пустыми)
            df = df.dropna(subset=['Рубрика', 'Тема статьи'])
            
            # Конвертируем DataFrame в список словарей
            articles = []
            for _, row in df.iterrows():
                # Пропускаем пустые строки
                if pd.isna(row.get('Рубрика')) or str(row['Рубрика']).strip() == '':
                    continue
                    
                topic = str(row['Тема статьи']).strip()
                # Пропускаем если тема статьи пустая или содержит только "nan"
                if not topic or topic == 'nan' or topic == '':
                    continue
                    
                article_data = {
                    'category': str(row['Рубрика']).strip(),
                    'topic': topic,
                    'anchor': str(row['Анкор']).strip(),
                    'url': str(row['Ссылка']).strip()
                }
                
                # Очищаем пустые значения
                if article_data['anchor'] == 'nan':
                    article_data['anchor'] = ''
                if article_data['url'] == 'nan':
                    article_data['url'] = ''
                    
                articles.append(article_data)
            
            logger.info(f"Загружено {len(articles)} статей из файла: {self.file_path}")
            return articles
            
        except Exception as e:
            logger.error(f"Ошибка при чтении файла {self.file_path}: {str(e)}")
            raise
    
    def validate_data(self, articles: List[Dict[str, str]]) -> bool:
        """
        Валидация данных о статьях
        
        Args:
            articles: Список статей для проверки
            
        Returns:
            True если все данные корректны
        """
        valid_articles = []
        
        for i, article in enumerate(articles):
            # Проверяем обязательные поля
            if not article['category']:
                logger.error(f"Строка {i+1}: Отсутствует рубрика")
                continue
            
            if not article['topic']:
                logger.error(f"Строка {i+1}: Отсутствует тема статьи")
                continue
            
            # Проверяем анкор и ссылку (только для статей со ссылками)
            has_link = bool(article['anchor'] and article['url'])
            
            if has_link:
                # Если анкор есть, но URL отсутствует или некорректный
                if not article['url']:
                    logger.warning(f"Строка {i+1}: Есть анкор, но нет URL ссылки")
                    continue
                
                # Проверяем формат URL
                if not article['url'].startswith(('http://', 'https://')):
                    logger.error(f"Строка {i+1}: Некорректный формат URL: {article['url']}")
                    continue
            
            # Статья валидна
            valid_articles.append(article)
            logger.info(f"Строка {i+1}: Статья валидна ({'со ссылкой' if has_link else 'без ссылки'})")
        
        if not valid_articles:
            logger.error("Нет валидных статей для обработки")
            return False
        
        logger.info(f"Валидация пройдена. Доступно {len(valid_articles)} из {len(articles)} статей")
        return True