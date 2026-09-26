"""Maintain one bot-owned incident for updater, chapter smoke, and public-host acceptance."""
import json
import os
import urllib.request

TITLE = "Aidoku source reliability check needs attention"
MARKER = "<!-- nixzle-updater-incident -->"


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
    incidents = []
    page = 1
    while True:
        issues = api("GET", f"/issues?state=open&per_page=100&page={page}")
        incidents.extend(item for item in issues
                         if item.get("user", {}).get("login") == "github-actions[bot]"
                         and MARKER in (item.get("body") or "")
                         and "pull_request" not in item)
        if len(issues) < 100:
            break
        page += 1

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
                {"state": "closed", "body": f"{MARKER}\nRecovered: [all reliability checks passed]({run})."})
        return

    summary = "\n".join(f"- {name}: `{value}`" for name, value in results.items())
    body = (
        f"{MARKER}\nOne or more Aidoku reliability checks did not pass.\n\n"
        f"{summary}\n\n[Inspect run]({run}).\n\n"
        "The previous published catalog remains recoverable through git history and rollback metadata."
    )
    if incidents:
        for incident in incidents:
            api("PATCH", f'/issues/{incident["number"]}', {"body": body})
    else:
        api("POST", "/issues", {"title": TITLE, "body": body})


if __name__ == "__main__":
    main()
