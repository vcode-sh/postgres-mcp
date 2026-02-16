from typing import Any
from typing import cast
from unittest.mock import MagicMock

import pytest

from postgres_mcp.index.dta_calc import DatabaseTuningAdvisor
from postgres_mcp.index.dta_calc import IndexRecommendation
from postgres_mcp.index.index_opt_base import IndexRecommendationAnalysis
from postgres_mcp.index.index_opt_base import IndexTuningResult
from postgres_mcp.index.presentation import TextPresentation
from postgres_mcp.sql.pg_compat import PgServerInfo


@pytest.mark.asyncio
async def test_skip_scan_candidate_is_marked_on_pg18(monkeypatch):
    async def fake_get_server_info(_sql_driver):
        return PgServerInfo(server_version_num=180000, major=18)

    monkeypatch.setattr("postgres_mcp.index.dta_calc.get_server_info", fake_get_server_info)

    dta = DatabaseTuningAdvisor(sql_driver=MagicMock())
    candidates = [IndexRecommendation(table="orders", columns=("customer_id",))]
    existing_indexes = [
        {
            "definition": "CREATE INDEX idx_orders_status_customer ON orders USING btree (status, customer_id)",
        }
    ]

    annotated = await cast(Any, dta)._annotate_skip_scan_candidates(candidates, existing_indexes)
    assert annotated[0].potential_problematic_reason == "pg18_skip_scan_redundant"


@pytest.mark.asyncio
async def test_skip_scan_candidate_not_marked_before_pg18(monkeypatch):
    async def fake_get_server_info(_sql_driver):
        return PgServerInfo(server_version_num=170000, major=17)

    monkeypatch.setattr("postgres_mcp.index.dta_calc.get_server_info", fake_get_server_info)

    dta = DatabaseTuningAdvisor(sql_driver=MagicMock())
    candidates = [IndexRecommendation(table="orders", columns=("customer_id",))]
    existing_indexes = [
        {
            "definition": "CREATE INDEX idx_orders_status_customer ON orders USING btree (status, customer_id)",
        }
    ]

    annotated = await cast(Any, dta)._annotate_skip_scan_candidates(candidates, existing_indexes)
    assert annotated[0].potential_problematic_reason is None


def test_presentation_adds_low_priority_annotation_for_skip_scan():
    sql_driver = MagicMock()
    index_tuning = MagicMock()
    presentation = TextPresentation(sql_driver=sql_driver, index_tuning=index_tuning)

    recommendation = IndexRecommendation(
        table="orders",
        columns=("customer_id",),
        potential_problematic_reason="pg18_skip_scan_redundant",
        estimated_size_bytes=1024,
    )
    analysis = IndexRecommendationAnalysis(
        index_recommendation=recommendation,
        progressive_base_cost=100.0,
        progressive_recommendation_cost=80.0,
        individual_base_cost=100.0,
        individual_recommendation_cost=80.0,
        queries=["select * from orders where customer_id = 1"],
        definition=recommendation.definition,
    )
    session = IndexTuningResult(
        session_id="test-session",
        budget_mb=10,
        recommendations=[analysis],
    )

    rendered = cast(Any, presentation)._build_recommendations_list(session)
    assert rendered[0]["confidence"] == "lower"
    assert rendered[0]["priority"] == "low"
    assert "skip scan" in rendered[0]["warning"].lower()
