"""Shared session-cookie constants for authentication.

认证共享的会话 Cookie 常量。
"""

from typing import Literal

SESSION_COOKIE_NAME = "atri_session"
SESSION_COOKIE_PATH = "/"
SESSION_COOKIE_SAMESITE: Literal["lax", "strict", "none"] = "lax"
