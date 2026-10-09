"""Tests for the promise CLI commands that deal with manual status and review."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from tisza_tracker.cli import cli
from tisza_tracker.core.config import ConfigManager
from tisza_tracker.core.promise_store import PromiseStore
from tisza_tracker.processors.llm_classifier import effective_prompt_version


@pytest.fixture
def env(tmp_data_dir: Path):
    config_path = str(tmp_data_dir / "config" / "config.yaml")
    config = ConfigManager(config_path).load_config()
    ps = PromiseStore(config)
    ps.add_promise("P-1", "Elfogadjuk a törvényt.", "gazdasag", deadline="2026-06-01")
    ps.add_promise("P-2", "Megtartjuk.", "gazdasag", kind="ongoing")

    def invoke(*args):
        return CliRunner().invoke(cli, ["--config", config_path, *args])

    version = effective_prompt_version(config["llm_classification"])
    return type("Env", (), {"invoke": staticmethod(invoke), "ps": ps, "version": version})


def test_status_command_locks_by_default(env):
    result = env.invoke("promise", "status", "P-1", "kept", "--evidence", "read the decree")
    assert result.exit_code == 0
    assert "(locked)" in result.output

    promise = env.ps.get_promise("P-1")
    assert promise["current_status"] == "kept"
    assert promise["status_locked"] == 1
    history = env.ps.get_status_history("P-1")
    assert history[-1]["source"] == "manual"
    assert history[-1]["evidence"] == "read the decree"


def test_status_command_no_lock(env):
    result = env.invoke("promise", "status", "P-1", "made", "--no-lock")
    assert result.exit_code == 0
    assert env.ps.get_promise("P-1")["status_locked"] == 0


def test_status_command_rejects_unknown_status(env):
    result = env.invoke("promise", "status", "P-1", "nonsense")
    assert result.exit_code != 0


def test_unlock_command(env):
    env.invoke("promise", "status", "P-1", "kept")
    result = env.invoke("promise", "unlock", "P-1")
    assert result.exit_code == 0
    assert env.ps.get_promise("P-1")["status_locked"] == 0

    assert env.invoke("promise", "unlock", "NOPE").exit_code != 0


def test_show_command_prints_kind_lock_and_flags(env):
    env.ps.update_status("P-2", "in_progress")
    env.ps.set_review_flags("P-2", ["delayed"])
    output = env.invoke("promise", "show", "P-2").output
    assert "Kind: ongoing" in output
    assert "locked" in output
    assert "Flag: delayed" in output


def test_review_command_lists_only_promises_needing_a_decision(env):
    assert "Nothing to review." in env.invoke("promise", "review").output

    env.ps.set_review_flags("P-1", ["review: reversal reported by 2 outlets", "delayed"])
    env.ps.set_review_flags("P-2", ["announced only"])
    env.ps.upsert_classification(
        "P-1", "E1", signal="reversal", outlet="Telex", published_date="2026-09-01",
        reasoning="The government dropped the bill.", prompt_version=env.version,
    )

    output = env.invoke("promise", "review").output
    assert "P-1" in output
    assert "review: reversal reported by 2 outlets" in output
    assert "[reversal] 2026-09-01 Telex" in output
    assert "The government dropped the bill." in output
    assert "P-2" not in output
    assert "delayed" not in output.replace("review:", "")

    items = json.loads(env.invoke("promise", "review", "--json").output)
    assert [i["id"] for i in items] == ["P-1"]
    assert items[0]["flags"] == ["review: reversal reported by 2 outlets"]
    assert items[0]["evidence"][0]["signal"] == "reversal"


def test_labelled_set_command_scores_recorded_outputs(env):
    result = env.invoke("eval", "--recorded")
    assert result.exit_code == 0
    assert "false reversals on real pairs:   1/99" in result.output
    assert "synthetic reversals caught:      4/4" in result.output
    assert "OK" in result.output
