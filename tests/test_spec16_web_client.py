"""Spec 16 AC-03: the api client's mock and live modes are tested by the web's node tests (`npm test`, run by CI's web
job). This module makes those tests visible to the AC-coverage gate and fails if they lose their AC-03 cases."""
from pathlib import Path

WEB = Path(__file__).resolve().parents[1] / "apps" / "web" / "lib"


def test_ac_03_mock_and_live_clients_are_covered_by_the_web_node_tests():
    """AC-03: lib/api.test.ts (mock) and lib/live.test.ts (live) both carry "spec 16 AC-03" cases."""
    for name in ("api.test.ts", "live.test.ts"):
        text = (WEB / name).read_text(encoding="utf-8")
        assert "spec 16 AC-03" in text, f"{name} lost its spec 16 AC-03 cases"
