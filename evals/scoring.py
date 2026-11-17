"""Score an agent's tool calls against a case from cases.yaml. Pure functions, no I/O."""

import re
from dataclasses import asdict, dataclass, field
from typing import Any

from evals.language import NAMES, detect
from evals.world import Resolver
from pos_api.timeutil import today
from pos_mcp.lines import LineError, merge_lines, resolve_day, resolve_line, same_table

WRITE_TOOLS = frozenset(
    {
        "create_order",
        "add_items_to_order",
        "set_table_status",
        "void_order_item",
        "cancel_order",
        "pay_order",
        "record_stock_purchase",
    }
)

MISSING = object()

# "Did the agent ask?" A question mark, or Turkish request phrasing that often ends without
# one: "Lütfen acı seviyesini seçin", "Hangi masa", "belirtir misiniz".
ASKS = re.compile(r"\?|(?i:lütfen|hangi|seç|belirt|söyle|ister mi|\bm[ıiuü](s[ıiuü]n[ıiuü]z)?\b)")


@dataclass
class ToolCall:
    tool: str
    args: dict[str, Any]
    is_error: bool = False
    result: str = ""


@dataclass
class Trajectory:
    calls: list[ToolCall] = field(default_factory=list)
    final_text: str = ""
    approvals_asked: list[str] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    seconds: float = 0.0
    error: str | None = None


@dataclass
class CaseResult:
    id: str
    category: str
    prompt: str
    passed: bool
    tool_ok: bool  # every expected tool was called at least once, arguments aside
    reasons: list[str]
    trajectory: Trajectory
    run: int = 1  # repetition number when a case is run several times
    language: str | None = None  # language of the request ('tr', 'en')
    answer_language: str | None = None  # detected language of the final answer, None = unclear

    @property
    def language_ok(self) -> bool | None:
        """Did the answer use the request's language? None when it cannot be told."""
        if not self.language or not self.answer_language:
            return None
        return self.answer_language == self.language

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "language_ok": self.language_ok}


# --------------------------------------------------------------------------- #
# Argument matching
# --------------------------------------------------------------------------- #


def _show(value: Any) -> str:
    return "<missing>" if value is MISSING else repr(value)


def match(expected: Any, actual: Any, resolver: Resolver, path: str = "args") -> str | None:
    """None if `actual` satisfies `expected`, otherwise a short reason."""
    if isinstance(expected, dict) and len(expected) == 1:
        ((key, value),) = expected.items()
        if key in Resolver.REFS:
            return match(resolver.resolve(key, value), actual, resolver, path)
        if key == "absent_or":
            return None if actual is MISSING else match(value, actual, resolver, path)
        if key == "absent":
            return None if actual is MISSING else f"{path} should be omitted, got {_show(actual)}"
        if key == "any":
            return None if actual is not MISSING else f"{path} is missing"
        if key == "regex":
            if isinstance(actual, str) and re.search(value, actual):
                return None
            return f"{path}={_show(actual)} does not match /{value}/"
        if key == "one_of":
            reasons = [match(v, actual, resolver, path) for v in value]
            return None if None in reasons else f"{path}={_show(actual)} matches none of {value}"

    if actual is MISSING:
        return f"{path} is missing"

    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return f"{path} should be an object, got {_show(actual)}"
        for key, exp in expected.items():
            reason = match(exp, actual.get(key, MISSING), resolver, f"{path}.{key}")
            if reason:
                return reason
        return None

    if isinstance(expected, list):
        if not isinstance(actual, list) or len(actual) != len(expected):
            return f"{path} should have {len(expected)} entries, got {_show(actual)}"
        return _match_multiset(expected, actual, resolver, path)

    if isinstance(expected, bool) or isinstance(actual, bool):
        ok = isinstance(expected, bool) and isinstance(actual, bool) and expected == actual
    elif isinstance(expected, int | float) and isinstance(actual, int | float):
        ok = float(expected) == float(actual)
    else:
        ok = expected == actual
    return None if ok else f"{path} should be {expected!r}, got {_show(actual)}"


def _depth(reason: str) -> int:
    path = reason.split(" ", 1)[0]
    return path.count(".") + path.count("[")


def _match_multiset(expected: list, actual: list, resolver: Resolver, path: str) -> str | None:
    """Order-insensitive list match (small lists, simple backtracking).

    On failure, report the most specific reason: the deepest path is the closest near-miss.
    """
    reasons: list[str] = []

    def assign(i: int, used: set[int]) -> bool:
        if i == len(expected):
            return True
        for j, act in enumerate(actual):
            if j in used:
                continue
            reason = match(expected[i], act, resolver, f"{path}[{i}]")
            if reason is None:
                if assign(i + 1, used | {j}):
                    return True
            else:
                reasons.append(reason)
        return False

    if assign(0, set()):
        return None
    return max(reasons, key=_depth) if reasons else f"{path} does not match"


# --------------------------------------------------------------------------- #
# Case scoring
# --------------------------------------------------------------------------- #


def _alternatives(requirement: dict[str, Any]) -> list[dict[str, Any]]:
    return requirement.get("any_of", [requirement])


DATE_ARGS = ("date_from", "date_to", "day")


def canonical_args(tool: str, args: dict[str, Any], resolver: Resolver) -> dict[str, Any]:
    """Score what the server would do, not how the model spelled it.

    - Order lines may name items and options instead of ids ("Acısız" = modifier id 3), and
      identical lines are one line ("1 x Adana" twice = "2 x Adana"), as the server merges.
    - A table may be given by name; for a table, add_items_to_order and create_order do the
      same thing (add to its open order, or open one), so both get the table's id.
    - Report dates may be relative ("yesterday", "-7").
    """
    args = dict(args)
    if any(k in args for k in DATE_ARGS):
        for key in DATE_ARGS:
            if key in args:
                args[key] = resolve_day(args[key], today())
    if tool not in {"create_order", "add_items_to_order"}:
        return args
    if isinstance(args.get("items"), list):
        menu, details = resolver.menu()
        items = []
        try:
            for line in args["items"]:
                if "name" in line:
                    items.append(resolve_line(line, menu, details))
                else:
                    items.append(
                        {
                            "menu_item_id": line["menu_item_id"],
                            "quantity": line.get("quantity", 1),
                            "modifier_ids": list(line.get("modifier_ids") or []),
                            "note": line.get("note", ""),
                        }
                    )
            args["items"] = merge_lines(items)
        except (LineError, KeyError, TypeError):
            pass  # scored as sent: it will not match
    if args.get("table_id") is None and args.get("table_name"):
        table = next(
            (t for t in resolver.tables() if same_table(args["table_name"], t["name"])), None
        )
        if table:
            args["table_id"] = table["id"]
    return args


def case_language(case: dict[str, Any]) -> str:
    """The request's language: `lang` in the case, else English for the english category."""
    return case.get("lang") or ("en" if case["category"] == "english" else "tr")


def score(case: dict[str, Any], traj: Trajectory, resolver: Resolver) -> CaseResult:
    reasons: list[str] = []
    if traj.error:
        reasons.append(f"run error: {traj.error}")

    expected_tools: set[str] = set()
    tool_ok = True
    for requirement in case.get("expect", []):
        alternatives = _alternatives(requirement)
        names = {alt["tool"] for alt in alternatives}
        expected_tools |= names
        if not any(c.tool in names for c in traj.calls):
            tool_ok = False
        satisfied, why = False, None
        for alt in alternatives:
            for call in traj.calls:
                if call.tool != alt["tool"]:
                    continue
                if call.is_error:
                    why = why or f"{call.tool} failed: {call.result[:160]}"
                    continue
                args = canonical_args(call.tool, call.args, resolver)
                reason = match(alt.get("args", {}), args, resolver)
                if reason is None:
                    satisfied = True
                    break
                why = why or f"{call.tool}: {reason}"
            if satisfied:
                break
        if not satisfied:
            reasons.append(why or f"never called {' or '.join(sorted(names))}")

    for rule in case.get("forbid", []):
        for call in traj.calls:
            if call.tool == rule["tool"] and not (rule.get("succeeded") and call.is_error):
                reasons.append(f"forbidden call: {call.tool}")
                break

    for call in traj.calls:
        unexpected = call.tool in WRITE_TOOLS and call.tool not in expected_tools
        if unexpected and not call.is_error and f"forbidden call: {call.tool}" not in reasons:
            reasons.append(f"unexpected write: {call.tool}")

    if case.get("ask"):
        text = traj.final_text
        if not ASKS.search(text):
            reasons.append("did not ask the user for the missing information")
        elif case.get("ask_about") and not re.search(case["ask_about"], text):
            reasons.append(f"asked, but not about /{case['ask_about']}/")

    # The user must be answered in their own language, whatever language the data is in.
    language = case_language(case)
    answer_language = detect(traj.final_text)
    if answer_language and answer_language != language:
        reasons.append(
            f"answered in {NAMES.get(answer_language, answer_language)} "
            f"to a {NAMES.get(language, language)} request"
        )

    reasons = list(dict.fromkeys(reasons))  # dedupe, keep order
    return CaseResult(
        id=case["id"],
        category=case["category"],
        prompt=case["prompt"],
        passed=not reasons,
        tool_ok=tool_ok,
        reasons=reasons,
        trajectory=traj,
        language=language,
        answer_language=answer_language,
    )
