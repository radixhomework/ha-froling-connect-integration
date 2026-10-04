"""Sanity tests for the integration skeleton and the recorded API fixtures."""

import json
from pathlib import Path

from custom_components.froling_connect.const import DOMAIN

REPO_ROOT = Path(__file__).parents[1]
COMPONENT_DIR = REPO_ROOT / "custom_components" / "froling_connect"


def test_manifest_matches_skeleton():
    manifest = json.loads((COMPONENT_DIR / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["domain"] == DOMAIN
    assert manifest["iot_class"] == "cloud_polling"
    assert manifest["requirements"] == []


def test_all_fixtures_are_valid_json():
    fixture_files = sorted((REPO_ROOT / "tests" / "fixtures").glob("*.json"))
    assert len(fixture_files) >= 6, fixture_files
    for path in fixture_files:
        json.loads(path.read_text(encoding="utf-8"))
