#!/usr/bin/env python3
"""
PBN Manager - главный entry point
Запуск: python pbn.py <команда>
"""

import sys
from pathlib import Path

# Добавляем корень проекта в путь
sys.path.insert(0, str(Path(__file__).parent))

from pbn_manager.cli.commands import main

if __name__ == "__main__":
    sys.exit(main())
