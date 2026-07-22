from abc import ABC, abstractmethod


class AIProviderUnavailableError(RuntimeError):
    """Raised when every configured provider model is temporarily unavailable."""


class AIProvider(ABC):
    @abstractmethod
    def generate(self, prompt: str) -> str:
        pass
