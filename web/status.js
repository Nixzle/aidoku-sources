"use strict";
const put = (id, text) => { document.getElementById(id).textContent = text; };
const date = value => {
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? "unknown" : parsed.toLocaleString();
};
async function json(url) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 10000);
  try {
    const response = await fetch(url, {signal: controller.signal, cache: "no-cache"});
    if (!response.ok) throw new Error("Status unavailable");
    return await response.json();
  } finally { clearTimeout(timeout); }
}
document.getElementById("copy").addEventListener("click", async () => {
  const input = document.getElementById("catalog-url");
  try {
    await navigator.clipboard.writeText(input.value);
    put("copy-result", "Copied. Paste into Aidoku â†’ Settings â†’ Source Lists.");
  } catch {
    input.focus(); input.select();
    put("copy-result", "Select and copy the highlighted link.");
  }
});
const runs = "https://api.github.com/repos/Nixzle/aidoku-sources/actions/workflows/daily-update.yml/runs";
json(runs + "?branch=main&per_page=1").then(data => {
  const latest = data.workflow_runs?.[0];
  if (!latest) throw new Error("No run");
  const result = latest.status === "completed" ? latest.conclusion : latest.status;
  put("automation-status", "Latest run: " + result + " Â· " + date(latest.updated_at));
}).catch(() => put("automation-status", "Live status unavailable. Check update runs below."));
json(runs + "?branch=main&status=success&per_page=1").then(data => {
  const latest = data.workflow_runs?.[0];
  if (!latest) throw new Error("No successful run");
  const stale = Date.now() - Date.parse(latest.updated_at) > 48 * 60 * 60 * 1000;
  put("last-success", "Last successful update: " + date(latest.updated_at) + (stale ? " â€” overdue; please check the updater." : ""));
}).catch(() => put("last-success", "Last successful update: unable to verify."));
json("inventory.json").then(data => {
  put("catalog-changed", "Catalog last changed: " + date(data.generatedAt));
  if (Number.isInteger(data.sourceCount)) put("source-count", data.sourceCount + " sources available.");
}).catch(() => put("catalog-changed", "Catalog timestamp unavailable."));

// A workflow result is labelled by its actual scope, never as device-wide health.
for (const [workflow,id,label] of [
  ["public-acceptance.yml","public-acceptance","Public feed check"],
  ["functional-smoke.yml","functional-acceptance","Headless functional check"]
]) {
  const endpoint = "https://api.github.com/repos/Nixzle/aidoku-sources/actions/workflows/" + workflow + "/runs?branch=main&per_page=1";
  json(endpoint).then(data => {
    const latest = data.workflow_runs?.[0];
    if (!latest) throw new Error("No acceptance run");
    const result = latest.status === "completed" ? latest.conclusion : latest.status;
    const age = Date.now() - Date.parse(latest.updated_at);
    put(id, label + ": " + result + " · " + date(latest.updated_at) + (age > 48*60*60*1000 ? " · stale evidence" : ""));
  }).catch(() => put(id,label + ": unable to verify. Open the evidence link below."));
}
json("status.json").then(data => {
  const value = data.lastHealthSweepAt;
  put("website-sweep", "Last website sweep: " + (value ? date(value) : "not recorded")
      + (data.lastSweep?.accepted === false ? " · inconclusive; health counters preserved" : ""));
}).catch(() => put("website-sweep","Last website sweep: unable to verify."));
