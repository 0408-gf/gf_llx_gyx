from __future__ import annotations

from typing import Protocol

SERVICE = "FootballJCAssistant"
_MEMORY: dict[str, str] = {}


class KeyringLike(Protocol):
    def get_password(self, service: str, username: str) -> str | None: ...
    def set_password(self, service: str, username: str, password: str) -> None: ...
    def delete_password(self, service: str, username: str) -> None: ...


class CredentialStore:
    """密钥只进入系统凭据库；不可用时仅保存在当前进程内存。"""

    def __init__(self, backend: KeyringLike | None = None) -> None:
        if backend is None:
            try:
                import keyring
                backend = keyring
            except ImportError:
                backend = None
        self.backend = backend
        self.memory_only = backend is None

    def get(self, provider: str) -> str | None:
        if self.backend is not None:
            try:
                return self.backend.get_password(SERVICE, provider) or _MEMORY.get(provider)
            except Exception:
                self.memory_only = True
        return _MEMORY.get(provider)

    def set(self, provider: str, secret: str) -> bool:
        secret = secret.strip()
        if not secret:
            raise ValueError("API Key 不能为空。")
        if self.backend is not None:
            try:
                self.backend.set_password(SERVICE, provider, secret)
                _MEMORY.pop(provider, None)
                return True
            except Exception:
                self.memory_only = True
        _MEMORY[provider] = secret
        return False

    def delete(self, provider: str) -> None:
        _MEMORY.pop(provider, None)
        if self.backend is not None:
            try:
                self.backend.delete_password(SERVICE, provider)
            except Exception:
                self.memory_only = True

