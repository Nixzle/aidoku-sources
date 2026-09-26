import copy
import hashlib
import json
from pathlib import Path
import socket
import tempfile
import unittest
from unittest import mock
import urllib.error

from scripts import functional_smoke, source_health as health, update_sources as updater
from scripts import validate_catalog as validator, verify_public as public, report_automation as reporter


class StructuredHealthTests(unittest.TestCase):
    def test_distinct_http_states(self):
        for code,kind in [(200,"ok"),(401,"auth_required"),(403,"forbidden"),(429,"rate_limited"),(451,"restricted"),(500,"server_error"),(404,"http_error")]:
            with self.subTest(code=code):
                result=health.classify_http(code)
                self.assertEqual(result["classification"],kind)
                self.assertEqual(result["functional"],"not_tested")
        self.assertEqual(health.classify_http(403,{"cf-mitigated":"challenge"})["classification"],"cloudflare_protected")

    def test_dns_failures_are_not_all_inconclusive(self):
        self.assertTrue(health.classify_error(socket.gaierror(socket.EAI_NONAME,"not found"))["conclusive"])
        self.assertFalse(health.classify_error(socket.gaierror(socket.EAI_AGAIN,"try again"))["conclusive"])
        self.assertEqual(health.classify_error(TimeoutError())["classification"],"timeout")

    def test_rejects_private_targets(self):
        opener=mock.Mock()
        with mock.patch.object(socket,"getaddrinfo",return_value=[(socket.AF_INET,1,6,"",("127.0.0.1",443))]):
            result=health.probe("https://example.com/",opener=opener,attempts=1)
        self.assertEqual(result["classification"],"unsafe_target")
        opener.assert_not_called()

    def test_conclusive_failure_counts_toward_coverage(self):
        result=health.sweep_quality({"en.a":health.observation("dns_failure"),"en.b":health.observation("dns_failure")},[health.classify_http(200)],0.5)
        self.assertTrue(result["accepted"])
        self.assertEqual(result["conclusiveRatio"],1)

    def test_network_failure_does_not_quarantine_everything(self):
        result=health.sweep_quality({"en.a":health.observation("timeout")},[health.observation("timeout")],0.5)
        self.assertFalse(result["accepted"])

    def test_probe_exceptions_remain_in_denominator(self):
        result=health.sweep_quality({"en.a":health.observation("dns_failure"),"en.b":health.observation("probe_error",conclusive=False),"en.c":health.observation("probe_error",conclusive=False)},[health.classify_http(200)],0.5)
        self.assertEqual(result["attempted"],3)
        self.assertFalse(result["accepted"])

    def test_empty_sweep_cannot_pass(self):
        self.assertFalse(health.sweep_quality({},[health.classify_http(200)],0.5)["accepted"])

    def test_future_exception_is_an_explicit_observation(self):
        with mock.patch.object(health,"probe",side_effect=ValueError("bad probe")):
            result=updater.observe_source_health([{"id":"en.test","baseURL":"https://example.com"}],{})
        self.assertIn("en.test",result)
        self.assertFalse(result["en.test"]["conclusive"])


class StateTransitionTests(unittest.TestCase):
    def state(self):
        state={"version":1,"sources":{}}
        for day in ("2026-09-20","2026-09-21","2026-09-22"):
            state,_=health.transition(state,{"en.test":False},observation_date=day)
        return state

    def test_intervening_failure_resets_recovery_streak(self):
        state=self.state()
        for day,value in [("2026-09-23",True),("2026-09-24",False),("2026-09-25",True)]:
            state,quarantine=health.transition(state,{"en.test":value},observation_date=day)
        self.assertIn("en.test",quarantine)
        self.assertEqual(state["sources"]["en.test"]["consecutiveSuccesses"],1)
        state,quarantine=health.transition(state,{"en.test":True},observation_date="2026-09-26")
        self.assertNotIn("en.test",quarantine)

    def test_protection_does_not_prove_recovery(self):
        state=self.state()
        for day in ("2026-09-23","2026-09-24"):
            state,quarantine=health.transition(state,{"en.test":health.classify_http(403)},observation_date=day)
        self.assertIn("en.test",quarantine)
        self.assertEqual(state["sources"]["en.test"]["consecutiveSuccesses"],0)

    def test_required_failure_is_high_severity_not_silent_health(self):
        state,quarantine=health.transition(self.state(),{"en.test":False},observation_date="2026-09-23",required_ids=["en.test"])
        self.assertNotIn("en.test",quarantine)
        self.assertEqual(state["sources"]["en.test"]["severity"],"high")
        self.assertEqual(state["sources"]["en.test"]["status"],"failing")

    def test_distinct_probe_and_state_change_times(self):
        state=self.state()
        before=state["probes"]["en.test"]["lastStateChangeAt"]
        state,_=health.transition(state,{"en.test":False},observation_date="2026-09-23")
        self.assertEqual(state["probes"]["en.test"]["lastStateChangeAt"],before)
        self.assertEqual(state["probes"]["en.test"]["lastProbeAt"],"2026-09-23T00:00:00+00:00")

    def test_inconclusive_sweep_preserves_counters_and_input(self):
        original=self.state(); snapshot=copy.deepcopy(original)
        result,_=health.transition(original,{"en.test":True},observation_date="2026-09-23",accepted=False)
        self.assertEqual(result["sources"],snapshot["sources"])
        self.assertEqual(original,snapshot)
        self.assertEqual(result["lastHealthSweepDate"],"2026-09-23")

    def test_all_healthy_runs_have_a_daily_dedup_marker(self):
        today=health.utc_now()[:10]
        state,_=health.transition({"version":2,"sources":{}},{"en.test":True},observation_date=today)
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"state.json"; path.write_text(json.dumps(state))
            with mock.patch.object(updater,"observe_source_health") as observe:
                _,reused=updater.refresh_health_state([],{},path)
        observe.assert_not_called(); self.assertEqual(reused,state)


class ProvenanceTests(unittest.TestCase):
    def detail(self):
        sha="a"*40
        return {"provenanceURL":f"https://github.com/Owner/Repo/blob/{sha}/overrides/en.test-v1.aix"}

    def test_blob_provenance_becomes_pinned_raw_download(self):
        result=updater.override_provenance(self.detail())
        self.assertEqual(result["sourceCommit"],"a"*40)
        self.assertIn("raw.githubusercontent.com/Owner/Repo/",result["upstreamPackageURL"])
        validator.validate_provenance(result,"test")

    def test_unpinned_override_rejected(self):
        detail=self.detail(); detail["provenanceURL"]=detail["provenanceURL"].replace("a"*40,"main")
        with self.assertRaises(ValueError): updater.override_provenance(detail)

    def test_contradictory_override_download_rejected(self):
        detail=self.detail(); detail["downloadURL"]="https://evil.example/file.aix"
        with self.assertRaises(ValueError): updater.override_provenance(detail)

    def test_html_page_is_never_a_download(self):
        with self.assertRaises(validator.ValidationFailure): validator.validate_provenance({"upstreamPackageURL":self.detail()["provenanceURL"]},"test")

    def test_partial_provenance_and_changed_commit_rejected(self):
        good=updater.override_provenance(self.detail())
        for key in ("sourceCommit","sourcePath","provenanceURL","packageRepository"):
            bad=dict(good); del bad[key]
            with self.assertRaises(validator.ValidationFailure): validator.validate_provenance(bad,"test")
        good["sourceCommit"]="b"*40
        with self.assertRaises(validator.ValidationFailure): validator.validate_provenance(good,"test")


class PublicAcceptanceTests(unittest.TestCase):
    def test_exact_manifest_match_required(self):
        self.assertEqual(public.check_manifests({"a":b"data"},{"a":b"data"})[0]["sha256"],hashlib.sha256(b"data").hexdigest())
        for received in ({},{"a":b"different"}):
            with self.assertRaises(ValueError): public.check_manifests({"a":b"data"},received)

    def test_unsafe_asset_paths_rejected(self):
        for value in ["../x","/x","https://evil.example/x","%2e%2e/x","a\\b","sources//x","a?b","a#b"]:
            with self.subTest(value=value),self.assertRaises(ValueError): public.relative_path(value)
        self.assertEqual(public.relative_path("sources/en.test-v1.aix"),"sources/en.test-v1.aix")

    def test_duplicate_catalog_sources_rejected(self):
        entry={"id":"en.test","version":1,"downloadURL":"sources/en.test-v1.aix","iconURL":"icons/en.test-v1.png"}
        item={"id":"en.test","version":1,"file":entry["downloadURL"],"sha256":"a"*64}
        with self.assertRaises(ValueError): public.catalog_assets(json.dumps({"sources":[entry,entry]}).encode(),json.dumps({"sourceCount":2,"sources":[item,item]}).encode())

    def test_package_hash_mismatch_fails_before_parser(self):
        with self.assertRaisesRegex(ValueError,"hash mismatch"):
            public.verify_package({"id":"en.test","sha256":"0"*64},b"not a package",b"icon")

    def test_git_ref_must_be_immutable(self):
        with self.assertRaises(ValueError): public.git_bytes(Path('.'),"main","index.json")


class FunctionalEvidenceTests(unittest.TestCase):
    def test_zero_or_partial_work_cannot_pass(self):
        good={"status":"passed","stage":"complete","runtimeLoaded":True,"searchCount":1,"chapterCount":1,"pageCount":1,"firstPageBytes":100}
        self.assertTrue(functional_smoke.valid_pass(good))
        for key in good:
            bad=dict(good); del bad[key]
            self.assertFalse(functional_smoke.valid_pass(bad),key)
        good["status"]="blocked"; self.assertFalse(functional_smoke.valid_pass(good))

    def test_settings_defaults_are_applied_without_login_data(self):
        result=functional_smoke.settings_defaults([{"type":"group","items":[{"key":"quality","default":"large"},{"key":"verify","type":"login"},{"key":"enabled","default":True}]}])
        self.assertEqual(result,{"quality":"large","enabled":True})

    def test_incident_namespaces_do_not_close_other_incidents(self):
        other={"number":7,"user":{"login":"github-actions[bot]"},"body":reporter.MARKER}
        with mock.patch.dict(reporter.os.environ,{"INCIDENT_KIND":"public","UPDATE_RESULT":"success","GITHUB_REPOSITORY":"Nixzle/aidoku-sources","GITHUB_RUN_ID":"1"}),mock.patch.object(reporter,"api",return_value=[other]) as api:
            reporter.main()
        self.assertEqual(api.call_count,1)


if __name__ == "__main__": unittest.main()
