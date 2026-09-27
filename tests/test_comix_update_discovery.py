import hashlib
import json
import unittest
from pathlib import Path

from scripts import update_sources as updater


ROOT = Path(__file__).resolve().parents[1]


class ComixUpdateDiscoveryTests(unittest.TestCase):
    def test_dedicated_feed_upgrades_installed_v129(self):
        normal = json.loads((ROOT / "index.min.json").read_text(encoding="utf-8"))
        dedicated = json.loads((ROOT / "comix-v130" / "index.min.json").read_text(encoding="utf-8"))

        self.assertFalse(any(item["id"] == "en.comix" for item in normal["sources"]))
        comix = next(item for item in dedicated["sources"] if item["id"] == "en.comix")
        self.assertGreater(comix["version"], 129)

        package = (ROOT / "comix-v130" / comix["downloadURL"]).read_bytes()
        info, _ = updater.read_package(
            package,
            "dedicated Comix feed",
            expected_id="en.comix",
            expected_version=comix["version"],
        )
        inventory = json.loads((ROOT / "comix-v130" / "inventory.json").read_text(encoding="utf-8"))
        self.assertEqual(info["version"], 130)
        self.assertEqual(hashlib.sha256(package).hexdigest(), inventory["sources"][0]["sha256"])


if __name__ == "__main__":
    unittest.main()
