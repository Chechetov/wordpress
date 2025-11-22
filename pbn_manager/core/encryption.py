"""
Модуль шифрования для безопасного хранения credentials
"""

import os
import base64
import secrets
from typing import Optional
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


class CredentialEncryption:
    """Класс для шифрования/дешифрования credentials"""

    def __init__(self, encryption_key: Optional[str] = None):
        """
        Инициализация шифровальщика

        Args:
            encryption_key: Ключ шифрования (Fernet key). Если не указан, берётся из env.
        """
        self.key = encryption_key or os.getenv("ENCRYPTION_KEY")

        if not self.key:
            raise ValueError(
                "ENCRYPTION_KEY не установлен. "
                "Сгенерируйте ключ с помощью: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
            )

        self.fernet = Fernet(self.key.encode() if isinstance(self.key, str) else self.key)

    def encrypt(self, plaintext: str) -> str:
        """
        Шифрование строки

        Args:
            plaintext: Строка для шифрования

        Returns:
            Зашифрованная строка (base64)
        """
        if not plaintext:
            return ""

        encrypted = self.fernet.encrypt(plaintext.encode())
        return encrypted.decode()

    def decrypt(self, ciphertext: str) -> str:
        """
        Дешифрование строки

        Args:
            ciphertext: Зашифрованная строка

        Returns:
            Расшифрованная строка
        """
        if not ciphertext:
            return ""

        decrypted = self.fernet.decrypt(ciphertext.encode())
        return decrypted.decode()

    @staticmethod
    def generate_key() -> str:
        """Генерация нового ключа шифрования"""
        return Fernet.generate_key().decode()

    @staticmethod
    def generate_key_from_password(password: str, salt: Optional[bytes] = None) -> tuple:
        """
        Генерация ключа из пароля (для пользовательского мастер-пароля)

        Args:
            password: Пароль пользователя
            salt: Соль (если None, генерируется новая)

        Returns:
            Кортеж (ключ, соль)
        """
        if salt is None:
            salt = os.urandom(16)

        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=480000,
        )

        key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
        return key.decode(), base64.b64encode(salt).decode()


def get_encryptor() -> CredentialEncryption:
    """Получение экземпляра шифровальщика с ключом из env"""
    return CredentialEncryption()


# Утилита для CLI
if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "generate":
        print("Новый ключ шифрования:")
        print(CredentialEncryption.generate_key())
        print("\nДобавьте его в .env файл как ENCRYPTION_KEY=<ключ>")
    else:
        print("Использование:")
        print("  python encryption.py generate  - сгенерировать новый ключ")
