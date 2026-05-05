"""Pydantic models for the Browser-Use web UI API."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class LLMProvider(str, Enum):
	browser_use = 'browser_use'
	openai = 'openai'
	anthropic = 'anthropic'
	google = 'google'
	groq = 'groq'
	ollama = 'ollama'
	azure_openai = 'azure_openai'
	mistral = 'mistral'


class BrowserConfig(BaseModel):
	model_config = ConfigDict(extra='forbid')

	headless: bool = True
	window_width: int = 1280
	window_height: int = 720
	allowed_domains: list[str] = Field(default_factory=list)
	prohibited_domains: list[str] = Field(default_factory=list)
	disable_security: bool = False


class AgentConfig(BaseModel):
	model_config = ConfigDict(extra='forbid')

	# LLM settings
	provider: LLMProvider = LLMProvider.browser_use
	model: str = ''
	api_key: str = ''
	temperature: float = Field(default=0.0, ge=0.0, le=2.0)

	# Agent behaviour
	max_steps: int = Field(default=50, ge=1, le=500)
	max_actions_per_step: int = Field(default=5, ge=1, le=20)
	use_vision: bool | Literal['auto'] = 'auto'
	use_thinking: bool = True
	flash_mode: bool = False
	extend_system_message: str = ''

	# Browser
	browser: BrowserConfig = Field(default_factory=BrowserConfig)


class RunRequest(BaseModel):
	model_config = ConfigDict(extra='forbid')

	task: str
	config: AgentConfig = Field(default_factory=AgentConfig)


class StopRequest(BaseModel):
	model_config = ConfigDict(extra='forbid')

	run_id: str


# ── WebSocket message types ──────────────────────────────────────────────────


class WsMessageType(str, Enum):
	step = 'step'
	action = 'action'
	screenshot = 'screenshot'
	log = 'log'
	done = 'done'
	error = 'error'
	status = 'status'


class WsMessage(BaseModel):
	"""Message sent to all connected WebSocket clients."""

	model_config = ConfigDict(extra='forbid')

	type: WsMessageType
	run_id: str
	data: dict[str, Any]


# ── History ──────────────────────────────────────────────────────────────────


class RunRecord(BaseModel):
	model_config = ConfigDict(extra='forbid')

	run_id: str
	task: str
	started_at: str
	finished_at: str | None = None
	status: Literal['running', 'done', 'error', 'stopped'] = 'running'
	steps: int = 0
	final_result: str | None = None
	errors: list[str] = Field(default_factory=list)
	config: AgentConfig


class HistoryResponse(BaseModel):
	model_config = ConfigDict(extra='forbid')

	runs: list[RunRecord]


class StatusResponse(BaseModel):
	model_config = ConfigDict(extra='forbid')

	running: bool
	run_id: str | None = None
	steps: int = 0
	task: str | None = None
