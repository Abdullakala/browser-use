"""
Browser-Use Web UI – FastAPI backend with WebSocket streaming.

Launch with:
    python -m browser_use.ui.app
or via the CLI:
    browser-use ui
    browseruse ui
    bu ui
"""

from __future__ import annotations

import asyncio
import base64
import logging
import os
import traceback
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

load_dotenv()

logger = logging.getLogger(__name__)

# ── Lazy browser_use imports (keep startup fast) ──────────────────────────────

from browser_use.ui.views import (
	AgentConfig,
	BrowserConfig,
	HistoryResponse,
	LLMProvider,
	RunRecord,
	RunRequest,
	StatusResponse,
	StopRequest,
	WsMessage,
	WsMessageType,
)

STATIC_DIR = Path(__file__).parent / 'static'

# ── State ─────────────────────────────────────────────────────────────────────

_ws_clients: set[WebSocket] = set()
_run_history: list[RunRecord] = []
_current_run: dict[str, Any] | None = None  # {'run_id': ..., 'task': ..., 'cancel': asyncio.Event}


# ── WebSocket helpers ─────────────────────────────────────────────────────────


async def _broadcast(msg: WsMessage) -> None:
	"""Send a message to all connected WebSocket clients."""
	dead: set[WebSocket] = set()
	payload = msg.model_dump_json()
	for ws in list(_ws_clients):
		try:
			await ws.send_text(payload)
		except Exception:
			dead.add(ws)
	_ws_clients.difference_update(dead)


# ── LLM factory ──────────────────────────────────────────────────────────────


def _build_llm(cfg: AgentConfig):
	"""Instantiate the correct ChatModel from config."""
	if cfg.api_key:
		_PROVIDER_ENV = {
			LLMProvider.openai: 'OPENAI_API_KEY',
			LLMProvider.anthropic: 'ANTHROPIC_API_KEY',
			LLMProvider.google: 'GOOGLE_API_KEY',
			LLMProvider.groq: 'GROQ_API_KEY',
			LLMProvider.browser_use: 'BROWSER_USE_API_KEY',
			LLMProvider.azure_openai: 'AZURE_OPENAI_API_KEY',
			LLMProvider.mistral: 'MISTRAL_API_KEY',
		}
		env_var = _PROVIDER_ENV.get(cfg.provider)
		if env_var:
			os.environ[env_var] = cfg.api_key

	kwargs: dict[str, Any] = {'temperature': cfg.temperature}
	if cfg.model:
		kwargs['model'] = cfg.model

	if cfg.provider == LLMProvider.browser_use:
		from browser_use.llm.browser_use.chat import ChatBrowserUse

		return ChatBrowserUse(**{k: v for k, v in kwargs.items() if k != 'model'})

	elif cfg.provider == LLMProvider.openai:
		from browser_use.llm.openai.chat import ChatOpenAI

		if not kwargs.get('model'):
			kwargs['model'] = 'gpt-4.1-mini'
		return ChatOpenAI(**kwargs)

	elif cfg.provider == LLMProvider.anthropic:
		from browser_use.llm.anthropic.chat import ChatAnthropic

		if not kwargs.get('model'):
			kwargs['model'] = 'claude-sonnet-4-5'
		return ChatAnthropic(**kwargs)

	elif cfg.provider == LLMProvider.google:
		from browser_use.llm.google.chat import ChatGoogle

		if not kwargs.get('model'):
			kwargs['model'] = 'gemini-2.0-flash'
		return ChatGoogle(**kwargs)

	elif cfg.provider == LLMProvider.groq:
		from browser_use.llm.groq.chat import ChatGroq

		if not kwargs.get('model'):
			kwargs['model'] = 'llama-3.3-70b-versatile'
		return ChatGroq(**kwargs)

	elif cfg.provider == LLMProvider.ollama:
		from browser_use.llm.ollama.chat import ChatOllama

		if not kwargs.get('model'):
			kwargs['model'] = 'llama3'
		return ChatOllama(**kwargs)

	elif cfg.provider == LLMProvider.azure_openai:
		from browser_use.llm.azure.chat import ChatAzureOpenAI

		return ChatAzureOpenAI(**kwargs)

	elif cfg.provider == LLMProvider.mistral:
		from browser_use.llm.mistral.chat import ChatMistral

		if not kwargs.get('model'):
			kwargs['model'] = 'mistral-large-latest'
		return ChatMistral(**kwargs)

	raise ValueError(f'Unsupported provider: {cfg.provider}')


def _build_browser(cfg: BrowserConfig):
	from browser_use.browser import BrowserSession

	browser_kwargs: dict[str, Any] = {
		'headless': cfg.headless,
		'window_size': {'width': cfg.window_width, 'height': cfg.window_height},
		'disable_security': cfg.disable_security,
	}
	if cfg.allowed_domains:
		browser_kwargs['allowed_domains'] = cfg.allowed_domains
	if cfg.prohibited_domains:
		browser_kwargs['prohibited_domains'] = cfg.prohibited_domains
	return BrowserSession(**browser_kwargs)


# ── Agent runner ──────────────────────────────────────────────────────────────


async def _run_agent(run_id: str, task: str, cfg: AgentConfig, cancel_event: asyncio.Event) -> None:
	"""Run the agent and stream updates via WebSocket."""
	global _current_run, _run_history

	# Find the record to update
	record = next((r for r in _run_history if r.run_id == run_id), None)
	if record is None:
		return

	await _broadcast(
		WsMessage(
			type=WsMessageType.status,
			run_id=run_id,
			data={'status': 'running', 'task': task, 'steps': 0},
		)
	)

	try:
		from browser_use.agent.service import Agent

		llm = _build_llm(cfg)
		browser = _build_browser(cfg.browser)

		agent_kwargs: dict[str, Any] = {
			'task': task,
			'llm': llm,
			'browser': browser,
			'use_vision': cfg.use_vision,
			'max_actions_per_step': cfg.max_actions_per_step,
			'use_thinking': cfg.use_thinking,
			'flash_mode': cfg.flash_mode,
		}
		if cfg.extend_system_message:
			agent_kwargs['extend_system_message'] = cfg.extend_system_message

		agent = Agent(**agent_kwargs)

		step_count = 0

		async def on_step_end(agent_instance) -> None:
			nonlocal step_count
			step_count += 1
			record.steps = step_count

			model_output = agent_instance.state.last_model_output
			actions_json: list[dict[str, Any]] = []
			if model_output:
				try:
					actions_json = [a.model_dump() for a in (model_output.action or [])]
				except Exception:
					pass

			# Screenshot
			screenshot_b64: str | None = None
			try:
				page = await browser.get_current_page()
				raw = await page.screenshot(type='jpeg', quality=70)
				screenshot_b64 = base64.b64encode(raw).decode()
			except Exception:
				pass

			step_data: dict[str, Any] = {
				'step': step_count,
				'actions': actions_json,
				'url': agent_instance.state.last_browser_state.url if agent_instance.state.last_browser_state else None,
			}

			await _broadcast(WsMessage(type=WsMessageType.step, run_id=run_id, data=step_data))

			if screenshot_b64:
				await _broadcast(
					WsMessage(
						type=WsMessageType.screenshot,
						run_id=run_id,
						data={'step': step_count, 'image': screenshot_b64},
					)
				)

			await _broadcast(
				WsMessage(
					type=WsMessageType.status,
					run_id=run_id,
					data={'status': 'running', 'task': task, 'steps': step_count},
				)
			)

		# Run the agent in a task so we can cancel it
		agent_task = asyncio.create_task(
			agent.run(
				max_steps=cfg.max_steps,
				on_step_end=on_step_end,
			)
		)

		# Wait for either the agent or a cancel signal
		cancel_task = asyncio.create_task(cancel_event.wait())
		done, pending = await asyncio.wait(
			{agent_task, cancel_task},
			return_when=asyncio.FIRST_COMPLETED,
		)

		for t in pending:
			t.cancel()

		if cancel_event.is_set():
			agent_task.cancel()
			record.status = 'stopped'
			await _broadcast(
				WsMessage(
					type=WsMessageType.done,
					run_id=run_id,
					data={'status': 'stopped', 'steps': step_count, 'result': None},
				)
			)
		else:
			history = agent_task.result()
			final = history.final_result() if history else None
			errors = [e for e in (history.errors() if history else []) if e]
			record.status = 'done'
			record.final_result = final
			record.errors = [str(e) for e in errors]
			await _broadcast(
				WsMessage(
					type=WsMessageType.done,
					run_id=run_id,
					data={
						'status': 'done',
						'steps': step_count,
						'result': final,
						'errors': record.errors,
					},
				)
			)

		try:
			await browser.kill()
		except Exception:
			pass

	except Exception as exc:
		tb = traceback.format_exc()
		logger.error('Agent run %s failed: %s', run_id, tb)
		if record:
			record.status = 'error'
			record.errors = [str(exc)]
		await _broadcast(
			WsMessage(
				type=WsMessageType.error,
				run_id=run_id,
				data={'error': str(exc), 'traceback': tb},
			)
		)
	finally:
		if record:
			record.finished_at = datetime.now(timezone.utc).isoformat()
		_current_run = None


# ── FastAPI app ───────────────────────────────────────────────────────────────


@asynccontextmanager
async def _lifespan(app: FastAPI):
	yield


app = FastAPI(title='Browser-Use Agent UI', version='1.0.0', lifespan=_lifespan)

# Serve static files
app.mount('/static', StaticFiles(directory=str(STATIC_DIR)), name='static')


@app.get('/', response_class=FileResponse)
async def index():
	return FileResponse(str(STATIC_DIR / 'index.html'))


# ── REST endpoints ────────────────────────────────────────────────────────────


@app.post('/api/run')
async def api_run(req: RunRequest):
	global _current_run

	if _current_run is not None:
		return JSONResponse(status_code=409, content={'error': 'An agent is already running. Stop it first.'})

	run_id = str(uuid.uuid4())
	cancel_event = asyncio.Event()

	record = RunRecord(
		run_id=run_id,
		task=req.task,
		started_at=datetime.now(timezone.utc).isoformat(),
		config=req.config,
	)
	_run_history.insert(0, record)

	_current_run = {'run_id': run_id, 'task': req.task, 'cancel': cancel_event}
	asyncio.create_task(_run_agent(run_id, req.task, req.config, cancel_event))

	return {'run_id': run_id, 'status': 'started'}


@app.post('/api/stop')
async def api_stop(req: StopRequest):
	global _current_run
	if _current_run is None or _current_run.get('run_id') != req.run_id:
		return JSONResponse(status_code=404, content={'error': 'No matching run found.'})
	_current_run['cancel'].set()
	return {'status': 'stop_requested'}


@app.get('/api/status')
async def api_status() -> StatusResponse:
	if _current_run:
		record = next((r for r in _run_history if r.run_id == _current_run['run_id']), None)
		return StatusResponse(
			running=True,
			run_id=_current_run['run_id'],
			steps=record.steps if record else 0,
			task=_current_run['task'],
		)
	return StatusResponse(running=False)


@app.get('/api/history')
async def api_history() -> HistoryResponse:
	return HistoryResponse(runs=_run_history[:50])


@app.delete('/api/history')
async def api_clear_history():
	_run_history.clear()
	return {'status': 'cleared'}


# ── WebSocket ─────────────────────────────────────────────────────────────────


@app.websocket('/ws')
async def websocket_endpoint(ws: WebSocket):
	await ws.accept()
	_ws_clients.add(ws)
	try:
		# Send current status immediately on connect
		status_msg: dict[str, Any]
		if _current_run:
			record = next((r for r in _run_history if r.run_id == _current_run['run_id']), None)
			status_msg = {
				'status': 'running',
				'run_id': _current_run['run_id'],
				'task': _current_run['task'],
				'steps': record.steps if record else 0,
			}
		else:
			status_msg = {'status': 'idle'}
		await ws.send_text(WsMessage(type=WsMessageType.status, run_id='', data=status_msg).model_dump_json())

		# Keep alive – just receive pings
		while True:
			await ws.receive_text()
	except WebSocketDisconnect:
		pass
	except Exception:
		pass
	finally:
		_ws_clients.discard(ws)


# ── Entry point ───────────────────────────────────────────────────────────────


def main(host: str = '0.0.0.0', port: int = 7788, reload: bool = False) -> None:
	"""Launch the Browser-Use web UI."""
	import uvicorn

	print(f'\n🚀  Browser-Use Agent UI → http://localhost:{port}\n')
	uvicorn.run(
		'browser_use.ui.app:app',
		host=host,
		port=port,
		reload=reload,
		log_level='warning',
	)


if __name__ == '__main__':
	main()
