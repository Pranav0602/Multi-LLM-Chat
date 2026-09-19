"""SQLAlchemy models — plan section 3 (Database Schema)."""
from __future__ import annotations

import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


class Group(Base):
    __tablename__ = "groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )

    group_models: Mapped[list["GroupModel"]] = relationship(
        "GroupModel", back_populates="group", cascade="all, delete-orphan"
    )
    conversations: Mapped[list["Conversation"]] = relationship(
        "Conversation", back_populates="group", cascade="all, delete-orphan"
    )


class LLMModel(Base):
    """Table `models` in the plan. Class renamed to avoid clash with `models` package."""

    __tablename__ = "models"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model_name: Mapped[str] = mapped_column(String(255), nullable=False)
    system_prompt: Mapped[str] = mapped_column(Text, default="", nullable=False)
    temperature: Mapped[float] = mapped_column(default=0.7)
    max_output_tokens: Mapped[int] = mapped_column(Integer, default=1024)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Per-model credentials (user-supplied via UI). Empty = fall back to .env global key.
    api_key: Mapped[str] = mapped_column(Text, default="", nullable=False)
    base_url: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )

    group_links: Mapped[list["GroupModel"]] = relationship("GroupModel", back_populates="model")
    turns: Mapped[list["Turn"]] = relationship("Turn", back_populates="model")


class GroupModel(Base):
    __tablename__ = "group_models"
    __table_args__ = (UniqueConstraint("group_id", "model_id", name="uq_group_model"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"), index=True)
    model_id: Mapped[int] = mapped_column(ForeignKey("models.id", ondelete="CASCADE"), index=True)
    turn_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    system_prompt_override: Mapped[str] = mapped_column(Text, default="", nullable=False)

    group: Mapped[Group] = relationship("Group", back_populates="group_models")
    model: Mapped[LLMModel] = relationship("LLMModel", back_populates="group_links")


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    original_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    current_round: Mapped[int] = mapped_column(Integer, default=1)
    current_turn: Mapped[int] = mapped_column(Integer, default=0)
    # active | paused | completed | error
    status: Mapped[str] = mapped_column(String(32), default="active")
    max_rounds: Mapped[int] = mapped_column(Integer, default=5)
    # Chat mode: research | debate | architecture | brainstorm | custom
    chat_type: Mapped[str] = mapped_column(String(64), default="research", nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )

    group: Mapped[Group] = relationship("Group", back_populates="conversations")
    turns: Mapped[list["Turn"]] = relationship(
        "Turn", back_populates="conversation", cascade="all, delete-orphan", order_by="Turn.turn_number"
    )
    summaries: Mapped[list["ContextSummary"]] = relationship(
        "ContextSummary",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="ContextSummary.id",
    )


class Turn(Base):
    __tablename__ = "turns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    model_id: Mapped[int | None] = mapped_column(ForeignKey("models.id", ondelete="SET NULL"))
    round_number: Mapped[int] = mapped_column(Integer, nullable=False)
    turn_number: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    # Exact payload sent to the model (JSON string) — critical for debugging.
    input_context: Mapped[str] = mapped_column(Text, default="", nullable=False)
    response: Mapped[str] = mapped_column(Text, default="", nullable=False)

    # Error handling (plan section 16): failed turns are stored, conversation continues.
    status: Mapped[str] = mapped_column(String(32), default="ok")  # ok | error
    error_message: Mapped[str] = mapped_column(Text, default="", nullable=False)

    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=_now)

    conversation: Mapped[Conversation] = relationship("Conversation", back_populates="turns")
    model: Mapped[LLMModel | None] = relationship("LLMModel", back_populates="turns")


class ContextSummary(Base):
    __tablename__ = "context_summaries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    up_to_turn_id: Mapped[int] = mapped_column(Integer, nullable=False)
    up_to_turn_number: Mapped[int] = mapped_column(Integer, default=0)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=_now)

    conversation: Mapped[Conversation] = relationship("Conversation", back_populates="summaries")
