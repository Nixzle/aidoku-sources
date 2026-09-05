"""Maintain one bot-owned incident using the result of the scheduled job."""
import json
import os
import urllib.request

TITLE = "Daily source updater needs attention"
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
    status = os.environ["UPDATE_RESULT"]
    run = f'https://github.com/{os.environ["GITHUB_REPOSITORY"]}/actions/runs/{os.environ["GITHUB_RUN_ID"]}'
    if status == "success":
        for incident in incidents:
            api("PATCH", f'/issues/{incident["number"]}',
                {"state": "closed", "body": f"{MARKER}\nRecovered: [successful run]({run})."})
    else:
        body = f"{MARKER}\nThe daily source update finished with `{status}`.\n\n[Inspect latest run]({run}).\n\nThe previous published catalog is retained."
        if incidents:
            for incident in incidents:
                api("PATCH", f'/issues/{incident["number"]}', {"body": body})
        else:
            api("POST", "/issues", {"title": TITLE, "body": body})


if __name__ == "__main__":
    main()
