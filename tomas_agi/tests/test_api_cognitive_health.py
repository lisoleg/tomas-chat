# -*- coding: utf-8 -*-
"""
TOMAS AGI v3.11 — Cognitive Health API 端点测试
=================================================
覆盖: /api/v3/cognitive-health/check, /stats, /pause, /restart
"""

import json
import pytest

# Import the Flask app
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "sim"))

from sim.server import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


# ══════════════════════════════════════════════════════════════════
# Group 1: POST /api/v3/cognitive-health/check
# ══════════════════════════════════════════════════════════════════

class TestCognitiveHealthCheckEndpoint:
    def test_check_returns_200(self, client):
        resp = client.post(
            "/api/v3/cognitive-health/check",
            data=json.dumps({}),
            content_type="application/json",
        )
        assert resp.status_code == 200

    def test_check_response_has_state(self, client):
        resp = client.post(
            "/api/v3/cognitive-health/check",
            data=json.dumps({}),
            content_type="application/json",
        )
        data = resp.get_json()
        assert "state" in data

    def test_check_response_has_recommendation(self, client):
        resp = client.post(
            "/api/v3/cognitive-health/check",
            data=json.dumps({}),
            content_type="application/json",
        )
        data = resp.get_json()
        assert "recommendation" in data

    def test_check_with_window_size(self, client):
        resp = client.post(
            "/api/v3/cognitive-health/check",
            data=json.dumps({"snap_window_size": 100}),
            content_type="application/json",
        )
        assert resp.status_code == 200


# ══════════════════════════════════════════════════════════════════
# Group 2: GET /api/v3/cognitive-health/stats
# ══════════════════════════════════════════════════════════════════

class TestCognitiveHealthStatsEndpoint:
    def test_stats_returns_200(self, client):
        resp = client.get("/api/v3/cognitive-health/stats")
        assert resp.status_code == 200

    def test_stats_has_predictions(self, client):
        resp = client.get("/api/v3/cognitive-health/stats")
        data = resp.get_json()
        assert "predictions" in data

    def test_stats_has_p_ad1(self, client):
        resp = client.get("/api/v3/cognitive-health/stats")
        data = resp.get_json()
        assert "P_AD1_habit_decay" in data.get("predictions", {})
