from __future__ import annotations

from abc import ABC, abstractmethod
import os


class LLMBase(ABC):
    @abstractmethod
    def generate(self, prompt: str, **kwargs: object) -> str:
        raise NotImplementedError

    @abstractmethod
    def is_available(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def runtime_name(self) -> str:
        raise NotImplementedError


class CloudLLMRuntime(LLMBase):
    def __init__(self, name: str, cloud_enabled: bool = False, api_key_env: str = "") -> None:
        self.name = name
        self.cloud_enabled = cloud_enabled
        self.api_key_env = api_key_env
        self.reason = "not probed"

    def runtime_name(self) -> str:
        return self.name

    def is_available(self) -> bool:
        if not self.cloud_enabled:
            self.reason = f"{self.name} cloud LLM policy-gated"
            return False
        if not self.api_key_env or not os.getenv(self.api_key_env):
            self.reason = f"{self.name} API key env var missing: {self.api_key_env}"
            return False
        self.reason = f"{self.name} cloud runtime structurally available; calls deferred"
        return True

    def generate(self, prompt: str, **kwargs: object) -> str:
        raise RuntimeError(f"{self.name} cloud LLM policy-gated or provider calls deferred")