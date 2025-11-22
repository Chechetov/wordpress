# PBN Manager

Система автоматического управления сетью WordPress сайтов (PBN - Private Blog Network).

## Возможности

### Управление сетью
- 📊 Централизованный реестр сайтов с шифрованием credentials
- 🎭 Fingerprint Randomizer - уникальный профиль для каждого сайта
- 🔄 Автоматическая установка WordPress через SSH

### Генерация контента
- 📝 AI-генерация статей через GPT-4 с вариативностью стилей
- 🖼️ Создание изображений через DALL-E
- 🎨 6+ стилей написания (формальный, дружелюбный, аналитический и др.)
- 📐 5+ структур статей (классическая, listicle, how-to и др.)

### Защита от обнаружения
- 🎭 Разные темы WordPress для каждого сайта
- 🔌 Вариативные наборы плагинов
- ⏰ Рандомизация расписания публикаций
- ✍️ Разные стили контента

## Быстрый старт

### 1. Установка

```bash
# Клонируйте репозиторий
git clone <repository-url>
cd wordpress

# Создайте виртуальное окружение
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows

# Установите зависимости
pip install -r requirements.txt
```

### 2. Конфигурация

```bash
# Скопируйте пример конфигурации
cp .env.example .env

# Сгенерируйте ключ шифрования
python pbn.py generate-key

# Отредактируйте .env, добавьте:
# - OPENAI_API_KEY
# - ENCRYPTION_KEY (из предыдущей команды)
```

### 3. Инициализация

```bash
python pbn.py init
```

## Использование

### CLI команды

```bash
# Помощь
python pbn.py --help

# Статистика по сети
python pbn.py stats

# Добавить сайт в реестр
python pbn.py site-add example.com \
    --wp-user admin \
    --wp-password "xxxx xxxx xxxx xxxx" \
    --generate-fingerprint

# Список сайтов
python pbn.py site-list
python pbn.py site-list --status active

# Информация о сайте
python pbn.py site-info --domain example.com

# Установить WordPress на новый сервер
python pbn.py site-provision example.com \
    --ssh-user root \
    --ssh-key ~/.ssh/id_rsa \
    --add-to-registry

# Сгенерировать fingerprint
python pbn.py fingerprint example.com --json
```

### Генерация контента (legacy)

```bash
# Публикация статей из CSV (старый способ)
python main.py articles.csv

# С отложенной публикацией
python main.py articles.csv --schedule
```

## Архитектура

```
wordpress/
├── pbn_manager/              # Новая система PBN Manager
│   ├── core/                 # Ядро системы
│   │   ├── models.py         # SQLAlchemy модели
│   │   ├── site_registry.py  # Управление сайтами
│   │   ├── encryption.py     # Шифрование credentials
│   │   └── fingerprint.py    # Генерация уникальных профилей
│   ├── content/              # Генерация контента
│   │   ├── generator.py      # AI-генератор с вариативностью
│   │   └── variations.py     # Стили и структуры
│   ├── wordpress/            # WordPress операции
│   │   └── provisioner.py    # Автоустановка WP через SSH
│   ├── cli/                  # CLI интерфейс
│   │   └── commands.py       # Команды
│   ├── api/                  # API для дашборда (в разработке)
│   └── dashboard/            # Web-интерфейс (в разработке)
├── src/                      # Legacy модули
│   ├── content_generator.py  # Старый генератор
│   ├── wordpress_publisher.py
│   ├── image_generator.py
│   └── data_reader.py
├── config/
│   └── settings.py           # Настройки
├── data/                     # База данных и данные
├── pbn.py                    # Entry point CLI
├── main.py                   # Legacy entry point
└── requirements.txt
```

## Модели данных

### Site (Сайт)
- Домен, URL, credentials (зашифрованы)
- SSH доступ для провизии
- Fingerprint профиль
- Статистика публикаций

### Post (Пост)
- Связь с сайтом
- Метаданные контента
- Ссылки (anchor, URL)
- Статус публикации

### ContentQueue (Очередь)
- Задания на генерацию
- Приоритеты и расписание

### LinkStrategy (Стратегия ссылок)
- Целевые URL
- Распределение анкоров
- Лимиты ссылок

## Fingerprint система

Каждый сайт получает уникальный профиль:

```python
{
    "theme": "flavor",         # Случайная тема
    "plugins": ["flavor", "flavor"],  # Набор плагинов
    "content_style": "formal_expert", # Стиль контента
    "permalink_structure": "/%postname%/",
    "timezone": "Europe/Moscow",
    "post_frequency_days": 2.5,       # Частота публикаций
    "post_time_range": [9, 18],       # Часы публикации
    ...
}
```

## Стили контента

| Стиль | Описание |
|-------|----------|
| formal_expert | Серьёзный экспертный стиль |
| casual_friendly | Дружелюбный разговорный |
| practical_guide | Пошаговые инструкции |
| storyteller | Нарративный с историями |
| analytical | Глубокий анализ с данными |
| news_reporter | Новостной стиль |

## Безопасность

- Все пароли шифруются Fernet (AES-128-CBC)
- Credentials хранятся в зашифрованном виде в БД
- Ключ шифрования отдельно в .env

## Roadmap

- [x] Site Registry с шифрованием
- [x] WordPress Provisioner (SSH)
- [x] Fingerprint Randomizer
- [x] Content Variations
- [x] CLI интерфейс
- [ ] Web Dashboard (FastAPI + React)
- [ ] Celery workers для фоновых задач
- [ ] Link Strategy Manager
- [ ] Мониторинг и алерты
- [ ] API для внешних интеграций

## Лицензия

MIT License
