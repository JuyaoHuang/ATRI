"""Authentication exception hierarchy.

认证异常层次结构。
"""


class AuthError(Exception):
    """Base authentication error.

    认证错误基类。
    """


class AuthConfigError(AuthError):
    """Authentication configuration is missing or invalid.

    认证配置缺失或无效。
    """


class AuthUnauthorizedError(AuthError):
    """Request is not authenticated or the user is not allowed.

    请求未认证或用户不在允许列表中。
    """


class AuthTokenError(AuthUnauthorizedError):
    """JWT token is missing, invalid, or expired.

    JWT 令牌缺失、无效或已过期。
    """

