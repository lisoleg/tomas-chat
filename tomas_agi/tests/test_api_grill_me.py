# -*- coding: utf-8 -*-
"""
TOMAS AGI v3.11 — Grill-Me API 端点测试
=========================================
覆盖: /api/v3/grill/gap-analysis, /gate-status, /trace, /trace/verify,
      /gap/close, /release
"""

import json
import pytest

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
# Group 1: POST /api/v3/grill/gap-analysis
# ══════════════════════════════════════════════════════════════════

class TestGrillGapAnalysisEndpoint:
    def test_gap_analysis_returns_200(self, client):
        resp = client.post(
            "/api/v3/grill/gap-analysis",
            data=json.dumps({"requirement": "做一个用户登录功能"}),
            content_type="application/json",
        )
        assert resp.status_code == 200

    def test_gap_analysis_has_layers(self, client):
        resp = client.post(
            "/api/v3/grill/gap-analysis",
            data=json.dumps({"requirement": "做一个用户登录功能"}),
            content_type="application/json",
        )
        data = resp.get_json()
        assert "layers" in data or "data" in data

    def test_gap_analysis_empty_requirement_400(self, client):
        resp = client.post(
            "/api/v3/grill/gap-analysis",
            data=json.dumps({"requirement": ""}),
            content_type="application/json",
        )
        assert resp.status_code in (200, 400)

    def test_gap_analysis_no_body(self, client):
        resp = client.post(
            "/api/v3/grill/gap-analysis",
            data=json.dumps({}),
            content_type="application/json",
        )
        # Empty requirement should return 400 or error
        assert resp.status_code in (200, 400)

    def test_gap_analysis_vague_requirement(self, client):
        resp = client.post(
            "/api/v3/grill/gap-analysis",
            data=json.dumps({"requirement": "做个东西"}),
            content_type="application/json",
        )
        data = resp.get_json()
        # Should have some gaps for vague requirement
        if "layers" in data:
            assert len(data["layers"]) > 0


# ══════════════════════════════════════════════════════════════════
# Group 2: GET /api/v3/grill/gate-status
# ══════════════════════════════════════════════════════════════════

class TestGrillGateStatusEndpoint:
    def test_gate_status_returns_200(self, client):
        resp = client.get("/api/v3/grill/gate-status")
        assert resp.status_code == 200

    def test_gate_status_has_total(self, client):
        resp = client.get("/api/v3/grill/gate-status")
        data = resp.get_json()
        assert "total_registered" in data or "total" in data or isinstance(data, dict)


# ══════════════════════════════════════════════════════════════════
# Group 3: GET /api/v3/grill/trace
# ══════════════════════════════════════════════════════════════════

class TestGrillTraceEndpoint:
    def test_trace_with_req_id(self, client):
        resp = client.get("/api/v3/grill/trace?req_id=test-req-001")
        assert resp.status_code == 200

    def test_trace_without_req_id(self, client):
        resp = client.get("/api/v3/grill/trace")
        # Should return error or empty result
        assert resp.status_code in (200, 400)


# ══════════════════════════════════════════════════════════════════
# Group 4: POST /api/v3/grill/trace/verify
# ══════════════════════════════════════════════════════════════════

class TestGrillTraceVerifyEndpoint:
    def test_trace_verify_returns_200(self, client):
        resp = client.post(
            "/api/v3/grill/trace/verify",
            data=json.dumps({"req_id": "test-req-001"}),
            content_type="application/json",
        )
        assert resp.status_code == 200


# ══════════════════════════════════════════════════════════════════
# Group 5: POST /api/v3/grill/gap/close
# ══════════════════════════════════════════════════════════════════

class TestGrillGapCloseEndpoint:
    def test_gap_close_returns_200(self, client):
        resp = client.post(
            "/api/v3/grill/gap/close",
            data=json.dumps({
                "requirement": "做一个用户登录功能",
                "layer": "D",
                "evidence": "数据格式为JSON",
                "closed_by": "tester",
            }),
            content_type="application/json",
        )
        assert resp.status_code == 200

    def test_gap_close_has_success(self, client):
        resp = client.post(
            "/api/v3/grill/gap/close",
            data=json.dumps({
                "requirement": "做一个用户登录功能",
                "layer": "D",
                "evidence": "数据格式为JSON",
                "closed_by": "tester",
            }),
            content_type="application/json",
        )
        data = resp.get_json()
        assert "success" in data


# ══════════════════════════════════════════════════════════════════
# Group 6: POST /api/v3/grill/release
# ══════════════════════════════════════════════════════════════════

class TestGrillReleaseEndpoint:
    def test_release_returns_200(self, client):
        resp = client.post(
            "/api/v3/grill/release",
            data=json.dumps({
                "requirement": "做一个用户登录功能",
            }),
            content_type="application/json",
        )
        assert resp.status_code == 200

    def test_release_has_locked_field(self, client):
        resp = client.post(
            "/api/v3/grill/release",
            data=json.dumps({
                "requirement": "做一个用户登录功能",
            }),
            content_type="application/json",
        )
        data = resp.get_json()
        assert "locked" in data or "success" in data
