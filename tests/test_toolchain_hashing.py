import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from codex_eval_lab import oracle
from codex_eval_lab.util import LabError


class ToolchainHashingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.suite = Path(self.temp.name)
        self.first = self.executable("first", b"aaaa")
        self.second = self.executable("second", b"bbbb")

    def executable(self, name, data):
        path = self.suite / name
        path.write_bytes(data)
        path.chmod(0o755)
        return path

    def check(self, reference, grader):
        return oracle.toolchain(self.suite, {"reference_command": [str(reference)]},
                                {"execution": {"grader_command": [str(grader)]}})

    def test_same_executable_is_read_once_per_boundary(self):
        with mock.patch.object(oracle, "file_hash", wraps=oracle.file_hash) as hashed:
            first = self.check(self.first, self.first)
            self.assertEqual(hashed.call_count, 1)
            self.assertEqual(self.check(self.first, self.first), first)
            self.assertEqual(hashed.call_count, 2)
        self.assertEqual(first["executables_sha256"],
                         {str(self.first.resolve()): hashlib.sha256(b"aaaa").hexdigest()})

    def test_distinct_role_executables_keep_independent_hashes(self):
        with mock.patch.object(oracle, "file_hash", wraps=oracle.file_hash) as hashed:
            actual = self.check(self.first, self.second)
            self.assertEqual(hashed.call_count, 2)
        self.assertEqual(actual["executables_sha256"], {
            str(self.first.resolve()): hashlib.sha256(b"aaaa").hexdigest(),
            str(self.second.resolve()): hashlib.sha256(b"bbbb").hexdigest()})

    def test_same_size_restored_mtime_change_is_freshly_hashed(self):
        before = self.check(self.first, self.first)
        stat = self.first.stat()
        self.first.write_bytes(b"zzzz")
        os.utime(self.first, ns=(stat.st_atime_ns, stat.st_mtime_ns))
        after = self.check(self.first, self.first)
        self.assertNotEqual(before, after)
        self.assertEqual(after["executables_sha256"][str(self.first.resolve())],
                         hashlib.sha256(b"zzzz").hexdigest())

    def test_aliases_resolve_each_time_and_retargeting_changes_identity(self):
        alias = self.suite / "alias"
        alias.symlink_to(self.first)
        with mock.patch.object(oracle, "file_hash", wraps=oracle.file_hash) as hashed:
            before = self.check(self.first, alias)
            self.assertEqual(hashed.call_count, 1)
        alias.unlink()
        alias.symlink_to(self.second)
        after = self.check(self.first, alias)
        self.assertNotEqual(before, after)
        self.assertEqual(set(after["executables_sha256"]),
                         {str(self.first.resolve()), str(self.second.resolve())})

    def test_suite_launcher_preserves_relative_identity_and_freshness(self):
        with mock.patch.object(oracle, "file_hash", wraps=oracle.file_hash) as hashed:
            before = self.check("{suite}/first", "{suite}/first")
            self.assertEqual(hashed.call_count, 1)
        self.assertEqual(set(before["executables_sha256"]), {"{suite}/first"})
        self.first.write_bytes(b"zzzz")
        self.assertNotEqual(before, self.check("{suite}/first", "{suite}/first"))

    def test_missing_second_role_is_not_hidden_by_first_hash(self):
        with self.assertRaisesRegex(LabError, "unavailable"):
            self.check(self.first, self.suite / "missing")


if __name__ == "__main__":
    unittest.main()
