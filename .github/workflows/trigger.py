#!/usr/bin/env python3

from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen


def request(path, params=None, query=None, body=None):
    path = urljoin("https://api.github.com/", path)
    if params is not None:
        path = path.format(**params)
    if query is not None:
        path = f"{path}?{urlencode(query)}"

    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    if body is None:
        data = None
    else:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = Request(path, data, headers=headers)

    try:
        with urlopen(req) as res:
            result = res.read()
    except HTTPError as e:
        e.add_note(e.read().decode("utf-8"))
        raise

    if result:
        return json.loads(result)


def trigger_workflow_dispatch():
    params = {"owner": "ocf", "repo": "transpire-ci", "workflow_id": "build-module.yml"}
    body = {
        "ref": "master",
        "inputs": {
            "run_id": os.environ["RUN_ID"],
            "module_name": os.environ["MODULE_NAME"],
        },
    }
    return request(
        "/repos/{owner}/{repo}/actions/workflows/{workflow_id}/dispatches",
        params=params,
        body=body,
    )


def find_triggered_run():
    params = {"owner": "ocf", "repo": "transpire-ci"}
    created_threshold = datetime.now(timezone.utc) - timedelta(minutes=5)
    query = {
        "event": "workflow_dispatch",
        "created": f">{created_threshold.isoformat()}",
    }
    result = request("/repos/{owner}/{repo}/actions/runs", params=params, query=query)
    if result is None:
        return None
    name_re = re.compile(rf"build .+ \({re.escape(os.environ['RUN_ID'])}\)")
    try:
        return next(x for x in result["workflow_runs"] if re.match(name_re, x["name"]))
    except StopIteration:
        return None


def get_run(run_id):
    params = {"owner": "ocf", "repo": "transpire-ci", "run_id": run_id}
    return request("/repos/{owner}/{repo}/actions/runs/{run_id}", params=params)


def main():
    print("Triggering workflow dispatch on ocf/transpire-ci")
    trigger_workflow_dispatch()

    for i in range(10):
        print(f"Looking for triggered workflow run (try {i})")
        triggered_run = find_triggered_run()
        if triggered_run is not None:
            break
        time.sleep(2)
    else:
        print("[ERROR] Could not find triggered workflow run")
        sys.exit(1)

    text = f"Found run with id {triggered_run['id']}"

    print()
    print(f"+-{'-' * len(text)}-+")
    print("|", text, "|")
    print(f"+-{'-' * len(text)}-+")
    print()

    url = f"https://github.com/ocf/transpire-ci/actions/runs/{triggered_run['id']}"
    print("For logs, please visit", url)
    print()

    while triggered_run["conclusion"] is None:
        print("Awaiting run conclusion")
        time.sleep(10)
        triggered_run = get_run(triggered_run["id"])
        if triggered_run is None:
            print(f"[ERROR] Run not found")
            sys.exit(1)

    print("Run concluded with status:", triggered_run["conclusion"])

    if triggered_run["conclusion"] != "success":
        sys.exit(1)


if __name__ == "__main__":
    main()
