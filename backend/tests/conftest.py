"""Keep tests independent of local credentials and the demo's persistent database."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture(autouse=True)
def isolated_runtime(tmp_path, monkeypatch):
    import main
    from rewards import RewardsStore
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("AUTH_ENABLED", "false")
    monkeypatch.setenv("REWARDS_DB_PATH", str(tmp_path / "state.sqlite3"))
    monkeypatch.setattr(main, "_rewards_store_instance", RewardsStore(str(tmp_path / "state.sqlite3")))
