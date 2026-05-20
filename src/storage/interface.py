"""Abstract interface for chat storage.

Defines the contract for chat persistence implementations (JSON, database, etc.).

聊天存储的抽象接口，定义了聊天持久化实现（JSON、数据库等）的契约。
"""

from abc import ABC, abstractmethod


class ChatStorageInterface(ABC):
    """Abstract interface for chat storage operations.

    聊天存储操作的抽象接口。
    """

    @abstractmethod
    async def create_chat(self, user_id: str, character_id: str, title: str) -> dict:
        """
        Create a new chat session.

        创建新的聊天会话。

        Args:
            user_id: User identifier / 用户标识符
            character_id: Character identifier / 角色标识符
            title: Chat title (LLM-generated or fallback) / 聊天标题（LLM 生成或回退）

        Returns:
            Chat metadata dict with keys: id, title, character_id,
            created_at, updated_at, message_count
            聊天元数据字典，包含键：id, title, character_id, created_at, updated_at, message_count
        """
        ...

    @abstractmethod
    async def list_chats(self, user_id: str, character_id: str | None = None) -> list[dict]:
        """
        List user's chat sessions, sorted by updated_at descending.

        列出用户的聊天会话，按 updated_at 降序排列。

        Args:
            user_id: User identifier / 用户标识符
            character_id: Optional filter by character / 可选的角色过滤条件

        Returns:
            List of chat metadata dicts / 聊天元数据字典列表
        """
        ...

    @abstractmethod
    async def get_chat(self, chat_id: str) -> dict | None:
        """
        Get chat metadata by ID.

        根据 ID 获取聊天元数据。

        Args:
            chat_id: Chat identifier / 聊天标识符

        Returns:
            Chat metadata dict or None if not found
            聊天元数据字典，未找到时返回 None
        """
        ...

    @abstractmethod
    async def get_chat_for_user(self, user_id: str, chat_id: str) -> dict | None:
        """
        Get chat metadata by ID, scoped to a user.

        根据 ID 获取聊天元数据，限定到特定用户。

        Args:
            user_id: User identifier / 用户标识符
            chat_id: Chat identifier / 聊天标识符

        Returns:
            Chat metadata dict or None if not found for this user
            聊天元数据字典，该用户下未找到时返回 None
        """
        ...

    @abstractmethod
    async def get_chat_for_user_character(
        self, user_id: str, character_id: str, chat_id: str
    ) -> dict | None:
        """
        Get chat metadata by ID, scoped to a user and character.

        根据 ID 获取聊天元数据，限定到特定用户和角色。

        Args:
            user_id: User identifier / 用户标识符
            character_id: Character identifier / 角色标识符
            chat_id: Chat identifier / 聊天标识符

        Returns:
            Chat metadata dict or None if not found for this user/character
            聊天元数据字典，该用户/角色下未找到时返回 None
        """
        ...

    @abstractmethod
    async def update_chat(self, chat_id: str, **kwargs: str) -> dict:
        """
        Update chat metadata (e.g., title).

        更新聊天元数据（如标题）。

        Args:
            chat_id: Chat identifier / 聊天标识符
            **kwargs: Fields to update (e.g., title="New Title") / 要更新的字段

        Returns:
            Updated chat metadata dict / 更新后的聊天元数据字典

        Raises:
            ValueError: If chat_id not found / 聊天 ID 不存在时抛出
        """
        ...

    @abstractmethod
    async def update_chat_for_user(self, user_id: str, chat_id: str, **kwargs: str) -> dict:
        """
        Update chat metadata for a specific user.

        更新特定用户的聊天元数据。

        Args:
            user_id: User identifier / 用户标识符
            chat_id: Chat identifier / 聊天标识符
            **kwargs: Fields to update / 要更新的字段

        Returns:
            Updated chat metadata dict / 更新后的聊天元数据字典

        Raises:
            ValueError: If chat_id not found for this user / 该用户下聊天 ID 不存在时抛出
        """
        ...

    @abstractmethod
    async def delete_chat(self, chat_id: str) -> None:
        """
        Delete a chat session and its messages.

        删除聊天会话及其消息。

        Args:
            chat_id: Chat identifier / 聊天标识符

        Raises:
            ValueError: If chat_id not found / 聊天 ID 不存在时抛出
        """
        ...

    @abstractmethod
    async def delete_chat_for_user(self, user_id: str, chat_id: str) -> None:
        """
        Delete a chat session for a specific user.

        删除特定用户的聊天会话。

        Args:
            user_id: User identifier / 用户标识符
            chat_id: Chat identifier / 聊天标识符

        Raises:
            ValueError: If chat_id not found for this user / 该用户下聊天 ID 不存在时抛出
        """
        ...

    @abstractmethod
    async def append_message(
        self, chat_id: str, role: str, content: str, name: str | None = None
    ) -> dict:
        """
        Append a message to chat history.

        向聊天历史追加消息。

        Args:
            chat_id: Chat identifier / 聊天标识符
            role: Message role (human/ai/system) / 消息角色（human/ai/system）
            content: Message content / 消息内容
            name: Optional speaker name / 可选的发言者名称

        Returns:
            Message dict with keys: role, content, name, timestamp
            消息字典，包含键：role, content, name, timestamp

        Raises:
            ValueError: If chat_id not found / 聊天 ID 不存在时抛出
        """
        ...

    @abstractmethod
    async def append_message_for_user(
        self, user_id: str, chat_id: str, role: str, content: str, name: str | None = None
    ) -> dict:
        """
        Append a message to a user-scoped chat history.

        向用户范围的聊天历史追加消息。

        Args:
            user_id: User identifier / 用户标识符
            chat_id: Chat identifier / 聊天标识符
            role: Message role / 消息角色
            content: Message content / 消息内容
            name: Optional speaker name / 可选的发言者名称

        Returns:
            Message dict / 消息字典

        Raises:
            ValueError: If chat_id not found for this user / 该用户下聊天 ID 不存在时抛出
        """
        ...

    @abstractmethod
    async def get_messages(self, chat_id: str, limit: int = 50, offset: int = 0) -> list[dict]:
        """
        Get chat message history with pagination.

        分页获取聊天消息历史。

        Args:
            chat_id: Chat identifier / 聊天标识符
            limit: Maximum messages to return / 返回的最大消息数
            offset: Number of messages to skip / 跳过的消息数

        Returns:
            List of message dicts / 消息字典列表

        Raises:
            ValueError: If chat_id not found / 聊天 ID 不存在时抛出
        """
        ...

    @abstractmethod
    async def get_messages_for_user(
        self, user_id: str, chat_id: str, limit: int | None = 50, offset: int = 0
    ) -> list[dict]:
        """
        Get user-scoped chat message history with pagination.

        分页获取用户范围的聊天消息历史。

        Args:
            user_id: User identifier / 用户标识符
            chat_id: Chat identifier / 聊天标识符
            limit: Maximum messages to return / 返回的最大消息数
            offset: Number of messages to skip / 跳过的消息数

        Returns:
            List of message dicts / 消息字典列表

        Raises:
            ValueError: If chat_id not found for this user / 该用户下聊天 ID 不存在时抛出
        """
        ...
