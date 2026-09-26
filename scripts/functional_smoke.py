#!/usr/bin/env python3
"""Run bounded functional checks on the exact catalog WASM, preserving blocked results."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
from datetime import datetime, timezone
import subprocess
import sys
import tempfile
import zipfile

try:
    from scripts import update_sources as updater
except ModuleNotFoundError:
    import update_sources as updater

def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


CASES = {"en.asurascans": "solo", "en.mangadistrict": "solo", "en.readcomicsonline": "batman"}


def settings_defaults(items) -> dict:
    defaults = {}
    if isinstance(items, list):
        for item in items:
            defaults.update(settings_defaults(item))
    elif isinstance(items, dict):
        if isinstance(items.get("key"), str) and "default" in items:
            defaults[items["key"]] = items["default"]
        defaults.update(settings_defaults(items.get("items", [])))
    return defaults


def valid_pass(report: dict) -> bool:
    # An empty test run or mere WASM instantiation is never sufficient.
    return (report.get("status") == "passed" and report.get("stage") == "complete"
            and report.get("runtimeLoaded") is True
            and all(type(report.get(key)) is int and report[key] > 0
                    for key in ("searchCount", "chapterCount", "pageCount"))
            and (report.get("firstPageBytes", 0) > 64 or report.get("firstPageTextLength", 0) > 0))


def overall_status(results: list[dict]) -> str:
    if not results or any(item.get("status") not in {"passed", "failed", "blocked", "inconclusive"} for item in results):
        return "failed"
    if any(item.get("status") == "failed" or (item.get("status") == "passed" and not valid_pass(item)) for item in results):
        return "failed"
    if all(valid_pass(item) for item in results):
        return "passed"
    if any(item.get("status") == "inconclusive" for item in results):
        return "inconclusive"
    return "blocked"


def run_case(root: Path, runner: Path, source_id: str, query: str, output: Path) -> dict:
    inventory = json.loads((root / "inventory.json").read_text(encoding="utf-8-sig"))
    item = next((entry for entry in inventory["sources"] if entry["id"] == source_id), None)
    if item is None:
        return {"id": source_id, "status": "failed", "error": "required source missing"}
    package = updater._safe_local_reference(root, item["file"]).read_bytes()
    digest = hashlib.sha256(package).hexdigest()
    if digest != item["sha256"]:
        raise ValueError("Source package does not match catalog checksum")
    updater.read_package(package, source_id, expected_id=source_id, expected_version=item["version"])
    with tempfile.TemporaryDirectory(prefix="aidoku-smoke-") as name:
        temp = Path(name)
        with zipfile.ZipFile(updater.io.BytesIO(package)) as archive:
            members = {member.casefold(): member for member in archive.namelist()}
            wasm = archive.read(members["payload/main.wasm"])
            settings = json.loads(archive.read(members["payload/settings.json"])) if "payload/settings.json" in members else []
        wasm_file = temp / "main.wasm"
        wasm_file.write_bytes(wasm)
        settings_file = temp / "settings.json"
        settings_file.write_text(json.dumps(settings_defaults(settings)), encoding="utf-8")
        result_file = temp / "result.json"
        try:
            # Only the reviewed runner executable receives arguments. No shell and no credentials.
            env = {key: value for key, value in os.environ.items()
                   if not any(term in key.upper() for term in ("TOKEN", "SECRET", "PASSWORD", "CREDENTIAL"))}
            process = subprocess.run([str(runner), str(wasm_file), query, str(settings_file), str(result_file)],
                                     capture_output=True, timeout=150, env=env, check=False)
            (output / f"{source_id}.stdout.log").write_bytes(process.stdout)
            (output / f"{source_id}.stderr.log").write_bytes(process.stderr)
            report = json.loads(result_file.read_text()) if result_file.exists() else {
                "status": "failed", "error": "runner did not produce a result", "exitCode": process.returncode}
            report["exitCode"] = process.returncode
            if process.returncode != 0 or not valid_pass(report):
                report["status"] = "failed"
                report.setdefault("error", "incomplete functional acceptance")
                network = report.get("network", [])
                if network and network[-1].get("status") in (401, 403, 429, 451):
                    report["status"] = "blocked"
                    report["limitation"] = "Protected HTTP response observed. Headless run cannot establish in-app usability."
        except subprocess.TimeoutExpired as error:
            (output / f"{source_id}.stdout.log").write_bytes(error.stdout or b"")
            (output / f"{source_id}.stderr.log").write_bytes(error.stderr or b"")
            report = {"status": "inconclusive", "error": "150-second per-source timeout; no protection diagnosis established"}
        report.update(id=source_id, version=item["version"], packageSha256=digest,
                      wasmSha256=hashlib.sha256(wasm).hexdigest(), checkedAt=utc_now())
        return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runner", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, default=Path("acceptance/functional"))
    parser.add_argument("--source", action="append", choices=sorted(CASES))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    runner = args.runner.resolve()
    results = []
    for source_id, query in CASES.items():
        if args.source and source_id not in args.source:
            continue
        try:
            result = run_case(args.root, runner, source_id, query, args.output)
        except Exception as error:
            result = {"id": source_id, "status": "failed", "error": str(error)[:1000]}
        (args.output / f"{source_id}.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
        results.append(result)
        print(source_id, result["status"], result.get("stage", "setup"), result.get("error", ""))
    overall = overall_status(results)
    report = {"schema":"AIDOKU_FUNCTIONAL_SMOKE_V1", "checkedAt":utc_now(),
              "status":overall,
              "scope":"Exact published package WASM, headless Aidoku donor runtime, one sample per critical source. Not iOS rendering or an unidentified user chapter.",
              "catalogRoot":str(args.root), "cases":results}
    (args.output / "summary.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    output_path = os.environ.get("GITHUB_OUTPUT")
    if output_path:
        with open(output_path, "a", encoding="utf-8") as handle:
            handle.write(f"acceptance={overall}\n")
            unverified = ", ".join(item["id"] for item in results if item.get("status") != "passed")
            handle.write(f"unverified_sources={unverified}\n")
    step_summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if step_summary:
        with open(step_summary, "a", encoding="utf-8") as handle:
            handle.write("## Functional source acceptance\n\n")
            for item in results:
                handle.write(f"- {item['id']}: **{item['status']}** at {item.get('stage', 'setup')}\n")
            handle.write("\nA green job with blocked or inconclusive sources is not a reader pass.\n")
    if overall == "blocked":
        blocked = ", ".join(item["id"] for item in results if item.get("status") == "blocked")
        print(f"::warning::Functional acceptance blocked by site protection: {blocked}")
    return 1 if overall == "failed" else 0


if __name__ == "__main__":
    sys.exit(main())
