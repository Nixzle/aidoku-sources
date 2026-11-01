import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class ComixOwnerDeviceGate(unittest.TestCase):
    def test_failed_v140_is_not_promoted_or_misreported(self):
        policy = json.loads((ROOT / "config/source_policy.json").read_text(encoding="utf-8"))
        status = json.loads((ROOT / "status.json").read_text(encoding="utf-8"))
        catalog = json.loads((ROOT / "index.min.json").read_text(encoding="utf-8"))
        reason = policy["quarantinedSources"]["en.comix"]["reason"]
        self.assertIn("v140", reason)
        self.assertIn("failed", reason.lower())
        self.assertNotIn("en.comix", {source["id"] for source in catalog["sources"]})
        actual = next(item for item in status["manualQuarantine"] if item["id"] == "en.comix")
        self.assertEqual(actual["reason"], reason)

    def test_recovery_is_publisher_hosted_without_repacking(self):
        guide = (ROOT / "docs/COMIX_DEVICE_RECOVERY.md").read_text(encoding="utf-8")
        self.assertIn("https://smexhy.github.io/yomu-aidoku-sources/comix/index.min.json", guide)
        self.assertIn("https://smexhy.github.io/yomu-aidoku-sources/sources/en.comix-v138.aix", guide)
        self.assertIn("do not", guide.lower())
        self.assertIn("backup", guide.lower())
