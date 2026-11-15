"""Agents under test. Each takes a user prompt and a ToolSession and returns a Trajectory."""

import time
from typing import Protocol

from evals.harness import ToolSession
from evals.scoring import Trajectory
from pos_mcp.server import INSTRUCTIONS

SYSTEM_PROMPT = (
    INSTRUCTIONS
    + """
You assist the restaurant staff. Answer in the user's language.
The user cannot reply during this task. If a required detail is missing, do not guess:
end with a question asking for it.
"""
)


class Agent(Protocol):
    name: str

    async def run(self, prompt: str, session: ToolSession) -> Trajectory: ...


class AnthropicAgent:
    """Plain tool-use loop on the Anthropic Messages API (no framework)."""

    def __init__(self, model: str, max_steps: int = 10, max_tokens: int = 2048):
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
                    system=SYSTEM_PROMPT,
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
