from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import functional_smoke as smoke
from scripts import report_automation as reporting
from scripts import source_health


def passed_case():
    return {'id': 'en.example', 'status': 'passed', 'stage': 'complete',
            'runtimeLoaded': True, 'searchCount': 1, 'chapterCount': 1,
            'pageCount': 1, 'firstPageBytes': 128}


class FunctionalStatusTests(unittest.TestCase):
    def test_empty_unknown_and_incomplete_passes_fail(self):
        for results in [[], [{}], [{'status': 'passed'}], [{'status': 'made_up'}],
                        [{**passed_case(), 'pageCount': 0}], [{**passed_case(), 'chapterCount': True}]]:
            with self.subTest(results=results):
                self.assertEqual(smoke.overall_status(results), 'failed')

    def test_actual_reader_pass_is_required(self):
        self.assertEqual(smoke.overall_status([passed_case()]), 'passed')
        self.assertEqual(smoke.overall_status([passed_case(), {'status': 'blocked'}]), 'blocked')
        self.assertEqual(smoke.overall_status([{'status': 'blocked'}, {'status': 'inconclusive'}]), 'inconclusive')
        self.assertEqual(smoke.overall_status([{'status': 'failed'}, {'status': 'blocked'}]), 'failed')

    def test_script_exports_blocked_acceptance_despite_successful_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / 'job-output'
            summary = root / 'job-summary'
            case = {'id': 'en.example', 'status': 'blocked', 'stage': 'search'}
            with mock.patch.object(smoke, 'CASES', {'en.example': 'example'}), \
                 mock.patch.object(smoke, 'run_case', return_value=case), \
                 mock.patch('sys.argv', ['functional_smoke.py', '--runner', 'unused', '--output', str(root / 'results')]), \
                 mock.patch.dict(os.environ, {'GITHUB_OUTPUT': str(output), 'GITHUB_STEP_SUMMARY': str(summary)}, clear=True):
                self.assertEqual(smoke.main(), 0)
            self.assertIn('acceptance=blocked', output.read_text())
            self.assertIn('unverified_sources=en.example', output.read_text())
            self.assertEqual(json.loads((root / 'results/summary.json').read_text())['status'], 'blocked')
            self.assertIn('not a reader pass', summary.read_text())

    def test_workflow_forwards_actual_status_and_does_not_rebuild_main(self):
        workflow = Path(__file__).resolve().parents[1] / '.github/workflows/functional-smoke.yml'
        text = workflow.read_text()
        self.assertIn('FUNCTIONAL_STATUS: ${{ needs.smoke.outputs.acceptance }}', text)
        self.assertIn('acceptance: ${{ steps.functional.outputs.acceptance }}', text)
        self.assertIn("Build candidate catalog\n        if: github.event_name == 'pull_request'", text)


class FunctionalIncidentTests(unittest.TestCase):
    def call_report(self, acceptance, execution='success'):
        marker, _ = reporting.incident_identity('functional')
        incident = {'number': 7, 'body': marker, 'user': {'login': 'github-actions[bot]'}}
        api = mock.Mock(side_effect=lambda method, path, body=None: [incident] if method == 'GET' else {})
        env = {'INCIDENT_KIND': 'functional', 'UPDATE_RESULT': execution,
               'FUNCTIONAL_STATUS': acceptance, 'UNVERIFIED_SOURCES': 'en.comix',
               'GITHUB_REPOSITORY': 'Nixzle/aidoku-sources', 'GITHUB_RUN_ID': '123'}
        with mock.patch.object(reporting, 'api', api), mock.patch.dict(os.environ, env, clear=True):
            reporting.main()
        return api.call_args_list

    def test_blocked_inconclusive_missing_and_failed_never_close_incident(self):
        for status in ['blocked', 'inconclusive', '', 'unknown', 'failed']:
            with self.subTest(status=status):
                calls = self.call_report(status)
                patches = [call.args[2] for call in calls if call.args[0] == 'PATCH']
                self.assertTrue(patches)
                self.assertTrue(all(body.get('state') != 'closed' for body in patches))
                self.assertIn('Unverified source IDs: en.comix', patches[0]['body'])

    def test_explicit_pass_closes_incident(self):
        calls = self.call_report('passed')
        self.assertTrue(any(call.args[0] == 'PATCH' and call.args[2].get('state') == 'closed' for call in calls))

    def test_failed_workflow_cannot_close_even_with_passed_result(self):
        calls = self.call_report('passed', execution='failure')
        self.assertFalse(any(call.args[0] == 'PATCH' and call.args[2].get('state') == 'closed' for call in calls))


class RequiredSeverityTests(unittest.TestCase):
    def test_answering_http_server_error_is_still_critical(self):
        self.assertEqual(source_health.required_severity(source_health.classify_http(503)), 'critical')

    def test_protection_is_degraded_not_a_dead_site(self):
        self.assertEqual(source_health.required_severity(source_health.classify_http(403)), 'degraded')

    def test_inconclusive_is_unknown_not_healthy(self):
        self.assertEqual(source_health.required_severity({'conclusive': False, 'reachable': False}), 'unknown')


if __name__ == '__main__':
    unittest.main()
