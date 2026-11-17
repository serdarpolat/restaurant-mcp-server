"""Agents under test. Each takes a user prompt and a ToolSession and returns a Trajectory."""

import asyncio
import json
import re
import time
from typing import Protocol

import httpx

from evals.harness import ToolSession
from evals.scoring import ToolCall, Trajectory
from pos_mcp.server import INSTRUCTIONS

# What every run tells the model about the eval itself (not about the restaurant).
EVAL_PROTOCOL = """You assist the restaurant staff.
The user cannot reply during this task. If a required detail is missing, do not guess:
end with a question asking for it.
"""

# Default: the server's instructions reach the model, as in clients that pass MCP
# `instructions` on. With --no-instructions the model sees only the tool descriptions and
# tool results, as in clients that drop them: the server must then carry every rule.
SYSTEM_PROMPT = INSTRUCTIONS + "\n" + EVAL_PROTOCOL + "Answer in the user's language.\n"
BARE_SYSTEM_PROMPT = EVAL_PROTOCOL


def system_prompt(server_instructions: bool = True) -> str:
    return SYSTEM_PROMPT if server_instructions else BARE_SYSTEM_PROMPT


class Agent(Protocol):
    name: str

    async def run(self, prompt: str, session: ToolSession) -> Trajectory: ...


class AnthropicAgent:
    """Plain tool-use loop on the Anthropic Messages API (no framework)."""

    def __init__(
        self, model: str, max_steps: int = 10, max_tokens: int = 2048, system: str = SYSTEM_PROMPT
    ):
        try:
            import anthropic
        except ImportError as exc:
            raise SystemExit(
                'The eval needs extra packages: uv sync --extra eval  (or pip install -e ".[eval]")'
            ) from exc
        self.name = model
        self.model = model
        self.max_steps = max_steps
        self.max_tokens = max_tokens
        self.system = system
        self.client = anthropic.AsyncAnthropic(max_retries=6)

    async def run(self, prompt: str, session: ToolSession) -> Trajectory:
        traj = Trajectory()
        started = time.perf_counter()
        tools = [dict(t) for t in session.tools]
        tools[-1]["cache_control"] = {"type": "ephemeral"}  # tool list is identical every turn
        messages: list[dict] = [{"role": "user", "content": prompt}]
        try:
            for _ in range(self.max_steps):
                response = await self.client.messages.create(
                    model=self.model,
                    max_tokens=self.max_tokens,
                    system=self.system,
                    tools=tools,
                    messages=messages,
                )
                usage = response.usage
                traj.input_tokens += (
                    usage.input_tokens
                    + (usage.cache_read_input_tokens or 0)
                    + (usage.cache_creation_input_tokens or 0)
                )
                traj.output_tokens += usage.output_tokens
                messages.append({"role": "assistant", "content": response.content})

                uses = [b for b in response.content if b.type == "tool_use"]
                if not uses:
                    traj.final_text = "".join(b.text for b in response.content if b.type == "text")
                    break
                results = []
                for block in uses:
                    call = await session.call(block.name, dict(block.input))
                    results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": call.result,
                            "is_error": call.is_error,
                        }
                    )
                messages.append({"role": "user", "content": results})
            else:
                traj.error = f"no final answer after {self.max_steps} steps"
        except Exception as exc:  # noqa: BLE001 - one failing case must not stop the run
            traj.error = f"{type(exc).__name__}: {exc}"
        traj.calls = list(session.calls)
        traj.approvals_asked = list(session.approvals_asked)
        traj.seconds = round(time.perf_counter() - started, 2)
        return traj


# --------------------------------------------------------------------------- #
# OpenAI-compatible chat completions: LM Studio, Ollama, Gemini, Groq, OpenRouter...
# --------------------------------------------------------------------------- #

PROVIDERS = {
    # name: (base_url, env var holding the API key or None)
    "lmstudio": ("http://localhost:1234/v1", None),
    "ollama": ("http://localhost:11434/v1", None),
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai", "GEMINI_API_KEY"),
    "groq": ("https://api.groq.com/openai/v1", "GROQ_API_KEY"),
    "openrouter": ("https://openrouter.ai/api/v1", "OPENROUTER_API_KEY"),
}

_THINK = re.compile(r"<think>.*?</think>", re.DOTALL)


def visible_text(text: str | None) -> str:
    """Drop <think>...</think> blocks some local reasoning models put in the answer."""
    text = _THINK.sub("", text or "")
    if "</think>" in text:  # opening tag was in the prompt template
        text = text.split("</think>", 1)[1]
    return text.strip()


class OpenAICompatibleAgent:
    """Plain tool-calling loop on any OpenAI-compatible /chat/completions endpoint."""

    def __init__(
        self,
        model: str,
        base_url: str,
        api_key: str | None = None,
        max_steps: int = 10,
        max_tokens: int = 4096,
        timeout: float = 600,
        transport: httpx.AsyncBaseTransport | None = None,
        system: str = SYSTEM_PROMPT,
    ):
        self.name = model
        self.system = system
        self.model = model
        self.max_steps = max_steps
        self.max_tokens = max_tokens
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self.http = httpx.AsyncClient(
            base_url=base_url.rstrip("/") + "/",
            headers=headers,
            timeout=timeout,
            transport=transport,
        )

    async def list_models(self) -> list[str]:
        response = await self.http.get("models")
        response.raise_for_status()
        return [m["id"] for m in response.json()["data"]]

    async def _complete(self, messages: list[dict], tools: list[dict]) -> dict:
        body = {
            "model": self.model,
            "messages": messages,
            "tools": tools,
            "tool_choice": "auto",
            "max_tokens": self.max_tokens,
        }
        for attempt in range(5):
            response = await self.http.post("chat/completions", json=body)
            if response.status_code == 429 and attempt < 4:  # free tiers rate-limit hard
                await asyncio.sleep(float(response.headers.get("retry-after", 10 * (attempt + 1))))
                continue
            if response.is_error:
                raise RuntimeError(f"HTTP {response.status_code}: {response.text[:500]}")
            return response.json()
        raise RuntimeError("rate limited")

    async def run(self, prompt: str, session: ToolSession) -> Trajectory:
        traj = Trajectory()
        started = time.perf_counter()
        tools = [
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t["description"],
                    "parameters": t["input_schema"],
                },
            }
            for t in session.tools
        ]
        messages: list[dict] = [
            {"role": "system", "content": self.system},
            {"role": "user", "content": prompt},
        ]
        try:
            for _ in range(self.max_steps):
                data = await self._complete(messages, tools)
                usage = data.get("usage") or {}
                traj.input_tokens += usage.get("prompt_tokens") or 0
                traj.output_tokens += usage.get("completion_tokens") or 0
                message = data["choices"][0]["message"]
                tool_calls = message.get("tool_calls") or []
                messages.append(
                    {
                        "role": "assistant",
                        "content": message.get("content") or "",
                        **({"tool_calls": tool_calls} if tool_calls else {}),
                    }
                )
                if not tool_calls:
                    traj.final_text = visible_text(message.get("content"))
                    break
                for tc in tool_calls:
                    name = tc["function"]["name"]
                    raw = tc["function"].get("arguments") or "{}"
                    try:
                        args = json.loads(raw) if isinstance(raw, str) else dict(raw)
                    except json.JSONDecodeError:
                        call = ToolCall(
                            name, {}, is_error=True, result=f"Invalid JSON: {raw[:200]}"
                        )
                        session.calls.append(call)
                    else:
                        call = await session.call(name, args)
                    messages.append(
                        {"role": "tool", "tool_call_id": tc.get("id", ""), "content": call.result}
                    )
            else:
                traj.error = f"no final answer after {self.max_steps} steps"
        except Exception as exc:  # noqa: BLE001 - one failing case must not stop the run
            traj.error = f"{type(exc).__name__}: {exc}"
        traj.calls = list(session.calls)
        traj.approvals_asked = list(session.approvals_asked)
        traj.seconds = round(time.perf_counter() - started, 2)
        return traj
