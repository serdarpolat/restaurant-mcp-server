"""The eval harness itself, tested without any model or network: a scripted agent plays the
role of the LLM, so we know exactly which cases must pass and which must fail."""

from collections.abc import Callable

import pytest
from sqlmodel import Session

from evals.harness import ToolSession
from evals.run import load_cases, run_cases, select_cases, summary_markdown
from evals.scoring import MISSING, ToolCall, Trajectory, match, score
from evals.world import Resolver, build_world, sqlite_engine

SPEC = load_cases()
CASES = {c["id"]: c for c in SPEC["cases"]}

Plan = Callable[[Resolver], tuple[list[tuple[str, dict]], str]]


@pytest.fixture(scope="module")
def world_db(tmp_path_factory):
    path = tmp_path_factory.mktemp("evals") / "world.db"
    build_world(path, SPEC["world"], days=7)
    return path


@pytest.fixture
def resolver(world_db):
    engine = sqlite_engine(world_db)
    with Session(engine) as session:
        yield Resolver(session)
    engine.dispose()


class ScriptedAgent:
    """Replays planned tool calls (ids looked up from the eval world) and a final answer."""

    name = "scripted"

    def __init__(self, plans: dict[str, Plan], resolver: Resolver):
        self.plans = plans
        self.resolver = resolver

    async def run(self, prompt: str, session: ToolSession) -> Trajectory:
        case_id = next(c["id"] for c in SPEC["cases"] if c["prompt"] == prompt)
        calls, final_text = self.plans[case_id](self.resolver)
        for tool, args in calls:
            await session.call(tool, args)
        return Trajectory(
            calls=list(session.calls),
            final_text=final_text,
            approvals_asked=list(session.approvals_asked),
        )


def r(resolver: Resolver, ref: str, value) -> int | str:
    return resolver.resolve(ref, value)


GOOD: dict[str, Plan] = {
    "report-top5-yesterday": lambda x: (
        [
            (
                "get_top_items",
                {"date_from": r(x, "date", -1), "date_to": r(x, "date", -1), "limit": 5},
            )
        ],
        "İşte dünün en çok satanları.",
    ),
    "write-new-dine-in": lambda x: (
        [
            ("search_menu", {"query": "adana"}),
            (
                "create_order",
                {
                    "table_id": r(x, "table", "Salon 3"),
                    "items": [
                        {"name": "Ayran", "menu_item_id": r(x, "menu", "Ayran"), "quantity": 2},
                        {
                            "name": "Adana Kebap",
                            "menu_item_id": r(x, "menu", "Adana Kebap"),
                            "quantity": 2,
                            "modifier_ids": [r(x, "modifier", ["Adana Kebap", "Acılı"])],
                        },
                    ],
                },
            ),
        ],
        "Sipariş açıldı.",
    ),
    "en-new-dine-in-mixed": lambda x: (
        [
            ("search_menu", {"query": "adana kebab"}),
            (
                "create_order",
                {
                    "table_id": r(x, "table", "Salon 4"),
                    "items": [
                        {
                            "name": "Adana Kebap",
                            "menu_item_id": r(x, "menu", "Adana Kebap"),
                            "modifier_ids": [r(x, "modifier", ["Adana Kebap", spice])],
                        }
                        for spice in ("Acısız", "Acılı")
                    ],
                },
            ),
        ],
        "Order opened on Salon 4.",
    ),
    # names and option names instead of ids score the same as ids
    "write-mixed-spice": lambda x: (
        [
            (
                "create_order",
                {
                    "table_name": "Salon 6",
                    "items": [
                        {"name": "adana kebab", "options": ["spicy"]},
                        {"name": "Adana Kebap", "options": ["Acısız"]},
                    ],
                },
            )
        ],
        "Sipariş açıldı.",
    ),
    "approve-cancel-restock": lambda x: (
        [
            (
                "cancel_order",
                {
                    "order_id": r(x, "open_order", "Teras 2"),
                    "reason": "Mutfağa gitmeden vazgeçtiler",
                    "return_to_stock": True,
                },
            )
        ],
        "İptal edildi, malzemeler stoğa döndü.",
    ),
    "ask-spice-adana": lambda x: (
        [("search_menu", {"query": "adana"})],
        "Adana için acı seviyesi ne olsun: acılı, az acılı, acısız?",
    ),
}

BAD: dict[str, Plan] = {
    # both spice levels on one line of 2: refused by the POS, so no order is opened
    "en-new-dine-in-mixed": lambda x: (
        [
            (
                "create_order",
                {
                    "table_id": r(x, "table", "Salon 4"),
                    "items": [
                        {
                            "name": "Adana Kebap",
                            "menu_item_id": r(x, "menu", "Adana Kebap"),
                            "quantity": 2,
                            "modifier_ids": [
                                r(x, "modifier", ["Adana Kebap", "Acılı"]),
                                r(x, "modifier", ["Adana Kebap", "Acısız"]),
                            ],
                        }
                    ],
                },
            )
        ],
        "Could you specify the spice level for each kebab?",
    ),
    # wrong date range
    "report-top5-yesterday": lambda x: (
        [("get_top_items", {"date_from": r(x, "date", 0), "limit": 5})],
        "Bugünün en çok satanları.",
    ),
    # picks the spice level for the user
    "write-new-dine-in": lambda x: (
        [
            (
                "create_order",
                {
                    "table_id": r(x, "table", "Salon 3"),
                    "items": [
                        {"name": "Ayran", "menu_item_id": r(x, "menu", "Ayran"), "quantity": 2},
                        {
                            "name": "Adana Kebap",
                            "menu_item_id": r(x, "menu", "Adana Kebap"),
                            "quantity": 2,
                            "modifier_ids": [r(x, "modifier", ["Adana Kebap", "Acısız"])],
                        },
                    ],
                },
            )
        ],
        "Sipariş açıldı.",
    ),
    # forgets the restock request
    "approve-cancel-restock": lambda x: (
        [("cancel_order", {"order_id": r(x, "open_order", "Teras 2"), "reason": "Vazgeçtiler"})],
        "İptal edildi.",
    ),
    # guesses instead of asking
    "ask-spice-adana": lambda x: (
        [
            (
                "create_order",
                {
                    "table_id": r(x, "table", "Salon 4"),
                    "items": [
                        {
                            "name": "Adana Kebap",
                            "menu_item_id": r(x, "menu", "Adana Kebap"),
                            "modifier_ids": [r(x, "modifier", ["Adana Kebap", "Acılı"])],
                        }
                    ],
                },
            )
        ],
        "Acılı Adana siparişi açıldı.",
    ),
}


async def _run(plans: dict[str, Plan], resolver, tmp_path):
    cases = [CASES[i] for i in plans]
    agent = ScriptedAgent(plans, resolver)
    return {res.id: res for res in await run_cases(agent, SPEC, cases, tmp_path, days=7)}


def test_cases_file_is_well_formed():
    ids = [c["id"] for c in SPEC["cases"]]
    assert len(ids) == len(set(ids)) >= 25
    for case in SPEC["cases"]:
        assert case["category"] in {
            "report",
            "inventory",
            "menu",
            "write",
            "ask",
            "approval",
            "english",
        }
        assert case.get("expect") or case.get("ask"), case["id"]


def test_every_reference_in_the_cases_resolves(resolver):
    def walk(node):
        if isinstance(node, dict):
            if len(node) == 1:
                ((key, value),) = node.items()
                if key in Resolver.REFS:
                    resolver.resolve(key, value)  # raises if the world lacks it
                    return
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(SPEC["cases"])


async def test_correct_agent_passes(resolver, tmp_path):
    results = await _run(GOOD, resolver, tmp_path)
    assert {i: res.reasons for i, res in results.items() if not res.passed} == {}
    # the simulated user was asked to approve the cancellation, with the stock note
    approvals = results["approve-cancel-restock"].trajectory.approvals_asked
    assert len(approvals) == 1 and "back to stock" in approvals[0]


async def test_wrong_agent_fails_for_the_right_reasons(resolver, tmp_path):
    results = await _run(BAD, resolver, tmp_path)
    assert not any(res.passed for res in results.values())
    assert "date_from" in results["report-top5-yesterday"].reasons[0]
    assert "modifier_ids" in results["write-new-dine-in"].reasons[0]
    assert "return_to_stock" in results["approve-cancel-restock"].reasons[0]
    assert any("forbidden call" in x for x in results["ask-spice-adana"].reasons)
    assert results["report-top5-yesterday"].tool_ok  # right tool, wrong arguments

    md = summary_markdown("scripted", list(results.values()))
    assert "| **total** | **5** | **0/5 (0%)** |" in md


def test_matchers(resolver):
    assert match({"absent_or": 0}, MISSING, resolver) is None
    assert match({"absent_or": 0}, 0.0, resolver) is None
    assert match({"absent": True}, None, resolver)
    assert match({"one_of": ["free", {"absent": True}]}, MISSING, resolver) is None
    assert match({"regex": "(?i)skender"}, "İskender", resolver) is None
    assert match(True, 1, resolver)  # booleans are not numbers
    assert match([1, 2], [2, 1], resolver) is None
    assert match([1, 2], [1, 2, 3], resolver)


def test_unexpected_writes_fail_a_read_case(resolver):
    case = CASES["floor-bill-total"]
    order_id = resolver.resolve("open_order", "Teras 2")
    traj = Trajectory(
        calls=[
            ToolCall("get_order", {"order_id": order_id}),
            ToolCall("pay_order", {"order_id": order_id, "method": "cash"}),
        ],
        final_text="Hesap kapatıldı.",
    )
    result = score(case, traj, resolver)
    assert result.reasons == ["unexpected write: pay_order"]


def test_select_cases():
    assert [c["id"] for c in select_cases(SPEC["cases"], "ask-spice-adana", None)] == [
        "ask-spice-adana"
    ]
    assert all(c["category"] == "ask" for c in select_cases(SPEC["cases"], None, "ask"))
    with pytest.raises(SystemExit):
        select_cases(SPEC["cases"], "nope", None)


class BrokeAgent:
    name = "broke"

    async def run(self, prompt: str, session: ToolSession) -> Trajectory:
        return Trajectory(error="BadRequestError: Your credit balance is too low to access the API")


async def test_account_errors_stop_the_run(tmp_path):
    with pytest.raises(SystemExit, match="no credits"):
        await run_cases(BrokeAgent(), SPEC, SPEC["cases"][:3], tmp_path, days=7)


async def test_openai_compatible_agent_against_a_fake_lm_studio(resolver, tmp_path):
    """The OpenAI-format loop: tool call -> tool result -> final answer (think block hidden)."""
    import json

    import httpx

    from evals.agent import OpenAICompatibleAgent

    yesterday = resolver.resolve("date", -1)
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen.append(body)
        if len(seen) == 1:
            assert body["tools"][0]["type"] == "function"
            call = {
                "id": "call_1",
                "type": "function",
                "function": {
                    "name": "get_top_items",
                    "arguments": json.dumps(
                        {"date_from": yesterday, "date_to": yesterday, "limit": 5}
                    ),
                },
            }
            message = {"role": "assistant", "content": None, "tool_calls": [call]}
        else:
            assert body["messages"][-1]["role"] == "tool"
            assert body["messages"][-1]["tool_call_id"] == "call_1"
            message = {"role": "assistant", "content": "<think>hmm?</think>Dünün ilk 5'i hazır."}
        usage = {"prompt_tokens": 100, "completion_tokens": 10}
        return httpx.Response(200, json={"choices": [{"message": message}], "usage": usage})

    agent = OpenAICompatibleAgent(
        "fake-model", "http://lmstudio/v1", transport=httpx.MockTransport(handler)
    )
    [result] = await run_cases(agent, SPEC, [CASES["report-top5-yesterday"]], tmp_path, days=7)
    assert result.passed, result.reasons
    assert result.trajectory.final_text == "Dünün ilk 5'i hazır."
    assert result.trajectory.input_tokens == 200


async def test_unreachable_model_server_stops_the_run(tmp_path):
    import httpx

    from evals.agent import OpenAICompatibleAgent

    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    agent = OpenAICompatibleAgent(
        "m", "http://localhost:1/v1", transport=httpx.MockTransport(refuse)
    )
    with pytest.raises(SystemExit, match="Start Server"):
        await run_cases(agent, SPEC, SPEC["cases"][:2], tmp_path, days=7)


@pytest.mark.parametrize(
    ("answer", "passes"),
    [
        ("Adana için acı seviyesi ne olsun?", True),
        ("Lütfen Adana Kebap için acı seviyesini seçin: Acılı, Az Acılı, Acısız", True),
        ("Acılı mı olsun, acısız mı", True),
        ("Salon 4'e Adana siparişi açtım.", False),  # no question
        ("Hangi masaya açayım?", False),  # a question, but not about the spice level
    ],
)
def test_ask_detection(resolver, answer, passes):
    result = score(CASES["ask-spice-adana"], Trajectory(final_text=answer), resolver)
    assert result.passed is passes, result.reasons


async def test_repeat_reports_per_run_totals_and_unstable_cases(resolver, tmp_path):
    flips = iter([True, False])  # passes in run 1, fails in run 2

    def plan(x):
        good = next(flips)
        return GOOD["report-top5-yesterday"](x) if good else BAD["report-top5-yesterday"](x)

    agent = ScriptedAgent({"report-top5-yesterday": plan}, resolver)
    case = [CASES["report-top5-yesterday"]]
    results = await run_cases(agent, SPEC, case, tmp_path, days=7, repeat=2)
    assert [(r.run, r.passed) for r in results] == [(1, True), (2, False)]
    md = summary_markdown("scripted", results)
    assert "Passed per run: 1, 0 of 1" in md
    assert "failed 1/2" in md
