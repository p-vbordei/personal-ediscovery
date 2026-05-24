"""CLI smoke tests using typer.testing.CliRunner."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from personal_ediscovery import cli as cli_module
from personal_ediscovery import store as store_module


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def isolated_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect the CLI's default Store() path to a per-test temp dir."""
    target = tmp_path / "store"
    monkeypatch.setattr(store_module, "DEFAULT_DIR", target)
    return target


@pytest.fixture
def corpus(tmp_path: Path) -> Path:
    root = tmp_path / "corpus"
    root.mkdir()
    (root / "kitchen.md").write_text("Kitchen renovation budget: $20000.")
    (root / "vacation.md").write_text("Vacation plan to Lisbon for next summer.")
    (root / "storage.txt").write_text("Old roommate left their things in storage unit B.")
    return root


def test_init_index_search_flow(
    runner: CliRunner, isolated_store: Path, corpus: Path
) -> None:
    r = runner.invoke(
        cli_module.app,
        ["init", "--collection", "notes", "--root", str(corpus)],
    )
    assert r.exit_code == 0, r.output
    assert "Created collection" in r.output
    assert "Consent token" in r.output

    r = runner.invoke(cli_module.app, ["index", "--collection", "notes"])
    assert r.exit_code == 0, r.output
    assert "Indexed 3 documents" in r.output

    r = runner.invoke(
        cli_module.app, ["search", "kitchen", "--collection", "notes"]
    )
    assert r.exit_code == 0, r.output
    assert "kitchen" in r.output.lower()


def test_forget_then_search_empty(
    runner: CliRunner, isolated_store: Path, corpus: Path
) -> None:
    runner.invoke(cli_module.app, ["init", "--collection", "notes", "--root", str(corpus)])
    runner.invoke(cli_module.app, ["index", "--collection", "notes"])

    r = runner.invoke(
        cli_module.app,
        ["forget", "--collection", "notes", "--query", "roommate"],
    )
    assert r.exit_code == 0, r.output
    assert "Removed 1" in r.output

    r = runner.invoke(
        cli_module.app, ["search", "roommate", "--collection", "notes", "--output", "json"]
    )
    assert r.exit_code == 0, r.output
    payload = json.loads(r.output)
    assert payload == []


def test_mcp_stdio_prints_contract(runner: CliRunner) -> None:
    r = runner.invoke(cli_module.app, ["mcp-stdio"])
    assert r.exit_code == 0, r.output
    contract = json.loads(r.output)
    assert contract["spec"] == "mcp-provenance/0.1"
    assert contract["name"] == "@personal-ediscovery/server"
    tools = contract["capabilities"]["tools"]
    assert "ediscovery.search" in tools
    assert "ediscovery.forget" in tools


def test_list_shows_collection_with_doc_count(
    runner: CliRunner, isolated_store: Path, corpus: Path
) -> None:
    runner.invoke(cli_module.app, ["init", "--collection", "notes", "--root", str(corpus)])
    runner.invoke(cli_module.app, ["index", "--collection", "notes"])

    r = runner.invoke(cli_module.app, ["list"])
    assert r.exit_code == 0, r.output
    assert "notes" in r.output
    assert "fs-text" in r.output
    assert "(3 docs)" in r.output
