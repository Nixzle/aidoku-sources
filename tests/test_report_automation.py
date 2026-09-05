import os
import unittest
from unittest.mock import patch
from scripts import report_automation as report


class ReportingTests(unittest.TestCase):
    def run_report(self, result, issues):
        with patch.dict(os.environ, {"GITHUB_REPOSITORY": "Nixzle/aidoku-sources",
                                    "GITHUB_RUN_ID": "42", "UPDATE_RESULT": result}):
            with patch.object(report, "api", side_effect=[issues, {}]) as api:
                report.main()
                return api.call_args_list

    def test_failure_opens_incident(self):
        calls = self.run_report("failure", [])
        self.assertEqual(calls[-1].args[:2], ("POST", "/issues"))
        self.assertIn(report.MARKER, calls[-1].args[2]["body"])

    def test_recovery_only_closes_bot_owned_incident(self):
        issues = [{"number": 1, "body": report.MARKER, "user": {"login": "github-actions[bot]"}},
                  {"number": 2, "body": report.MARKER, "user": {"login": "Nixzle"}}]
        calls = self.run_report("success", issues)
        self.assertEqual(calls[-1].args[:2], ("PATCH", "/issues/1"))
        self.assertEqual(calls[-1].args[2]["state"], "closed")

    def test_failure_updates_existing_without_duplicate(self):
        calls = self.run_report("failure", [{"number": 1, "body": report.MARKER,
                                            "user": {"login": "github-actions[bot]"}}])
        self.assertEqual(calls[-1].args[:2], ("PATCH", "/issues/1"))

    def test_healthy_run_without_incident_writes_nothing(self):
        self.assertEqual(len(self.run_report("success", [])), 1)
