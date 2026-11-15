"""Run the Turkish tool-calling eval.

    uv sync --extra eval
    set ANTHROPIC_API_KEY=...            (or put it in .env)
    uv run python -m evals.run --model claude-sonnet-5-5
    uv run python -m evals.run --model claude-haiku-5-5 --only write-new-dine-in,ask-spice-adana

Writes evals/results/<model>.json (every call, for debugging) and <model>.md (summary).
"""

import argparse
import asyncio
import json
import os
import shutil
import sys
import tempfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from sqlmodel import Session

from evals.agent import Agent, AnthropicAgent
from evals.harness import tool_session
from evals.scoring import CaseResult, score
from evals.world import Resolver, build_world, sqlite_engine

EVALS_DIR = Path(__file__).parent
CASES_FILE = EVALS_DIR / "cases.yaml"
CATEGORY_ORDER = ["report", "inventory", "menu", "write", "ask", "approval"]


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
    agent: Agent, spec: dict[str, Any], cases: list[dict], workdir: Path, days: int = 30
) -> list[CaseResult]:
    template = workdir / "world.db"
    print(f"Building the eval restaurant ({days} days of history)...", file=sys.stderr)
    build_world(template, spec.get("world", {}), days=days)

    engine = sqlite_engine(template)
    results: list[CaseResult] = []
    try:
        with Session(engine) as session:
            resolver = Resolver(session)  # expected ids come from the untouched world
            for n, case in enumerate(cases, start=1):
                db = workdir / f"case-{n}.db"
                shutil.copy(template, db)
                async with tool_session(db) as tools:
                    traj = await agent.run(case["prompt"], tools)
                result = score(case, traj, resolver)
                results.append(result)
                mark = "PASS" if result.passed else "FAIL"
                calls = " > ".join(c.tool for c in traj.calls) or "-"
                print(f"[{n:>2}/{len(cases)}] {mark}  {case['id']:<32} {calls}")
                for reason in result.reasons:
                    print(f"         - {reason}")
                if traj.error and "Authentication" in traj.error:
                    raise SystemExit("Authentication failed. Check ANTHROPIC_API_KEY.")
    finally:
        engine.dispose()
    return results


def _pct(part: int, whole: int) -> str:
    return f"{100 * part / whole:.0f}%" if whole else "-"


def summary_markdown(model: str, results: list[CaseResult]) -> str:
    by_cat: dict[str, list[CaseResult]] = defaultdict(list)
    for r in results:
        by_cat[r.category].append(r)
    order = [c for c in CATEGORY_ORDER if c in by_cat] + sorted(set(by_cat) - set(CATEGORY_ORDER))

    lines = [
        f"## {model}",
        "",
        f"Run: {datetime.now().strftime('%Y-%m-%d %H:%M')} · {len(results)} cases",
        "",
        "| Category | Cases | Passed | Right tool |",
        "|---|---:|---:|---:|",
    ]
    for cat in order:
        rs = by_cat[cat]
        passed = sum(r.passed for r in rs)
        tool_ok = sum(r.tool_ok for r in rs)
        lines.append(
            f"| {cat} | {len(rs)} | {passed} ({_pct(passed, len(rs))}) | {_pct(tool_ok, len(rs))} |"
        )
    passed = sum(r.passed for r in results)
    tool_ok = sum(r.tool_ok for r in results)
    lines.append(
        f"| **total** | **{len(results)}** | **{passed} ({_pct(passed, len(results))})** "
        f"| **{_pct(tool_ok, len(results))}** |"
    )

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

    failed = [r for r in results if not r.passed]
    if failed:
        lines += ["", "### Failures", ""]
        for r in failed:
            calls = " > ".join(c.tool for c in r.trajectory.calls) or "no tool calls"
            lines.append(f"- `{r.id}` ({r.prompt}) — {'; '.join(r.reasons)}  \n  calls: {calls}")
    return "\n".join(lines) + "\n"


def save(model: str, results: list[CaseResult], out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = model.replace("/", "_").replace(":", "_")
    (out_dir / f"{stem}.json").write_text(
        json.dumps([r.to_dict() for r in results], ensure_ascii=False, indent=2), encoding="utf-8"
    )
    md = out_dir / f"{stem}.md"
    md.write_text(summary_markdown(model, results), encoding="utf-8")
    return md


def main() -> None:
    parser = argparse.ArgumentParser(description="Turkish tool-calling eval.")
    parser.add_argument("--model", default="claude-sonnet-5-5", help="Anthropic model id.")
    parser.add_argument("--only", help="Comma-separated case ids.")
    parser.add_argument("--category", choices=CATEGORY_ORDER)
    parser.add_argument("--max-steps", type=int, default=10)
    parser.add_argument("--days", type=int, default=30, help="Days of seeded history.")
    parser.add_argument("--out", type=Path, default=EVALS_DIR / "results")
    args = parser.parse_args()

    if not os.getenv("ANTHROPIC_API_KEY"):
        raise SystemExit("Set ANTHROPIC_API_KEY (environment or .env) to run the eval.")

    spec = load_cases()
    cases = select_cases(spec["cases"], args.only, args.category)
    agent = AnthropicAgent(args.model, max_steps=args.max_steps)

    with tempfile.TemporaryDirectory() as tmp:
        results = asyncio.run(run_cases(agent, spec, cases, Path(tmp), days=args.days))

    md = save(args.model, results, args.out)
    passed = sum(r.passed for r in results)
    print(f"\n{passed}/{len(results)} passed. Summary: {md}")


if __name__ == "__main__":
    main()
