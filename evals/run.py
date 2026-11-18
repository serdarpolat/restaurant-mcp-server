"""Run the Turkish tool-calling eval.

    uv sync --extra eval

    # Local model in LM Studio (start its server first), no key needed:
    uv run python -m evals.run --provider lmstudio --list-models
    uv run python -m evals.run --provider lmstudio --model mistralai/magistral-small-2509
    # Without the server's MCP instructions (clients that drop them):
    uv run python -m evals.run --provider lmstudio --model ... --no-instructions

    # Hosted (keys in .env): ANTHROPIC_API_KEY, GEMINI_API_KEY, GROQ_API_KEY, OPENROUTER_API_KEY
    uv run python -m evals.run --provider anthropic --model claude-sonnet-5-5
    uv run python -m evals.run --provider gemini --model <model id> --only ask-spice-adana

Writes evals/results/<model>.json (every call, for debugging) and <model>.md (summary).
"""

import argparse
import asyncio
import json
import logging
import os
import shutil
import sys
import tempfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
import yaml
from sqlmodel import Session

from evals.agent import PROVIDERS, Agent, AnthropicAgent, OpenAICompatibleAgent, system_prompt
from evals.harness import tool_session
from evals.scoring import CaseResult, score
from evals.world import Resolver, build_world, sqlite_engine

EVALS_DIR = Path(__file__).parent
CASES_FILE = EVALS_DIR / "cases.yaml"
CATEGORY_ORDER = ["report", "inventory", "menu", "write", "ask", "approval", "english"]

# Errors that will fail every case the same way: stop instead of burning through the list.
FATAL_ERRORS = {
    "credit balance is too low": "The API account has no credits. Add some under Plans & "
    "Billing in the Anthropic Console, then run again.",
    "AuthenticationError": "Authentication failed. Check ANTHROPIC_API_KEY in .env.",
    "PermissionDeniedError": "This API key may not use this model.",
    "NotFoundError": "Unknown model id. Check --model.",
    "HTTP 401": "The API key was rejected. Check the key in .env.",
    "HTTP 404": "Unknown model or endpoint. Check --model (try --list-models).",
    "ConnectError": "Cannot reach the model server. In LM Studio: Developer tab > Start Server.",
    "context length": "The model's context window is too small for 20 tools. Reload it in "
    "LM Studio with a context length of at least 16384.",
    "n_keep": "The model's context window is too small for 20 tools. Reload it in LM Studio "
    "with a context length of at least 16384.",
}


def load_cases(path: Path = CASES_FILE) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def select_cases(cases: list[dict], only: str | None, category: str | None) -> list[dict]:
    if only:
        wanted = {c.strip() for c in only.split(",")}
        unknown = wanted - {c["id"] for c in cases}
        if unknown:
            raise SystemExit(f"Unknown case id(s): {', '.join(sorted(unknown))}")
        cases = [c for c in cases if c["id"] in wanted]
    if category:
        cases = [c for c in cases if c["category"] == category]
    return cases


async def run_cases(
    agent: Agent,
    spec: dict[str, Any],
    cases: list[dict],
    workdir: Path,
    days: int = 30,
    repeat: int = 1,
) -> list[CaseResult]:
    template = workdir / "world.db"
    print(f"Building the eval restaurant ({days} days of history)...", file=sys.stderr)
    build_world(template, spec.get("world", {}), days=days)

    engine = sqlite_engine(template)
    results: list[CaseResult] = []
    try:
        with Session(engine) as session:
            resolver = Resolver(session)  # expected ids come from the untouched world
            for run in range(1, repeat + 1):
                prefix = f"run {run}/{repeat} " if repeat > 1 else ""
                for n, case in enumerate(cases, start=1):
                    db = workdir / f"case-{n}.db"
                    shutil.copy(template, db)
                    async with tool_session(db) as tools:
                        traj = await agent.run(case["prompt"], tools)
                    result = score(case, traj, resolver)
                    result.run = run
                    results.append(result)
                    mark = "PASS" if result.passed else "FAIL"
                    calls = " > ".join(c.tool for c in traj.calls) or "-"
                    print(f"{prefix}[{n:>2}/{len(cases)}] {mark}  {case['id']:<32} {calls}")
                    for reason in result.reasons:
                        print(f"         - {reason}")
                    for marker, advice in FATAL_ERRORS.items():
                        if traj.error and marker in traj.error:
                            raise SystemExit(f"\nStopped: {advice}")
    finally:
        engine.dispose()
    return results


def _pct(part: int, whole: int) -> str:
    return f"{100 * part / whole:.0f}%" if whole else "-"


def _language(results: list[CaseResult]) -> str:
    known = [r.language_ok for r in results if r.language_ok is not None]
    return f"{sum(known)}/{len(known)}" if known else "-"


def _saved(results: list[CaseResult]) -> str:
    known = [r.answer_matches_saved for r in results if r.answer_matches_saved is not None]
    return f"{sum(known)}/{len(known)}" if known else "-"


def summary_markdown(
    model: str, results: list[CaseResult], server_instructions: bool = True
) -> str:
    runs = max((r.run for r in results), default=1)
    case_ids = list(dict.fromkeys(r.id for r in results))
    by_cat: dict[str, list[CaseResult]] = defaultdict(list)
    for r in results:
        by_cat[r.category].append(r)
    order = [c for c in CATEGORY_ORDER if c in by_cat] + sorted(set(by_cat) - set(CATEGORY_ORDER))

    header = f"Run: {datetime.now().strftime('%Y-%m-%d %H:%M')} · {len(case_ids)} cases"
    if runs > 1:
        header += f" × {runs} runs (counts below are over all runs)"
    if not server_instructions:
        header += " · server instructions OFF (model sees tool descriptions and results only)"
    lines = [
        f"## {model}",
        "",
        header,
        "",
        "| Category | Cases | Passed | Right tool | Right language | Answer = saved |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for cat in order:
        rs = by_cat[cat]
        passed = sum(r.passed for r in rs)
        tool_ok = sum(r.tool_ok for r in rs)
        lines.append(
            f"| {cat} | {len(rs) // runs} | {passed}/{len(rs)} ({_pct(passed, len(rs))}) "
            f"| {_pct(tool_ok, len(rs))} | {_language(rs)} | {_saved(rs)} |"
        )
    passed = sum(r.passed for r in results)
    tool_ok = sum(r.tool_ok for r in results)
    lines.append(
        f"| **total** | **{len(case_ids)}** | **{passed}/{len(results)} "
        f"({_pct(passed, len(results))})** | **{_pct(tool_ok, len(results))}** "
        f"| **{_language(results)}** | **{_saved(results)}** |"
    )
    lines += [
        "",
        (
            "Right language: answers in the request's language, of those whose language is "
            'clear (very short answers such as "İskender 620 TL." are not counted). '
            "Answer = saved: of the answers that state quantities of an order the agent "
            "placed, those whose quantities match what the server saved."
        ),
    ]

    if runs > 1:
        per_run = [sum(r.passed for r in results if r.run == i) for i in range(1, runs + 1)]
        mean = sum(per_run) / runs
        lines += [
            "",
            (
                f"Passed per run: {', '.join(map(str, per_run))} of {len(case_ids)} "
                f"(mean {mean:.1f}, min {min(per_run)}, max {max(per_run)})"
            ),
        ]

    n = len(results) or 1
    calls = sum(len(r.trajectory.calls) for r in results) / n
    tokens_in = sum(r.trajectory.input_tokens for r in results)
    tokens_out = sum(r.trajectory.output_tokens for r in results)
    seconds = sum(r.trajectory.seconds for r in results) / n
    lines += [
        "",
        (
            f"Avg tool calls per case: {calls:.1f} · Avg time: {seconds:.1f}s · "
            f"Tokens: {tokens_in:,} in / {tokens_out:,} out"
        ),
    ]

    failures: dict[str, list[CaseResult]] = defaultdict(list)
    for r in results:
        if not r.passed:
            failures[r.id].append(r)
    if failures:
        lines += ["", "### Failures", ""]
        for case_id in case_ids:
            if case_id not in failures:
                continue
            fails = failures[case_id]
            r = fails[-1]  # the latest failure stands for the others
            count = f" — failed {len(fails)}/{runs}" if runs > 1 else ""
            calls = " > ".join(c.tool for c in r.trajectory.calls) or "no tool calls"
            answer = " ".join(r.trajectory.final_text.split())
            if len(answer) > 220:
                answer = answer[:220] + "…"
            lines.append(
                f"- `{r.id}` ({r.prompt}){count} — {'; '.join(r.reasons)}  \n"
                f"  calls: {calls}  \n  answer: {answer or '-'}"
            )
    return "\n".join(lines) + "\n"


def save(
    model: str, results: list[CaseResult], out_dir: Path, server_instructions: bool = True
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = model.replace("/", "_").replace(":", "_")
    (out_dir / f"{stem}.json").write_text(
        json.dumps([r.to_dict() for r in results], ensure_ascii=False, indent=2), encoding="utf-8"
    )
    md = out_dir / f"{stem}.md"
    md.write_text(summary_markdown(model, results, server_instructions), encoding="utf-8")
    return md


def make_agent(args: argparse.Namespace) -> Agent:
    system = system_prompt(server_instructions=not args.no_instructions)
    if args.provider == "anthropic":
        if not os.getenv("ANTHROPIC_API_KEY"):
            raise SystemExit(
                "Set ANTHROPIC_API_KEY (environment or .env) to use --provider anthropic."
            )
        return AnthropicAgent(args.model, max_steps=args.max_steps, system=system)

    base_url, key_env = PROVIDERS.get(args.provider, (None, None))
    base_url = args.base_url or base_url
    if not base_url:
        raise SystemExit("--provider openai needs --base-url (an OpenAI-compatible /v1 URL).")
    key = os.getenv(key_env) if key_env else os.getenv("OPENAI_API_KEY")
    if key_env and not key:
        raise SystemExit(f"Set {key_env} (environment or .env) to use --provider {args.provider}.")
    return OpenAICompatibleAgent(
        args.model or "", base_url, key, max_steps=args.max_steps, system=system
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Turkish tool-calling eval.")
    parser.add_argument(
        "--provider", default="anthropic", choices=["anthropic", *PROVIDERS, "openai"]
    )
    parser.add_argument("--model", help="Model id. Default for anthropic: claude-sonnet-5-5.")
    parser.add_argument("--base-url", help="Override the provider URL (any OpenAI-compatible).")
    parser.add_argument("--list-models", action="store_true", help="Show the provider's models.")
    parser.add_argument("--only", help="Comma-separated case ids.")
    parser.add_argument("--category", choices=CATEGORY_ORDER)
    parser.add_argument("--max-steps", type=int, default=10)
    parser.add_argument("--days", type=int, default=30, help="Days of seeded history.")
    parser.add_argument("--out", type=Path, default=EVALS_DIR / "results")
    parser.add_argument("--tag", help="Suffix for the result files, e.g. baseline.")
    parser.add_argument("--repeat", type=int, default=1, help="Run every case N times.")
    parser.add_argument(
        "--no-instructions",
        action="store_true",
        help="Do not give the model the server's instructions, as clients that drop MCP "
        "instructions (the model sees only tool descriptions and results).",
    )
    args = parser.parse_args()
    if args.provider == "anthropic" and not args.model:
        args.model = "claude-sonnet-5-5"

    logging.getLogger("httpx").setLevel(logging.WARNING)
    agent = make_agent(args)

    if args.list_models:
        if not isinstance(agent, OpenAICompatibleAgent):
            raise SystemExit("--list-models works with OpenAI-compatible providers.")
        try:
            models = asyncio.run(agent.list_models())
        except httpx.ConnectError as exc:
            raise SystemExit(
                f"Cannot reach {agent.http.base_url}. {FATAL_ERRORS['ConnectError']}"
            ) from exc
        except httpx.HTTPError as exc:
            raise SystemExit(f"Cannot list models: {type(exc).__name__}: {exc}") from exc
        print("\n".join(models))
        return
    if not args.model:
        raise SystemExit("Pass --model (see --list-models).")

    spec = load_cases()
    cases = select_cases(spec["cases"], args.only, args.category)
    label = args.model if args.provider == "anthropic" else f"{args.provider}/{args.model}"
    if args.tag:
        label += f"@{args.tag}"
    if args.no_instructions:
        label += "+no-instructions"

    with tempfile.TemporaryDirectory() as tmp:
        results = asyncio.run(
            run_cases(agent, spec, cases, Path(tmp), days=args.days, repeat=args.repeat)
        )

    md = save(label, results, args.out, server_instructions=not args.no_instructions)
    passed = sum(r.passed for r in results)
    runs = f" over {args.repeat} runs" if args.repeat > 1 else ""
    print(f"\n{passed}/{len(results)} passed{runs}. Summary: {md}")


if __name__ == "__main__":
    main()
