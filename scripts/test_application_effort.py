import concurrent.futures
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import application_effort as effort


class DeferralsTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.now = datetime(2026, 9, 8, tzinfo=timezone.utc)
        self.key = "https://example.test/jobs/123|fall-2026"

    def defer(self, **kwargs):
        return effort.mutate(self.root, self.key, "defer", reason="manual-heavy",
                             detail="Three required unknown personal facts", now=self.now, **kwargs)

    def test_read_only_empty_and_expiry(self):
        self.assertFalse(effort.check(self.root, self.key, self.now)["deferred"])
        self.assertEqual(effort.list_active(self.root, self.now)["records"], [])
        self.assertFalse((self.root / "pipeline").exists())
        self.defer()
        self.assertTrue(effort.check(self.root, self.key, self.now)["deferred"])
        self.assertFalse(effort.check(self.root, self.key, self.now + timedelta(days=1))["deferred"])
        self.assertEqual(effort.list_active(self.root, self.now + timedelta(days=1))["records"], [])

    def test_repeated_defer_does_not_extend_and_release_keeps_history(self):
        original = self.defer()
        repeat = effort.mutate(self.root, self.key, "defer", reason="no-progress", detail="Retry",
                               now=self.now + timedelta(hours=2))
        self.assertFalse(repeat["changed"])
        self.assertEqual(original["record"], repeat["record"])
        effort.mutate(self.root, self.key, "release", now=self.now + timedelta(hours=3))
        self.assertFalse(effort.check(self.root, self.key, self.now + timedelta(hours=4))["deferred"])
        state = effort.read_state(self.root)
        self.assertEqual(state["revision"], 2)
        self.assertEqual(state["history"][0]["record"], original["record"])
        self.assertFalse(effort.mutate(self.root, self.key, "release", now=self.now)["changed"])

    def test_expired_can_be_deferred_again_and_keys_are_not_paths(self):
        self.defer(minutes=1)
        result = effort.mutate(self.root, self.key, "defer", reason="time-budget", detail="New attempt",
                               now=self.now + timedelta(minutes=2))
        self.assertTrue(result["changed"])
        effort.mutate(self.root, "../candidate|2027", "defer", reason="user-action", detail="Verification",
                      now=self.now)
        self.assertEqual(len(effort.read_state(self.root)["records"]), 2)
        self.assertFalse((self.root / "candidate").exists())

    def test_corrupt_state_fails_closed_without_overwrite(self):
        self.defer()
        path = effort.state_path(self.root)
        path.write_text('{"broken":true}')
        with self.assertRaises(ValueError):
            self.defer()
        self.assertEqual(path.read_text(), '{"broken":true}')
        process = subprocess.run([sys.executable, effort.__file__, "--root", str(self.root),
                                  "check", "--key", self.key], capture_output=True, text=True)
        self.assertEqual(process.returncode, 2)
        self.assertTrue(json.loads(process.stdout)["deferred"])

    def test_invalid_inputs_do_not_write(self):
        for kwargs in ({"minutes": 0}, {"minutes": -1}, {"minutes": 1.5}):
            with self.assertRaises(ValueError):
                self.defer(**kwargs)
        with self.assertRaises(ValueError):
            effort.mutate(self.root, "", "defer", reason="manual-heavy", detail="Missing")
        self.assertFalse((self.root / "pipeline").exists())

    def test_corrupt_history_fails_closed(self):
        self.defer()
        state = effort.read_state(self.root)
        state["history"][0]["record"]["detail"] = "Tampered history"
        effort.state_path(self.root).write_text(json.dumps(state))
        with self.assertRaises(ValueError):
            effort.check(self.root, self.key, self.now)

    def test_parallel_cli_writers_do_not_lose_records_or_touch_tracker(self):
        (self.root / "pipeline").mkdir()
        tracker = self.root / "pipeline" / "tracker.md"
        tracker.write_text("Do not change this tracker\n")
        def write(index):
            return subprocess.run([sys.executable, effort.__file__, "--root", str(self.root),
                                   "defer", "--key", f"candidate-{index}|2026", "--reason", "no-progress",
                                   "--detail", "Two attempts without progress"], capture_output=True, text=True)
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(write, range(16)))
        self.assertTrue(all(result.returncode == 0 for result in results))
        state = effort.read_state(self.root)
        self.assertEqual(state["revision"], 16)
        self.assertEqual(len(state["records"]), 16)
        self.assertEqual(len(state["history"]), 16)
        self.assertEqual(tracker.read_text(), "Do not change this tracker\n")


if __name__ == "__main__":
    unittest.main()
