import json
import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timezone
from build_dashboard import status_of, engine_opportunities


class DashboardTests(unittest.TestCase):
    def test_negative_outcomes(self):
        for raw, expected in [("deferred — not submitted", "deferred"), ("submitted — not rejected", "submitted"), ("not submitted", "unknown"), ("submitted-unverified", "unverified"), ("held — submitted nowhere", "deferred"), ("skipped by user", "skipped"), ("vetted, not yet submitted", "vetted"), ("mystery", "unknown")]:
            self.assertEqual(status_of({"fields": {"status": raw}}), expected, raw)

    def test_snapshot_overrides_legacy_status_and_keeps_skips(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            data = {"version": 2, "generatedAt": "2026-09-10T06:00:00Z", "counts": dict.fromkeys(("actionable", "reconcile", "deferred", "skipped", "submitted", "closed", "outOfScope", "unknown"), 0), "warnings": [], "candidates": [{"name": "Example", "state": "skipped", "recordPath": "pipeline/opportunities/one.md", "sourceUrl": "https://example.com", "category": "travel"}]}
            path.write_text(json.dumps(data))
            rows, engine, warnings = engine_opportunities([{"file": "one.md", "fields": {"status": "found"}}], path, datetime(2026, 9, 10, 6, tzinfo=timezone.utc))
            self.assertEqual(status_of(rows[0]), "skipped")
            self.assertEqual(warnings, [])
            self.assertIsNotNone(engine)
            data["candidates"][0].update(state="unverified", due=False)
            path.write_text(json.dumps(data))
            rows, _, _ = engine_opportunities([], path)
            self.assertEqual(status_of(rows[0]), "reconcile-wait")
            data["counts"]["submitted"] = "58"
            path.write_text(json.dumps(data))
            rows, engine, warnings = engine_opportunities([], path)
            self.assertEqual(rows, [])
            self.assertIsNone(engine)
            self.assertIn("withheld", warnings[0])

    def test_missing_snapshot_is_honest_legacy_fallback(self):
        rows, engine, warnings = engine_opportunities([{"fields": {"status": "submitted"}}], Path("/nonexistent-engine-state.json"))
        self.assertEqual(len(rows), 1)
        self.assertIsNone(engine)
        self.assertIn("legacy", warnings[0])


if __name__ == "__main__":
    unittest.main()
