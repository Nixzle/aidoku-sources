#!/usr/bin/env python3
"""Run bounded chapter-level HTTP smoke checks for owner-critical Aidoku sources."""

from __future__ import annotations

import argparse
import ipaddress
import json
import socket
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
USER_AGENT = "Nixzle-Aidoku-Critical-Smoke/1.0"
MAX_BODY = 2 * 1024 * 1024
PROTECTED = {401, 403, 429, 451}


def public_https(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("smoke URL must be a credential-free https URL")
    addresses = {ipaddress.ip_address(item[4][0]) for item in socket.getaddrinfo(parsed.hostname, 443)}
    if not addresses or not all(address.is_global for address in addresses):
        raise ValueError("smoke URL host must resolve only to public addresses")
    return parsed.hostname.casefold()


def fetch(url: str, timeout: int = 20) -> tuple[int, bytes]:
    public_https(url)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = int(getattr(response, "status", response.getcode()))
            body = response.read(MAX_BODY + 1)
    except urllib.error.HTTPError as error:
        status = error.code
        body = error.read(MAX_BODY + 1)
    if len(body) > MAX_BODY:
        raise RuntimeError("smoke response exceeded size limit")
    return status, body


def run(policy: dict) -> dict:
    tests = policy.get("criticalSmokeTests", {})
    required = set(policy.get("requiredMaintainedSources", []))
    if not isinstance(tests, dict) or not required <= set(tests):
        missing = sorted(required - set(tests) if isinstance(tests, dict) else required)
        raise RuntimeError(f"missing critical smoke definitions: {missing}")
    results = []
    failed = False
    for source_id in sorted(required):
        spec = tests[source_id]
        try:
            status, body = fetch(str(spec["url"]))
        except (TimeoutError, socket.timeout) as error:
            results.append({
                "id": source_id,
                "level": spec.get("level", "chapter"),
                "url": spec["url"],
                "result": "inconclusive",
                "httpStatus": None,
                "detail": f"network timeout: {error}",
            })
            continue
        except urllib.error.URLError as error:
            reason = getattr(error, "reason", error)
            if isinstance(reason, socket.gaierror):
                results.append({
                    "id": source_id,
                    "level": spec.get("level", "chapter"),
                    "url": spec["url"],
                    "result": "fail",
                    "httpStatus": None,
                    "detail": f"DNS failure: {reason}",
                })
                failed = True
            else:
                results.append({
                    "id": source_id,
                    "level": spec.get("level", "chapter"),
                    "url": spec["url"],
                    "result": "inconclusive",
                    "httpStatus": None,
                    "detail": f"network error: {reason}",
                })
            continue
        text = body.decode("utf-8", errors="replace")
        if 200 <= status < 400:
            missing = [marker for marker in spec.get("requiredSubstrings", []) if marker not in text]
            result = "pass" if not missing else "fail"
            detail = None if not missing else "missing expected page markers: " + ", ".join(missing)
        elif status in PROTECTED and spec.get("allowProtected", False):
            result = "protected"
            detail = f"HTTP {status}; endpoint is reachable but functional parsing is unverified"
        else:
            result = "fail"
            detail = f"HTTP {status}"
        failed = failed or result == "fail"
        results.append({
            "id": source_id,
            "level": spec.get("level", "chapter"),
            "url": spec["url"],
            "result": result,
            "httpStatus": status,
            **({"detail": detail} if detail else {}),
        })
    return {
        "checkedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "result": "fail" if failed else (
            "degraded"
            if any(x["result"] in {"protected", "inconclusive"} for x in results)
            else "pass"
        ),
        "sources": results,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", type=Path, default=ROOT / "config" / "source_policy.json")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)
    policy = json.loads(args.policy.read_text(encoding="utf-8-sig"))
    report = run(policy)
    if args.report:
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 1 if report["result"] == "fail" else 0


if __name__ == "__main__":
    sys.exit(main())
