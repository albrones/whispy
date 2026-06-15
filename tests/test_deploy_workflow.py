"""Structural tests for the website deploy pipeline (deploy-website.yml).

The workflow itself only runs in CI, but its contract is testable from here:
it must be valid YAML, fire only on website changes, and wire up the Vercel
secrets. These guard against the common breakages — a bad path filter that
deploys on every commit, or a renamed secret that silently no-ops the deploy.
"""

from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

WORKFLOW = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "deploy-website.yml"


@pytest.fixture(scope="module")
def workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def test_workflow_exists():
    assert WORKFLOW.is_file(), "deploy-website.yml is missing"


def test_workflow_is_valid_yaml(workflow: dict):
    assert isinstance(workflow, dict)


def test_triggers_are_path_filtered_to_website(workflow: dict):
    # PyYAML parses the bare ``on:`` key as the boolean True.
    on = workflow.get("on") or workflow.get(True)
    assert on, "workflow has no triggers"
    for event in ("push", "pull_request"):
        assert event in on, f"missing {event} trigger"
        assert on[event]["paths"] == ["website/**"], f"{event} must be path-filtered to website/**"


def test_push_trigger_only_on_main(workflow: dict):
    on = workflow.get("on") or workflow.get(True)
    assert on["push"]["branches"] == ["main"]


def test_tags_do_not_trigger_website_deploy(workflow: dict):
    on = workflow.get("on") or workflow.get(True)
    assert "tags" not in on["push"], "tag pushes must not deploy the website"


def test_references_required_vercel_secrets():
    text = WORKFLOW.read_text(encoding="utf-8")
    for secret in ("VERCEL_TOKEN", "VERCEL_ORG_ID", "VERCEL_PROJECT_ID"):
        assert f"secrets.{secret}" in text, f"workflow does not use {secret}"
