"""Structured website observations. Reachability is not parser or reader acceptance."""
from __future__ import annotations

import copy
import ipaddress
import socket
import ssl
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from urllib.parse import urlsplit

PROTECTED = {401: "auth_required", 403: "forbidden", 429: "rate_limited", 451: "restricted"}
FAILURES = {"dns_failure", "timeout", "connection_failure", "tls_failure", "server_error", "http_error"}
CONTROL_URLS = ("https://www.python.org/", "https://github.com/")


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def observation(kind: str, *, code=None, conclusive=True, reachable=False) -> dict:
    return {"classification": kind, "httpStatus": code, "conclusive": conclusive,
            "reachable": reachable, "functional": "not_tested"}


def classify_http(code: int, headers=None) -> dict:
    headers = headers or {}
    # Do not label every 403 as Cloudflare, or every Cloudflare response as a challenge.
    challenge = str(headers.get("cf-mitigated", "")).lower() == "challenge"
    if challenge:
        return observation("cloudflare_protected", code=code, reachable=True)
    if code in PROTECTED:
        return observation(PROTECTED[code], code=code, reachable=True)
    if 200 <= code < 300:
        return observation("ok", code=code, reachable=True)
    if code >= 500:
        return observation("server_error", code=code, reachable=True)
    return observation("http_error", code=code, reachable=True)


def classify_error(error: Exception) -> dict:
    reason = error.reason if isinstance(error, urllib.error.URLError) else error
    if isinstance(reason, socket.gaierror):
        nx = {socket.EAI_NONAME, getattr(socket, "EAI_NODATA", socket.EAI_NONAME), 11001}
        return observation("dns_failure" if reason.errno in nx else "dns_inconclusive",
                           conclusive=reason.errno in nx)
    if isinstance(reason, (TimeoutError, socket.timeout)):
        return observation("timeout")
    if isinstance(reason, ssl.SSLError):
        return observation("tls_failure")
    if isinstance(reason, (ConnectionError, OSError)):
        return observation("connection_failure")
    return observation("probe_error", conclusive=False)


def probe(url: str, *, opener, attempts: int = 2, timeout: int = 12,
          user_agent: str = "Nixzle-Aidoku-Health/3.0") -> dict:
    parsed = urlsplit(url)
    host = (parsed.hostname or "").casefold().rstrip(".")
    if (parsed.scheme != "https" or not host or parsed.username or parsed.password
            or parsed.port not in (None, 443) or len(url) > 2048):
        return observation("unsafe_target", conclusive=False)
    if host == "localhost" or host.endswith((".local", ".localhost", ".internal")):
        return observation("unsafe_target", conclusive=False)
    result = observation("probe_error", conclusive=False)
    for attempt in range(max(1, min(attempts, 3))):
        try:
            addresses = {ipaddress.ip_address(item[4][0].split("%", 1)[0])
                         for item in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)}
            if not addresses or not all(address.is_global for address in addresses):
                return observation("unsafe_target", conclusive=False)
            request = urllib.request.Request(url, headers={"User-Agent": user_agent})
            with opener(request, timeout=timeout, allowed_hosts={host}, require_public=True) as response:
                code = int(response.status)
                response.read(1)
                return classify_http(code, response.headers)
        except urllib.error.HTTPError as error:
            result = classify_http(error.code, error.headers)
            error.close()
            if error.code < 500:
                return result
        except (urllib.error.URLError, OSError, TimeoutError) as error:
            result = classify_error(error)
        except ValueError:
            # A blocked redirect/configuration is not evidence that a source is dead.
            return observation("redirect_blocked", conclusive=False)
        if attempt + 1 < max(1, min(attempts, 3)):
            time.sleep(0.25 * (2 ** attempt))
    return result


def normalize(value) -> dict:
    # v1 callers and persisted fixtures remain readable during migration.
    if isinstance(value, bool):
        return observation("ok" if value else "connection_failure", reachable=value)
    if not isinstance(value, dict) or not isinstance(value.get("classification"), str):
        return observation("probe_error", conclusive=False)
    return dict(value)


def sweep_quality(observations: dict, controls: list[dict], minimum_ratio: float) -> dict:
    values = [normalize(value) for value in observations.values()]
    count = len(values)
    conclusive = sum(value.get("conclusive") is True for value in values)
    # Source failures count as evidence. Only inconclusive probes reduce coverage.
    coverage = conclusive / count if count else 0.0
    network_ok = any(value.get("reachable") is True for value in values + controls)
    accepted = bool(count and coverage >= minimum_ratio and network_ok)
    return {"attempted": count, "conclusive": conclusive, "conclusiveRatio": coverage,
            "networkObserved": network_ok, "accepted": accepted,
            "reason": "accepted" if accepted else "empty_or_inconclusive_or_network_unverified"}


def transition(state: dict, observations: dict, *, observation_date: str,
               checked_at: str | None = None, failure_threshold: int = 3,
               recovery_threshold: int = 2, required_ids=(), accepted=True) -> tuple[dict, set[str]]:
    if failure_threshold < 2 or recovery_threshold < 2:
        raise ValueError("Health thresholds must both be at least 2")
    checked_at = checked_at or observation_date + "T00:00:00+00:00"
    updated = copy.deepcopy(state)
    updated["version"] = 2
    records = updated.setdefault("sources", {})
    probes = updated.setdefault("probes", {})
    required = set(required_ids)
    for source_id, raw in sorted(observations.items()):
        result = normalize(raw)
        previous = dict(records.get(source_id, {}))
        old_probe = probes.get(source_id, {})
        last_change = old_probe.get("lastStateChangeAt")
        if old_probe.get("classification") != result["classification"]:
            last_change = checked_at
        probes[source_id] = {**result, "lastProbeAt": checked_at,
                             "lastStateChangeAt": last_change or checked_at}
        # Never turn an inconclusive sweep into a success or a quarantine.
        if not accepted or not result.get("conclusive"):
            continue
        if previous.get("lastObservationDate") == observation_date:
            continue
        kind = result["classification"]
        was_quarantined = previous.get("status") == "quarantined"
        failures = int(previous.get("consecutiveFailures", 0))
        successes = int(previous.get("consecutiveSuccesses", 0))
        if kind == "ok":
            if not was_quarantined or successes + 1 >= recovery_threshold:
                records.pop(source_id, None)
                continue
            successes += 1
            status = "quarantined"
        elif kind in FAILURES:
            # Reset the recovery streak on EVERY intervening failure.
            successes = 0
            failures = min(failures + 1, failure_threshold)
            status = "quarantined" if failures >= failure_threshold else "failing"
        else:
            # A protection challenge is reachable but cannot prove parser recovery.
            successes = 0
            if not was_quarantined:
                failures = 0
            status = "quarantined" if was_quarantined else "protected"
        if source_id in required and status == "quarantined":
            status = "failing"
        changed = previous.get("status") != status or (previous.get("classification") is not None and previous.get("classification") != kind)
        records[source_id] = {"status": status, "classification": kind,
                              "httpStatus": result.get("httpStatus"),
                              "consecutiveFailures": failures, "consecutiveSuccesses": successes,
                              "lastObservationDate": observation_date, "lastProbeAt": checked_at,
                              "lastStateChangeAt": checked_at if changed else previous.get("lastStateChangeAt", checked_at),
                              "severity": "high" if source_id in required else "warning",
                              "functional": "not_tested"}
    updated["sources"] = dict(sorted(records.items()))
    updated["probes"] = dict(sorted(probes.items()))
    updated["lastHealthSweepDate"] = observation_date
    updated["lastHealthSweepAt"] = checked_at
    return updated, {key for key, value in records.items() if value.get("status") == "quarantined"}
