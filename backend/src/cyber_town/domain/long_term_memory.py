"""Validated, provider-neutral structured long-term memory values."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from enum import StrEnum
from uuid import UUID

_MAX_IDENTIFIER_LENGTH = 64
_APPROVED_FACT_KEYS = frozenset(
    {"game_alias", "preferred_language", "reply_style", "favorite_cyber_town_topic"}
)
_GAME_ALIAS = re.compile(r"[A-Za-z0-9_-]{1,32}")
_SAFE_TOPIC = re.compile(r"[A-Za-z0-9\u4e00-\u9fff]+(?:[ -][A-Za-z0-9\u4e00-\u9fff]+)*")
_APPROVED_TOPIC_WORDS = frozenset(
    {
        "alley",
        "alleys",
        "arcade",
        "art",
        "cafe",
        "cafes",
        "city",
        "culture",
        "cyber",
        "district",
        "districts",
        "drone",
        "drones",
        "festival",
        "festivals",
        "food",
        "game",
        "games",
        "garden",
        "gardens",
        "light",
        "lights",
        "market",
        "markets",
        "music",
        "neon",
        "night",
        "quiet",
        "rain",
        "rainy",
        "robot",
        "robots",
        "rooftop",
        "rooftops",
        "shop",
        "shops",
        "skyline",
        "station",
        "stories",
        "story",
        "street",
        "streets",
        "technology",
        "town",
        "train",
        "tram",
        "walk",
        "walks",
    }
)
_APPROVED_CHINESE_TOPIC = re.compile(
    r"(?:霓虹|夜市|夜晚|散步|街道|街区|美食|电车|小镇|城市|赛博|灯光|音乐|"
    r"游戏|咖啡|艺术|文化|机器人|无人机|屋顶|花园|雨夜|市集|故事|夜景)+"
)
_UNSAFE_TOPIC = re.compile(
    r"(?:https?://|www\.|@|\d{7,}|"
    r"\b(?:system|developer|assistant|tool|password|secret|token|credential|"
    r"phone|email|address|identity|account|instruction|ignore|override|"
    r"reveal|execute|prompt|forget|obey|commands?|rules?|delete|erase|"
    r"clear|disclose|publish|prior)\b|"
    r"密码|密钥|令牌|手机|电话|邮箱|住址|地址|身份证|银行卡|账户|账号|"
    r"指令|忽略|覆盖|执行|调用|提示词|系统|开发者|助手|工具|"
    r"忘记|清空|规则|公开|角色设定|命令|服从|删除|清除)",
    re.IGNORECASE,
)


def validate_long_term_fact(fact_key: str, fact_value: str | None) -> None:
    """Validate one frozen, low-sensitivity structured fact without retaining it."""

    if not isinstance(fact_key, str) or fact_key not in _APPROVED_FACT_KEYS:
        raise ValueError("Long-term memory fact key is not approved")
    if not isinstance(fact_value, str):
        raise TypeError("Long-term memory fact body must be a string")
    if not fact_value or fact_value != fact_value.strip():
        raise ValueError("Long-term memory fact body is invalid")

    if fact_key == "game_alias" and _GAME_ALIAS.fullmatch(fact_value) is None:
        raise ValueError("Game alias is outside the approved format")
    if fact_key == "preferred_language" and fact_value not in {"zh-CN", "en-US"}:
        raise ValueError("Preferred language is not approved")
    if fact_key == "reply_style" and fact_value not in {"concise", "balanced"}:
        raise ValueError("Reply style is not approved")
    if fact_key == "favorite_cyber_town_topic":
        normalized = unicodedata.normalize("NFKC", fact_value)
        if (
            len(fact_value) > 64
            or any(not character.isprintable() for character in fact_value)
            or _SAFE_TOPIC.fullmatch(normalized) is None
            or _UNSAFE_TOPIC.search(normalized) is not None
        ):
            raise ValueError("Cyber Town topic is outside the approved content boundary")
        topic_parts = re.split(r"[ -]+", normalized.casefold())
        if any(
            part not in _APPROVED_TOPIC_WORDS and _APPROVED_CHINESE_TOPIC.fullmatch(part) is None
            for part in topic_parts
        ):
            raise ValueError("Cyber Town topic is outside the approved content boundary")


class MemoryType(StrEnum):
    """The approved classes of explicitly persisted game facts."""

    PROFILE = "profile"
    PREFERENCE = "preference"


class MemoryStatus(StrEnum):
    """The explicit lifecycle of a persisted structured fact."""

    ACTIVE = "active"
    SUPERSEDED = "superseded"
    FORGOTTEN = "forgotten"
    EXPIRED = "expired"


@dataclass(frozen=True, slots=True)
class LongTermMemoryScope:
    """The complete player/NPC ownership boundary of a long-term fact."""

    player_id: str
    npc_id: str

    def __post_init__(self) -> None:
        for name, value in (("player_id", self.player_id), ("npc_id", self.npc_id)):
            if not isinstance(value, str):
                raise TypeError(f"Long-term memory {name} must be a string")
            if not value or value != value.strip() or len(value) > _MAX_IDENTIFIER_LENGTH:
                raise ValueError(f"Long-term memory {name} is invalid")


@dataclass(frozen=True, slots=True)
class LongTermMemoryRecord:
    """One immutable, narrowly validated fact or bodyless lifecycle tombstone."""

    memory_id: UUID
    scope: LongTermMemoryScope
    memory_type: MemoryType
    fact_key: str
    fact_value: str | None = field(repr=False)
    source_conversation_id: UUID
    source_request_id: UUID
    source_trace_id: UUID
    importance: int
    confidence: int
    created_at: int
    updated_at: int
    expires_at: int | None
    version: int
    status: MemoryStatus

    def __post_init__(self) -> None:
        self._validate_identity()
        self._validate_numeric_fields()
        self._validate_fact_value()

    def _validate_identity(self) -> None:
        if not isinstance(self.scope, LongTermMemoryScope):
            raise TypeError("Long-term memory requires a validated player/NPC scope")

        for name, value in (
            ("memory_id", self.memory_id),
            ("source_conversation_id", self.source_conversation_id),
            ("source_request_id", self.source_request_id),
            ("source_trace_id", self.source_trace_id),
        ):
            if not isinstance(value, UUID):
                raise TypeError(f"Long-term memory {name} must be a validated UUID")

        if not isinstance(self.memory_type, MemoryType):
            raise TypeError("Long-term memory type must be an approved enum")
        if not isinstance(self.status, MemoryStatus):
            raise TypeError("Long-term memory status must be an approved enum")
        if not isinstance(self.fact_key, str) or self.fact_key not in _APPROVED_FACT_KEYS:
            raise ValueError("Long-term memory fact key is not approved")

    def _validate_numeric_fields(self) -> None:
        bounded_values = (
            ("importance", self.importance, 1, 5),
            ("confidence", self.confidence, 0, 1_000),
            ("version", self.version, 1, None),
            ("created_at", self.created_at, 1, None),
            ("updated_at", self.updated_at, 1, None),
        )
        for name, value, minimum, maximum in bounded_values:
            if type(value) is not int:
                raise TypeError(f"Long-term memory {name} must be an integer")
            if value < minimum or (maximum is not None and value > maximum):
                raise ValueError(f"Long-term memory {name} is outside its approved range")

        if self.updated_at < self.created_at:
            raise ValueError("Long-term memory update must not precede creation")

        if self.expires_at is not None:
            if type(self.expires_at) is not int:
                raise TypeError("Long-term memory expiration must be an integer")
            if self.expires_at <= self.created_at:
                raise ValueError("Long-term memory expiration must follow creation")

    def _validate_fact_value(self) -> None:
        if self.status in (MemoryStatus.FORGOTTEN, MemoryStatus.EXPIRED):
            if self.fact_value is not None:
                raise ValueError("Inactive long-term memory must not retain a fact body")
            return

        validate_long_term_fact(self.fact_key, self.fact_value)
