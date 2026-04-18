"""LLMFactory -- decorator-based registry for pluggable providers.

Providers register themselves at import time via
``@LLMFactory.register("<name>")``. The factory code itself never changes
when a new provider is added; only the provider file + a yaml entry.

Reference: docs/LLM调用层设计讨论.md §2.1, §2.3
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from src.llm.interface import LLMInterface


class LLMFactory:
    """Class-scoped registry mapping provider name -> provider class."""

    _registry: dict[str, type[LLMInterface]] = {}

    @classmethod
    def register(cls, name: str) -> Callable[[type[LLMInterface]], type[LLMInterface]]:
        """Return a decorator that binds ``name`` to the decorated class."""

        def wrapper(llm_class: type[LLMInterface]) -> type[LLMInterface]:
            cls._registry[name] = llm_class
            return llm_class

        return wrapper

    @classmethod
    def create(cls, name: str, **kwargs: Any) -> LLMInterface:
        """Instantiate a registered provider by ``name``."""
        if name not in cls._registry:
            available = sorted(cls._registry.keys())
            raise ValueError(f"Unknown LLM provider: {name!r}. Available: {available}")
        return cls._registry[name](**kwargs)

    @classmethod
    def available(cls) -> list[str]:
        """Return the sorted list of currently registered provider names."""
        return sorted(cls._registry.keys())


def create_from_role(role: str, llm_config: dict[str, Any]) -> LLMInterface:
    """Create an LLM instance by resolving a role name through the config.

    Looks up ``llm_config['llm_roles'][role]`` to get a pool key, then
    fetches ``llm_config['llm_configs'][pool_key]`` to get the provider
    parameters, and finally calls :meth:`LLMFactory.create`.

    Args:
        role: Call-site name -- one of ``"chat" | "l3_compress" | "l4_compact"``
            (or any key defined in ``llm_roles``).
        llm_config: The ``llm`` section from the merged config (contains
            ``llm_configs`` and ``llm_roles``).

    Returns:
        A ready-to-use :class:`LLMInterface` instance.

    Raises:
        KeyError: Role not in ``llm_roles`` or referenced pool key not in
            ``llm_configs``.
        ValueError: Pool entry's ``provider`` field is not registered.

        通过 config 解析角色名称来创建 LLM 实例。

    查找``llm_config['llm_roles'][role]``以获取池密钥，然后
    获取 ``llm_config['llm_configs'][pool_key]`` 以获取提供程序
    参数，最后调用 LLMFactory.create`。

    参数：
        角色：调用站点名称——``“聊天” | 之一“l3_压缩”| “l4_compact”``
        （或“llm_roles”中定义的任何键）。
        llm_config：合并配置中的 llm 部分（包含“llm_configs”和“llm_roles”）。

    返回：
        一个随时可用的 LLMInterface 实例。

    加薪：
        KeyError：角色不在“llm_roles”中或引用的池密钥不在
            ``llm_configs``。
        ValueError：池条目的“provider”字段未注册。
    """
    roles = llm_config.get("llm_roles", {})
    if role not in roles:
        raise KeyError(f"Role {role!r} not found in llm_roles. Available: {sorted(roles)}")

    pool_key = roles[role]
    pool = llm_config.get("llm_configs", {})
    if pool_key not in pool:
        raise KeyError(
            f"Role {role!r} references pool key {pool_key!r}, "
            f"but it is missing from llm_configs. Available: {sorted(pool)}"
        )

    entry = dict(pool[pool_key])
    provider = entry.pop("provider", None)
    if provider is None:
        raise KeyError(f"Pool entry {pool_key!r} is missing required 'provider' field")

    return LLMFactory.create(provider, **entry)
