# -*- coding: utf-8 -*-
"""
Tests for new modules: arc_api_client, compute_i_weight, gaia_fetcher, post_import
"""
import json
import os
import sys
import tempfile
import sqlite3
import math
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Ensure sim dir is on path
SIM_DIR = Path(__file__).parent.parent / "sim"
sys.path.insert(0, str(SIM_DIR))


# ============================================================
# ARC API Client Tests
# ============================================================

class TestARCAPIClient:
    """Tests for arc_api_client.py"""

    def test_import(self):
        """Module imports successfully."""
        from arc_api_client import ARCAPIClient, GRID_SIZE, NUM_COLORS
        assert GRID_SIZE == 64
        assert NUM_COLORS == 16

    def test_init_without_key(self):
        """Client initializes without API key (warning only)."""
        from arc_api_client import ARCAPIClient
        client = ARCAPIClient(api_key="")
        assert client.api_key == ""
        assert client.base_url == "https://arcprize.org"

    def test_init_with_key(self):
        """Client initializes with API key."""
        from arc_api_client import ARCAPIClient
        client = ARCAPIClient(api_key="test_key_123")
        assert client.api_key == "test_key_123"

    def test_init_with_env_key(self):
        """Client picks up API key from environment."""
        old_key = os.environ.get("ARC_API_KEY")
        os.environ["ARC_API_KEY"] = "env_key_456"
        try:
            from arc_api_client import ARCAPIClient
            client = ARCAPIClient()
            assert client.api_key == "env_key_456"
        finally:
            if old_key is not None:
                os.environ["ARC_API_KEY"] = old_key
            else:
                del os.environ["ARC_API_KEY"]

    def test_timeout_config(self):
        """Client timeout is configurable."""
        from arc_api_client import ARCAPIClient
        client = ARCAPIClient(api_key="test", timeout=60)
        assert client.timeout == 60

    def test_close_without_session(self):
        """Close works even if session was never created."""
        from arc_api_client import ARCAPIClient
        client = ARCAPIClient(api_key="test")
        client.close()  # Should not raise

    def test_fetch_environment_snapshot_import(self):
        """Module-level function exists."""
        from arc_api_client import fetch_environment_snapshot
        assert callable(fetch_environment_snapshot)

    def test_build_dataset_from_api_import(self):
        """Module-level function exists."""
        from arc_api_client import build_dataset_from_api
        assert callable(build_dataset_from_api)


# ============================================================
# Compute i_weight Tests
# ============================================================

class TestComputeIWeight:
    """Tests for compute_i_weight.py"""

    def test_import(self):
        """Module imports successfully."""
        from compute_i_weight import compute_i_weight, DB_PATH, BATCH_SIZE, DEFAULT_I_WEIGHT
        assert callable(compute_i_weight)
        assert "tomas.db" in DB_PATH or DB_PATH
        assert BATCH_SIZE > 0
        assert DEFAULT_I_WEIGHT == 1.0

    def test_dry_run_on_small_db(self):
        """Dry run computes stats without modifying database."""
        from compute_i_weight import compute_i_weight

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = tmp.name

        try:
            db = sqlite3.connect(db_path)
            db.execute("""
                CREATE TABLE knowledge_triples (
                    id INTEGER PRIMARY KEY,
                    subject TEXT,
                    predicate TEXT,
                    object TEXT,
                    i_weight FLOAT DEFAULT 1.0 NOT NULL
                )
            """)
            test_data = [
                ("Python", "is-a", "language", 1.0),
                ("Python", "created-by", "Guido", 1.0),
                ("Python", "used-for", "AI", 1.0),
                ("Java", "is-a", "language", 1.0),
                ("Rust", "is-a", "language", 1.5),  # Already has non-default weight
            ]
            for s, p, o, w in test_data:
                db.execute(
                    "INSERT INTO knowledge_triples (subject, predicate, object, i_weight) VALUES (?, ?, ?, ?)",
                    (s, p, o, w)
                )
            db.commit()
            db.close()

            compute_i_weight(db_path=db_path, dry_run=True)

            db = sqlite3.connect(db_path)
            weights = db.execute("SELECT i_weight FROM knowledge_triples WHERE subject='Python'").fetchall()
            db.close()
            # Dry run should not modify
            for w in weights:
                assert w[0] == 1.0

        finally:
            os.unlink(db_path)

    def test_actual_update_on_small_db(self):
        """Actual update modifies i_weight for default-value rows."""
        from compute_i_weight import compute_i_weight

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = tmp.name

        try:
            db = sqlite3.connect(db_path)
            db.execute("""
                CREATE TABLE knowledge_triples (
                    id INTEGER PRIMARY KEY,
                    subject TEXT,
                    predicate TEXT,
                    object TEXT,
                    i_weight FLOAT DEFAULT 1.0 NOT NULL
                )
            """)
            test_data = [
                ("Python", "is-a", "language", 1.0),
                ("Python", "created-by", "Guido", 1.0),
                ("Python", "used-for", "AI", 1.0),
                ("Java", "is-a", "language", 1.0),
            ]
            for s, p, o, w in test_data:
                db.execute(
                    "INSERT INTO knowledge_triples (subject, predicate, object, i_weight) VALUES (?, ?, ?, ?)",
                    (s, p, o, w)
                )
            db.commit()
            db.close()

            compute_i_weight(db_path=db_path, dry_run=False)

            db = sqlite3.connect(db_path)
            python_weights = db.execute(
                "SELECT i_weight FROM knowledge_triples WHERE subject='Python'"
            ).fetchall()
            java_weights = db.execute(
                "SELECT i_weight FROM knowledge_triples WHERE subject='Java'"
            ).fetchall()
            db.close()

            # Python appears 3 times -> weight = 1.0 + ln(1+3)/10 ≈ 1.1386
            expected_python = 1.0 + math.log(1 + 3) / 10.0
            for w in python_weights:
                assert w[0] is not None
                assert w[0] == pytest.approx(expected_python, rel=1e-4)

            # Java appears 1 time -> weight = 1.0 + ln(1+1)/10 ≈ 1.0693
            expected_java = 1.0 + math.log(1 + 1) / 10.0
            for w in java_weights:
                assert w[0] is not None
                assert w[0] == pytest.approx(expected_java, rel=1e-4)

        finally:
            os.unlink(db_path)

    def test_preserves_existing_weights(self):
        """Rows with non-default i_weight are not modified (without --recalculate)."""
        from compute_i_weight import compute_i_weight

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = tmp.name

        try:
            db = sqlite3.connect(db_path)
            db.execute("""
                CREATE TABLE knowledge_triples (
                    id INTEGER PRIMARY KEY,
                    subject TEXT,
                    predicate TEXT,
                    object TEXT,
                    i_weight FLOAT DEFAULT 1.0 NOT NULL
                )
            """)
            # One with default, one with custom value
            db.execute("INSERT INTO knowledge_triples (subject, predicate, object, i_weight) VALUES ('A', 'b', 'c', 1.0)")
            db.execute("INSERT INTO knowledge_triples (subject, predicate, object, i_weight) VALUES ('A', 'd', 'e', 2.5)")
            db.commit()
            db.close()

            compute_i_weight(db_path=db_path, dry_run=False)

            db = sqlite3.connect(db_path)
            weights = db.execute("SELECT i_weight FROM knowledge_triples WHERE subject='A' ORDER BY id").fetchall()
            db.close()

            # First row should be updated from 1.0, second should remain 2.5
            assert weights[0][0] != 1.0  # Updated
            assert weights[1][0] == 2.5  # Unchanged

        finally:
            os.unlink(db_path)

    def test_recalculate_all(self):
        """--recalculate updates ALL rows including those with non-default weights."""
        from compute_i_weight import compute_i_weight

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = tmp.name

        try:
            db = sqlite3.connect(db_path)
            db.execute("""
                CREATE TABLE knowledge_triples (
                    id INTEGER PRIMARY KEY,
                    subject TEXT,
                    predicate TEXT,
                    object TEXT,
                    i_weight FLOAT DEFAULT 1.0 NOT NULL
                )
            """)
            db.execute("INSERT INTO knowledge_triples (subject, predicate, object, i_weight) VALUES ('A', 'b', 'c', 2.5)")
            db.execute("INSERT INTO knowledge_triples (subject, predicate, object, i_weight) VALUES ('A', 'd', 'e', 1.0)")
            db.commit()
            db.close()

            # Recalculate ALL rows
            compute_i_weight(db_path=db_path, dry_run=False, recalculate=True)

            db = sqlite3.connect(db_path)
            weights = db.execute("SELECT i_weight FROM knowledge_triples WHERE subject='A' ORDER BY id").fetchall()
            db.close()

            # Both rows should have the same computed weight (subject A appears twice)
            expected = 1.0 + math.log(1 + 2) / 10.0
            for w in weights:
                assert w[0] == pytest.approx(expected, rel=1e-4)

        finally:
            os.unlink(db_path)


# ============================================================
# GAIA Fetcher Tests
# ============================================================

class TestGAIAFetcher:
    """Tests for gaia_fetcher.py"""

    def test_import(self):
        """Module imports successfully."""
        from gaia_fetcher import GAIA_HF_REPO, GAIA_CONFIG, DEFAULT_OUTPUT
        assert GAIA_HF_REPO == "gaia-benchmark/GAIA"
        assert GAIA_CONFIG == "2023_all"
        assert DEFAULT_OUTPUT == "data/gaia_real.json"

    def test_no_token_exits(self):
        """Script exits when no token is provided."""
        import gaia_fetcher
        old_token = os.environ.pop("HF_TOKEN", None)
        old_token2 = os.environ.pop("HUGGINGFACE_TOKEN", None)
        old_argv = sys.argv
        try:
            sys.argv = ["gaia_fetcher.py", "--token", ""]
            with pytest.raises(SystemExit):
                gaia_fetcher.main()
        finally:
            sys.argv = old_argv
            if old_token:
                os.environ["HF_TOKEN"] = old_token
            if old_token2:
                os.environ["HUGGINGFACE_TOKEN"] = old_token2

    def test_download_via_datasets_library_function_exists(self):
        """Download function exists and is callable."""
        from gaia_fetcher import download_via_datasets_library
        assert callable(download_via_datasets_library)

    def test_download_via_hf_api_function_exists(self):
        """Fallback download function exists and is callable."""
        from gaia_fetcher import download_via_hf_api
        assert callable(download_via_hf_api)


# ============================================================
# Post-Import Script Tests
# ============================================================

class TestPostImport:
    """Tests for post_import.py"""

    def test_import(self):
        """Module imports successfully."""
        from post_import import check_import_running, get_db_count, get_last_log_line
        assert callable(check_import_running)
        assert callable(get_db_count)
        assert callable(get_last_log_line)

    def test_check_import_running_returns_tuple(self):
        """check_import_running returns (bool, int)."""
        from post_import import check_import_running
        result = check_import_running()
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], bool)
        assert isinstance(result[1], int)

    def test_get_last_log_line(self):
        """get_last_log_line returns a string."""
        from post_import import get_last_log_line
        result = get_last_log_line()
        assert isinstance(result, str)


# ============================================================
# Server Endpoint Tests (without running Flask)
# ============================================================

class TestServerEndpoints:
    """Verify Flask app routes are correctly registered."""

    @pytest.fixture
    def app(self):
        """Create Flask app for testing."""
        from server import app
        app.config['TESTING'] = True
        return app

    def test_health_endpoint(self, app):
        """/api/health returns 200."""
        with app.test_client() as client:
            resp = client.get('/api/health')
            assert resp.status_code == 200
            data = resp.get_json()
            assert data['status'] == 'ok'

    def test_subsystem_status_endpoint(self, app):
        """/api/subsystem-status returns structured data."""
        with app.test_client() as client:
            resp = client.get('/api/subsystem-status')
            assert resp.status_code == 200
            data = resp.get_json()
            # Response format: {'success': True, 'data': {'subsystems': [...]}}
            subsystems = data.get('data', {}).get('subsystems', data.get('subsystems', []))
            assert len(subsystems) > 0

    def test_arc_agi3_fetch_real_endpoint(self, app):
        """/api/arc-agi3/fetch-real endpoint exists."""
        with app.test_client() as client:
            resp = client.post('/api/arc-agi3/fetch-real',
                             json={},
                             content_type='application/json')
            assert resp.status_code != 404

    def test_arc_agi3_list_games_endpoint(self, app):
        """/api/arc-agi3/list-games endpoint exists."""
        with app.test_client() as client:
            resp = client.get('/api/arc-agi3/list-games')
            assert resp.status_code != 404

    def test_route_count(self, app):
        """App has expected number of routes."""
        routes = list(app.url_map.iter_rules())
        assert len(routes) >= 50
