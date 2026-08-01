from __future__ import annotations

from app.agent_review import reports


def test_monthly_report_only_scores_confirmed_actions(tmp_path, monkeypatch):
    recommendations_path = tmp_path / "recommendations.json"
    actions_path = tmp_path / "actions.json"
    monkeypatch.setattr(reports, "RECOMMENDATIONS_PATH", recommendations_path)
    monkeypatch.setattr(reports, "ACTIONS_PATH", actions_path)

    recommendations_path.write_text(
        """[{
          "category": "opportunity",
          "evaluated_at": "2026-07-20T00:00:00+00:00",
          "outcome": {
            "verdict": "supported",
            "excess_return_pct": 4.5,
            "reason_categories": ["direction_judgment"]
          }
        }]""",
        encoding="utf-8",
    )
    actions_path.write_text(
        """[
          {
            "action_type": "increased",
            "user_confirmed": true,
            "evaluated_at": "2026-07-21T00:00:00+00:00",
            "outcome": {
              "verdict": "supported",
              "excess_return_pct": 3,
              "reason_categories": ["direction_judgment"]
            }
          },
          {
            "action_type": "reduced",
            "user_confirmed": false,
            "evaluated_at": "2026-07-22T00:00:00+00:00",
            "outcome": {
              "verdict": "not_supported",
              "excess_return_pct": 5,
              "reason_categories": ["timing_or_threshold"]
            }
          }
        ]""",
        encoding="utf-8",
    )

    report = reports.build_monthly_report("2026-07")

    assert report["recommendations"]["support_rate_pct"] == 100
    assert report["recommendations"]["average_excess_return_pct"] == 4.5
    assert report["confirmed_actions"]["evaluated"] == 1
    assert report["unconfirmed_action_count"] == 1
    assert report["reason_categories"] == [
        {"key": "direction_judgment", "label": "方向判断", "count": 2},
    ]
