from abc import ABC, abstractmethod
from collections.abc import Iterator


class AIProviderUnavailableError(RuntimeError):
    """Raised when every configured provider model is temporarily unavailable."""


class AIProviderQuotaError(AIProviderUnavailableError):
    """Raised when the upstream provider asks callers to wait for quota capacity."""

    def __init__(
        self,
        model: str,
        retry_after_seconds: int,
        provider: str = "AI provider",
    ) -> None:
        self.model = model
        self.provider = provider
        self.retry_after_seconds = max(1, retry_after_seconds)
        super().__init__(
            f"{provider} quota is temporarily exhausted for {model}. "
            f"Try again in {self.retry_after_seconds} seconds."
        )


class AIProviderPromptTooLargeError(ValueError):
    """Raised before generation when a prompt exceeds its configured token budget."""

    def __init__(self, input_tokens: int, max_input_tokens: int) -> None:
        self.input_tokens = input_tokens
        self.max_input_tokens = max_input_tokens
        super().__init__(
            f"AI prompt contains {input_tokens} input tokens; the configured limit is "
            f"{max_input_tokens}. Narrow the question or reduce repository context."
        )


class AIProvider(ABC):
    @abstractmethod
    def generate(self, prompt: str) -> str:
        pass

    def stream(self, prompt: str) -> Iterator[str]:
        """Stream generated text, with a buffered fallback for simple providers."""
        yield self.generate(prompt)
