# tests/conftest.py
import os
import pytest
import indexly.config as config

@pytest.fixture
def test_db(tmp_path):
    """Provide a path to a temporary SQLite test database."""
    return tmp_path / "test.db"
    
@pytest.fixture(autouse=True)
def patch_db_file(test_db, monkeypatch):
    """Force all connect_db() calls to use the temp test database."""
    monkeypatch.setattr(config, "DB_FILE", str(test_db))
    return test_db

# ------------------------------
# CI-friendly mode: strip '-s' in GitHub Actions
# ------------------------------

def pytest_configure(config):
    """
    Detect CI environment and adjust pytest output:
    - If running in GitHub Actions (GITHUB_ACTIONS=true), remove '-s'
    - Locally, keep '-s' for interactive output
    """
    if os.environ.get("GITHUB_ACTIONS") == "true":
        # Only remove '-s' if present
        if "-s" in config.invocation_params.args:
            config.invocation_params.args.remove("-s")