"""Tests for the GATE-01 idempotence gate."""

import hashlib
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


FIX = Path(__file__).resolve().parent / "fixtures"
GATE_SCRIPT = Path(os.environ.get(
    "GATE_SCRIPT",
    Path(__file__).resolve().parents[2] / "scripts" / "gate-idempotence.py"))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class GateIdempotence(unittest.TestCase):
    def run_gate(self, inventory, artifact_dir, leg, run_id, run_attempt="1"):
        completed = subprocess.run(
            [
                "python3",
                str(GATE_SCRIPT),
                "--inventory-dump",
                str(FIX / inventory),
                "--artifact-dir",
                str(artifact_dir),
                "--leg",
                leg,
                "--run-id",
                run_id,
                "--run-attempt",
                run_attempt,
            ],
            capture_output=True,
            check=False,
            text=True,
        )
        return (
            completed.returncode,
            completed.stdout.removesuffix("\n"),
            completed.stderr,
        )

    def test_t01_clean_second_converge_passes(self):
        rc, stdout, _ = self.run_gate(
            "inventory-main.json", FIX, "converge-2", "SPIKE100"
        )

        self.assertEqual(rc, 0)
        self.assertEqual(
            stdout,
            "PASS: converge-2-SPIKE100-1.json; "
            "expected=node_a,node_b,node_c; excluded=controller_explicit",
        )

    def test_t02_merged_stderr_is_unparseable(self):
        rc, stdout, _ = self.run_gate(
            "inventory-main.json", FIX, "converge-2", "COMBINED101"
        )

        self.assertEqual(rc, 1)
        self.assertTrue(stdout.startswith("FAIL: unreadable JSON: "))

    def test_t03_ignored_failure_fails(self):
        rc, stdout, _ = self.run_gate(
            "inventory-main.json", FIX, "converge-2", "IGNORE200"
        )

        self.assertEqual(rc, 1)
        self.assertTrue(stdout.startswith("FAIL: four-zero predicate: "))
        self.assertEqual(
            stdout,
            "FAIL: four-zero predicate: "
            "node_a.ignored=1,node_b.ignored=1,node_c.ignored=1",
        )

    def test_t04_unreachable_host_fails(self):
        rc, stdout, _ = self.run_gate(
            "inventory-unreachable.json", FIX, "converge-2", "UNREACH300"
        )

        self.assertEqual(rc, 1)
        self.assertTrue(stdout.startswith("FAIL: four-zero predicate: "))
        self.assertEqual(
            stdout,
            "FAIL: four-zero predicate: dead_host.unreachable=1",
        )

    def test_t05_limited_run_misses_hosts(self):
        rc, stdout, _ = self.run_gate(
            "inventory-main.json", FIX, "converge-2", "LIMIT400"
        )

        self.assertEqual(rc, 1)
        self.assertTrue(stdout.startswith("FAIL: missing expected hosts: "))
        self.assertEqual(stdout, "FAIL: missing expected hosts: node_b,node_c")

    def test_t06_varless_host_limited_out_fails(self):
        rc, stdout, _ = self.run_gate(
            "inventory-varless.json", FIX, "converge-2", "VARLESS401"
        )

        self.assertEqual(rc, 1)
        self.assertTrue(stdout.startswith("FAIL: missing expected hosts: "))
        self.assertEqual(stdout, "FAIL: missing expected hosts: varless_a")

    def test_t07_non_idempotent_second_converge_fails(self):
        rc, stdout, _ = self.run_gate(
            "inventory-main.json", FIX, "converge-2", "NONIDEM600"
        )

        self.assertEqual(rc, 1)
        self.assertTrue(stdout.startswith("FAIL: four-zero predicate: "))
        self.assertEqual(
            stdout,
            "FAIL: four-zero predicate: "
            "node_a.changed=1,node_b.changed=1,node_c.changed=1",
        )

    def test_t08_check_leg_reports_both_categories(self):
        rc, stdout, _ = self.run_gate(
            "inventory-main.json", FIX, "check-diff", "SPIKE700"
        )

        self.assertEqual(rc, 1)
        self.assertTrue(stdout.startswith("FAIL: four-zero predicate: "))
        self.assertEqual(
            stdout,
            "FAIL: four-zero predicate: "
            "node_a.changed=2,node_b.changed=2,node_c.changed=2; "
            "check leg predicted change: "
            "p0t0.node_a,p0t0.node_b,p0t0.node_c,"
            "p0t1.node_a,p0t1.node_b,p0t1.node_c",
        )

    def test_t09_stale_newer_file_ignored(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            fresh = shutil.copyfile(
                FIX / "converge-2-FRESH800-1.json",
                artifact_dir / "converge-2-FRESH800-1.json",
            )
            old = shutil.copyfile(
                FIX / "converge-2-OLD799-1.json",
                artifact_dir / "converge-2-OLD799-1.json",
            )
            os.utime(fresh, ns=(1_000_000_000, 1_000_000_000))
            os.utime(old, ns=(2_000_000_000, 2_000_000_000))
            rc, stdout, _ = self.run_gate(
                "inventory-main.json", artifact_dir, "converge-2", "FRESH800"
            )

        self.assertEqual(rc, 0)
        self.assertEqual(
            stdout,
            "PASS: converge-2-FRESH800-1.json; "
            "expected=node_a,node_b,node_c; excluded=controller_explicit",
        )

    def test_t10_expected_artifact_absent(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            shutil.copyfile(
                FIX / "converge-2-SPIKE100-1.json",
                artifact_dir / "converge-2-SPIKE100-1.json",
            )
            rc, stdout, _ = self.run_gate(
                "inventory-main.json", artifact_dir, "converge-2", "ABSENT801"
            )

        self.assertEqual(rc, 1)
        self.assertTrue(stdout.startswith("FAIL: artifact absent: "))
        self.assertTrue(stdout.endswith("/converge-2-ABSENT801-1.json"))

    def test_t11_pty_crlf_artifact_passes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir)
            artifact = artifact_dir / "converge-2-TTY900-1.json"
            lf_bytes = (FIX / artifact.name).read_bytes()
            artifact.write_bytes(lf_bytes.replace(b"\n", b"\r\n"))

            self.assertEqual(artifact.stat().st_size, 7122)
            self.assertEqual(
                digest(artifact),
                "2e13fb75c7de1dd3750c8903bd2c7cd61b64bdb9adf8bb8f8eef321f63f9e438",
            )
            rc, stdout, _ = self.run_gate(
                "inventory-main.json", artifact_dir, "converge-2", "TTY900"
            )

        self.assertEqual(rc, 0)
        self.assertEqual(
            stdout,
            "PASS: converge-2-TTY900-1.json; "
            "expected=node_a,node_b,node_c; excluded=controller_explicit",
        )

    def test_t12_group_declared_local_only_empty_set(self):
        rc, stdout, _ = self.run_gate(
            "inventory-group-local-only.json", FIX, "converge-2", "GROUPLOCAL501"
        )

        self.assertEqual(rc, 1)
        self.assertTrue(stdout.startswith("FAIL: empty expected host set"))
        self.assertEqual(stdout, "FAIL: empty expected host set")

    def test_t13_literal_localhost_excluded(self):
        rc, stdout, _ = self.run_gate(
            "inventory-localhost-present.json", FIX, "converge-2", "LOCALHOST110"
        )

        self.assertEqual(rc, 0)
        self.assertEqual(
            stdout,
            "PASS: converge-2-LOCALHOST110-1.json; "
            "expected=node_a,node_b,node_c; excluded=controller_explicit,localhost",
        )

    def test_t14_missing_counter_key_fails(self):
        rc, stdout, _ = self.run_gate(
            "inventory-main.json", FIX, "converge-2", "NOIGNORE120"
        )

        self.assertEqual(rc, 1)
        self.assertTrue(stdout.startswith("FAIL: four-zero predicate: "))
        self.assertEqual(
            stdout,
            "FAIL: four-zero predicate: node_a.ignored=missing",
        )

    def test_t15_unreadable_inventory_dump(self):
        rc, stdout, _ = self.run_gate(
            "inventory-truncated.json", FIX, "converge-2", "SPIKE100"
        )

        self.assertEqual(rc, 1)
        self.assertTrue(stdout.startswith("FAIL: unreadable inventory dump: "))

    def test_t16_usage_error_exits_two(self):
        completed = subprocess.run(
            ["python3", str(GATE_SCRIPT), "--leg", "converge-2"],
            capture_output=True,
            check=False,
            text=True,
        )

        self.assertEqual(completed.returncode, 2)
        self.assertEqual(completed.stdout, "")
        self.assertTrue(completed.stderr.startswith("usage:"))

    def test_t17_failures_counter_fails(self):
        rc, stdout, _ = self.run_gate(
            "inventory-main.json", FIX, "converge-2", "FAILURES130"
        )

        self.assertEqual(rc, 1)
        self.assertTrue(stdout.startswith("FAIL: four-zero predicate: "))
        self.assertEqual(
            stdout,
            "FAIL: four-zero predicate: node_a.failures=1",
        )

    def test_t18_check_leg_task_change_only(self):
        rc, stdout, _ = self.run_gate(
            "inventory-main.json", FIX, "check-diff", "TASKONLY710"
        )

        self.assertEqual(rc, 1)
        self.assertTrue(stdout.startswith("FAIL: check leg predicted change: "))
        self.assertEqual(
            stdout,
            "FAIL: check leg predicted change: "
            "p0t0.node_a,p0t0.node_b,p0t0.node_c,"
            "p0t1.node_a,p0t1.node_b,p0t1.node_c",
        )

    def test_t19_play_level_local_alias_judged_remote(self):
        rc, stdout, _ = self.run_gate(
            "inventory-play-only.json", FIX, "converge-2", "PLAYLOCAL502"
        )

        self.assertEqual(rc, 0)
        self.assertEqual(
            stdout,
            "PASS: converge-2-PLAYLOCAL502-1.json; "
            "expected=play_local_alias; excluded=-",
        )

    def test_t20_check_leg_excluded_host_change_fails(self):
        rc, stdout, _ = self.run_gate(
            "inventory-main.json", FIX, "check-diff", "CTRL720"
        )

        self.assertEqual(rc, 1)
        self.assertTrue(stdout.startswith("FAIL: check leg predicted change: "))
        self.assertEqual(
            stdout,
            "FAIL: check leg predicted change: p0t0.controller_explicit",
        )

    def test_t21_constructed_fixtures_match_committed_digests(self):
        names = (
            "converge-2-NONIDEM600-1.json",
            "inventory-localhost-present.json",
            "converge-2-LOCALHOST110-1.json",
            "converge-2-NOIGNORE120-1.json",
            "inventory-truncated.json",
            "converge-2-FAILURES130-1.json",
            "check-diff-TASKONLY710-1.json",
            "check-diff-CTRL720-1.json",
            "converge-2-DYNAMIC903-1.json",
            "check-diff-SECOND902-1.json",
            "converge-2-ATTEMPT904-2.json",
            "converge-2-ATTEMPT904-1.json",
            "converge-2-EXCLUDED905-1.json",
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir)
            completed = subprocess.run(
                ["python3", str(FIX / "build_constructed.py"), "--out", str(out)],
                capture_output=True,
                check=False,
                text=True,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            for name in names:
                with self.subTest(name=name):
                    self.assertEqual(digest(out / name), digest(FIX / name))

    def test_t22_runtime_added_host_is_judged(self):
        rc, stdout, _ = self.run_gate(
            "inventory-main.json", FIX, "converge-2", "DYNAMIC903"
        )

        self.assertEqual(rc, 1)
        self.assertTrue(stdout.startswith("FAIL: four-zero predicate: "))
        self.assertEqual(
            stdout,
            "FAIL: four-zero predicate: dynamic_added.changed=1",
        )

    def test_t23_second_play_check_results_scanned(self):
        rc, stdout, _ = self.run_gate(
            "inventory-main.json", FIX, "check-diff", "SECOND902"
        )

        self.assertEqual(rc, 1)
        self.assertTrue(stdout.startswith("FAIL: check leg predicted change: "))
        self.assertEqual(
            stdout,
            "FAIL: check leg predicted change: p1t0.node_a",
        )

    def test_t24_run_attempt_selects_its_own_artifact(self):
        rc, stdout, _ = self.run_gate(
            "inventory-main.json", FIX, "converge-2", "ATTEMPT904", "2"
        )

        self.assertEqual(rc, 0)
        self.assertEqual(
            stdout,
            "PASS: converge-2-ATTEMPT904-2.json; "
            "expected=node_a,node_b,node_c; excluded=controller_explicit",
        )

    def test_t25_excluded_host_counters_not_judged(self):
        rc, stdout, _ = self.run_gate(
            "inventory-main.json", FIX, "converge-2", "EXCLUDED905"
        )

        self.assertEqual(rc, 0)
        self.assertEqual(
            stdout,
            "PASS: converge-2-EXCLUDED905-1.json; "
            "expected=node_a,node_b,node_c; excluded=controller_explicit",
        )


if __name__ == "__main__":
    unittest.main()
