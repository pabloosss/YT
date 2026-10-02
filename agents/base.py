from __future__ import annotations

from abc import ABC, abstractmethod
from core.openai_gateway import OpenAIGateway


class BaseAgent(ABC):
    name = "Agent"

    def __init__(self, ai: OpenAIGateway):
        self.ai = ai

    @abstractmethod
    def run(self, **kwargs):
        raise NotImplementedError
