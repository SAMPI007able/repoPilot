from abc import ABC, abstractmethod
from collections.abc import Iterator


class AIProviderUnavailableError(RuntimeError):
    """Raised when every configured provider model is temporarily unavailable."""


class AIProvider(ABC):
    @abstractmethod
    def generate(self, prompt: str) -> str:
        pass

    def stream(self, prompt: str) -> Iterator[str]:
        """Stream generated text, with a buffered fallback for simple providers."""
        yield self.generate(prompt)
