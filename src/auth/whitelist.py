"""GitHub username whitelist checks.

GitHub 用户名白名单检查。
"""

from __future__ import annotations


class Whitelist:
    """Case-insensitive GitHub username whitelist.

    不区分大小写的 GitHub 用户名白名单。
    """

    def __init__(self, users: list[str] | None = None) -> None:
        self._users = {user.casefold() for user in users or [] if user.strip()}

    @property
    def users(self) -> list[str]:
        return sorted(self._users)

    def is_allowed(self, username: str) -> bool:
        return username.casefold() in self._users

