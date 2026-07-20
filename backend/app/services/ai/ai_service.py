from app.services.ai.provider import AIProvider


class AIService:
    def __init__(self, provider: AIProvider) -> None:
        self.provider = provider

    def generate_tests(self, prompt: str) -> str:
        return self.provider.generate(prompt)
