"""LLM call layer -- interfaces, factory, and built-in provider registrations.

Importing this package triggers the side-effect registration of all built-in
providers (via :mod:`src.llm.providers`), so downstream code can call
:func:`create_from_role` or :meth:`LLMFactory.create` without manually
importing provider modules.
"""

from __future__ import annotations

from src.llm.exceptions import (
    LLMAPIError,
    LLMConnectionError,
    LLMError,
    LLMRateLimitError,
)
from src.llm.factory import LLMFactory, create_from_role
from src.llm.interface import LLMInterface
from src.llm.providers import openai_compatible as _openai_compatible  # noqa: F401

__all__ = [
    "LLMAPIError",
    "LLMConnectionError",
    "LLMError",
    "LLMFactory",
    "LLMInterface",
    "LLMRateLimitError",
    "create_from_role",
]
