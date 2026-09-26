"""Maintain one bot-owned incident for updater, chapter smoke, and public-host acceptance."""
import json
import os
import urllib.request

TITLE = "Aidoku source reliability check needs attention"
MARKER = "<!-- nixzle-updater-incident -->"

def incident_identity(kind: str) -> tuple[str, str]:
    if kind == "functional":
        return "<!-- nixzle-functional-incident -->", "Aidoku functional source acceptance needs attention"
    if kind == "public":
        return "<!-- nixzle-public-incident -->", "Aidoku public feed acceptance needs attention"
    return MARKER, TITLE



def api(method, path, body=None):
    request = urllib.request.Request(
        "https://api.github.com/repos/" + os.environ["GITHUB_REPOSITORY"] + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": "Bearer " + os.environ["GH_TOKEN"],
                 "Accept": "application/vnd.github+json",
                 "Content-Type": "application/json"},
        method=method,
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def main():
    kind = os.environ.get("INCIDENT_KIND", "combined")
    marker, title = incident_identity(kind)
    incidents = []
    page = 1
    while True:
        issues = api("GET", f"/issues?state=open&per_page=100&page={page}")
        incidents.extend(item for item in issues
                         if item.get("user", {}).get("login") == "github-actions[bot]"
                         and marker in (item.get("body") or "")
                         and "pull_request" not in item)
        if len(issues) < 100:
            break
        page += 1

    if kind == "functional":
        acceptance = os.environ.get("FUNCTIONAL_STATUS", "unknown")
        results = {"workflow execution": os.environ.get("UPDATE_RESULT", "unknown"),
                   "functional WASM acceptance": "success" if acceptance == "passed" else acceptance}
    elif kind == "public":
        results = {"public feed acceptance": os.environ.get("UPDATE_RESULT", "unknown")}
    else:
        results = {
            "catalog update": os.environ.get("UPDATE_RESULT", "unknown"),
            "critical chapter smoke": os.environ.get("SMOKE_RESULT", "success"),
            "public Pages acceptance": os.environ.get("ACCEPTANCE_RESULT", "success"),
        }
    run = f'https://github.com/{os.environ["GITHUB_REPOSITORY"]}/actions/runs/{os.environ["GITHUB_RUN_ID"]}'
    healthy = all(value == "success" for value in results.values())
    if healthy:
        for incident in incidents:
            api("PATCH", f'/issues/{incident["number"]}',
                {"state": "closed", "body": f"{marker}\nRecovered: [all reliability checks passed]({run})."})
        return

    summary = "\n".join(f"- {name}: `{value}`" for name, value in results.items())
    if kind == "functional":
        summary += "\n- Unverified source IDs: " + os.environ.get("UNVERIFIED_SOURCES", "see attached run evidence")
        summary += "\n\nBlocked means the headless runner did not establish reader usability; it is not a confirmed iOS parser failure."
    body = (
        f"{marker}\nOne or more Aidoku reliability checks did not pass.\n\n"
        f"{summary}\n\n[Inspect run]({run}).\n\n"
        "The previous published catalog remains recoverable through git history and rollback metadata."
    )
    if incidents:
        for incident in incidents:
            api("PATCH", f'/issues/{incident["number"]}', {"body": body})
    else:
        api("POST", "/issues", {"title": title, "body": body})


if __name__ == "__main__":
    main()
