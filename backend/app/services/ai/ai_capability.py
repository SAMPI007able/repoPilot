from abc import ABC, abstractmethod


class AICapability(ABC):
    @abstractmethod
    def execute(self, *args, **kwargs) -> tuple[str, str]:
        raise NotImplementedError
