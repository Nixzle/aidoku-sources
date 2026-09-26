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
    kinds = {
        "updater": (TITLE, MARKER, "The daily source update", "The previous published catalog is retained."),
        "public": ("Public Aidoku feed needs attention", "<!-- nixzle-public-incident -->", "Public feed acceptance", "Repository validation is not evidence that the live feed matches. Inspect the pinned receipt before rollback."),
        "functional": ("Aidoku functional source checks need attention", "<!-- nixzle-functional-incident -->", "Functional source acceptance", "A blocked headless check is not a pass or proof of an in-app outage. Inspect per-source stage and network evidence."),
    }
    title, marker, description, guidance = kinds[os.environ.get("INCIDENT_KIND", "updater")]
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
    status = os.environ["UPDATE_RESULT"]
    if os.environ.get("INCIDENT_KIND", "updater") == "updater":
        aggregate = {"catalog update": status, "critical chapter smoke": os.environ.get("SMOKE_RESULT", "success"), "public Pages acceptance": os.environ.get("ACCEPTANCE_RESULT", "success")}
        status = "success" if all(value == "success" for value in aggregate.values()) else "failure"
        guidance += " Results: " + ", ".join(f"{key}={value}" for key,value in aggregate.items())
    run = f'https://github.com/{os.environ["GITHUB_REPOSITORY"]}/actions/runs/{os.environ["GITHUB_RUN_ID"]}'
    if status == "success":
        for incident in incidents:
            api("PATCH", f'/issues/{incident["number"]}',
                {"state": "closed", "body": f"{marker}\nRecovered: [successful run]({run})."})
    else:
        body = f"{marker}\n{description} finished with `{status}`.\n\n[Inspect latest run]({run}).\n\n{guidance}"
        if incidents:
            for incident in incidents:
                api("PATCH", f'/issues/{incident["number"]}', {"body": body})
        else:
            api("POST", "/issues", {"title": title, "body": body})


if __name__ == "__main__":
    main()
