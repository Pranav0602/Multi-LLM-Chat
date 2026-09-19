"""Pydantic schemas for request/response validation."""
from __future__ import annotations

import datetime

from pydantic import BaseModel, Field


# ---------- Groups ----------
class GroupCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str = ""


class GroupUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


class GroupOut(BaseModel):
    id: int
    name: str
    description: str
    created_at: datetime.datetime
    updated_at: datetime.datetime

    model_config = {"from_attributes": True}


# ---------- Models ----------
class LLMModelCreate(BaseModel):
    name: str
    provider: str  # any platform name: openai | anthropic | gemini | openrouter | local | mock | codecraft | custom (groq, together, ...)
    model_name: str
    system_prompt: str = ""
    temperature: float = 0.7
    max_output_tokens: int = 1024
    is_active: bool = True
    api_key: str = ""
    base_url: str = ""


class LLMModelUpdate(BaseModel):
    name: str | None = None
    provider: str | None = None
    model_name: str | None = None
    system_prompt: str | None = None
    temperature: float | None = None
    max_output_tokens: int | None = None
    is_active: bool | None = None
    api_key: str | None = None
    base_url: str | None = None


class LLMModelOut(BaseModel):
    id: int
    name: str
    provider: str
    model_name: str
    system_prompt: str
    temperature: float
    max_output_tokens: int
    is_active: bool
    api_key: str = ""
    base_url: str = ""

    model_config = {"from_attributes": True}


# ---------- GroupModels ----------
class GroupModelAdd(BaseModel):
    model_id: int
    turn_order: int = 0
    is_enabled: bool = True
    system_prompt_override: str = ""


class GroupModelUpdate(BaseModel):
    turn_order: int | None = None
    is_enabled: bool | None = None
    system_prompt_override: str | None = None


class GroupModelOut(BaseModel):
    id: int
    group_id: int
    model_id: int
    turn_order: int
    is_enabled: bool
    system_prompt_override: str
    model: LLMModelOut | None = None

    model_config = {"from_attributes": True}


class GroupModelsReorderRequest(BaseModel):
    ordered_link_ids: list[int]


class TestConnectionRequest(BaseModel):
    provider: str = ""
    model_name: str = ""
    api_key: str = ""
    base_url: str = ""
    temperature: float = 0.7
    max_output_tokens: int = 5


class TestConnectionOut(BaseModel):
    ok: bool
    latency_ms: float | None = None
    error_code: str | None = None
    message: str


# ---------- Conversations ----------
class ConversationCreate(BaseModel):
    group_id: int
    title: str = ""
    original_prompt: str = Field(min_length=1)
    max_rounds: int = 5
    chat_type: str = "research"


class ConversationOut(BaseModel):
    id: int
    group_id: int
    title: str
    original_prompt: str
    summary: str
    current_round: int
    current_turn: int
    status: str
    max_rounds: int
    chat_type: str = "research"

    model_config = {"from_attributes": True}


class ConversationControl(BaseModel):
    max_rounds: int | None = None


# ---------- Turns ----------
class TurnOut(BaseModel):
    id: int
    conversation_id: int
    model_id: int | None
    round_number: int
    turn_number: int
    input_context: str
    response: str
    status: str
    error_message: str
    input_tokens: int
    output_tokens: int
    created_at: datetime.datetime
    model_name: str | None = None
    provider: str | None = None
    role_name: str | None = None

    model_config = {"from_attributes": True}


class SummaryOut(BaseModel):
    id: int
    conversation_id: int
    up_to_turn_id: int
    up_to_turn_number: int
    summary: str
    created_at: datetime.datetime

    model_config = {"from_attributes": True}
