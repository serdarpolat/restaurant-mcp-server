from datetime import timedelta

import pytest

from pos_api.timeutil import today

WEEK = {"date_from": str(today() - timedelta(days=6)), "date_to": str(today())}


@pytest.mark.parametrize("group_by", ["day", "hour", "weekday", "channel"])
def test_sales_groups_add_up_to_total(client, group_by):
    report = client.get("/reports/sales", params=WEEK | {"group_by": group_by}).json()
    assert report["total_orders"] > 0
    assert sum(r["orders"] for r in report["rows"]) == report["total_orders"]
    assert sum(r["revenue"] for r in report["rows"]) == pytest.approx(report["total_revenue"])


def test_daily_sales_match_daily_summaries(client):
    report = client.get("/reports/sales", params=WEEK | {"group_by": "day"}).json()
    for row in report["rows"]:
        summary = client.get("/reports/daily-summary", params={"day": row["key"]}).json()
        assert summary["orders_paid"] == row["orders"]
        assert summary["net_sales"] == pytest.approx(row["revenue"])
        assert summary["net_sales"] == pytest.approx(summary["gross_sales"] - summary["discounts"])
        assert sum(summary["by_payment_method"].values()) == pytest.approx(summary["net_sales"])


def test_top_items_sorted(client):
    rows = client.get("/reports/top-items", params=WEEK | {"sort": "revenue", "limit": 5}).json()
    assert len(rows) == 5
    revenues = [r["revenue"] for r in rows]
    assert revenues == sorted(revenues, reverse=True)


def test_staff_report_sorted_by_revenue(client):
    rows = client.get("/reports/staff", params=WEEK).json()
    assert rows[0]["revenue"] >= rows[-1]["revenue"]


def test_low_stock_and_purchase(client):
    low = client.get("/inventory/ingredients", params={"below_reorder": True}).json()
    assert low, "seed data should leave some ingredients below reorder level"
    target = low[0]
    assert target["days_of_cover"] is not None

    r = client.post(
        "/inventory/purchases",
        json={"ingredient_id": target["id"], "quantity": target["reorder_level"] * 3},
        headers={"X-Actor": "mcp:test"},
    )
    assert r.status_code == 201
    assert r.json()["below_reorder"] is False

    moves = client.get(f"/inventory/ingredients/{target['id']}/movements").json()
    assert moves[0]["reason"] == "purchase"


def test_demo_data_is_seeded_once_and_refreshed_when_stale(tmp_path):
    from datetime import datetime

    from sqlmodel import create_engine

    from pos_api.db.database import RESTAURANT_TZ
    from pos_api.db.seed import ensure_demo_data

    eng = create_engine(f"sqlite:///{tmp_path / 'demo.db'}")
    now = datetime.now(RESTAURANT_TZ).replace(microsecond=0)
    assert ensure_demo_data(eng, days=2, now=now - timedelta(days=10)) == "seeded"
    assert ensure_demo_data(eng, days=2, now=now - timedelta(days=10)) == "fresh"
    assert ensure_demo_data(eng, days=2, now=now) == "refreshed"
    eng.dispose()
