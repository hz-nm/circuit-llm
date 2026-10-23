"""Provider adapters: one small HTTP client per LLM API, behind the :class:`Provider` protocol."""

from .anthropic import AnthropicProvider
from .base import Completion, ErrorKind, Message, Provider, ProviderError, Role, Usage
from .capabilities import reset_capability_cache
from .factory import ProviderFactory, create_provider, test_endpoint
from .gemini import GeminiProvider
from .openai_compat import OpenAICompatibleProvider, OpenRouterProvider

__all__ = [
    "AnthropicProvider",
    "Completion",
    "ErrorKind",
    "GeminiProvider",
    "Message",
    "OpenAICompatibleProvider",
    "OpenRouterProvider",
    "Provider",
    "ProviderError",
    "ProviderFactory",
    "Role",
    "Usage",
    "create_provider",
    "reset_capability_cache",
    "test_endpoint",
]
