#!/usr/bin/env python3
"""Collect a bounded, read-only status snapshot for the Expose admin desk.

Run this on the Proxmox entry node. It checks public HTTPS and automation files,
and reads the Miami request aggregate through a fixed `pct exec 170` command.
It never connects to a guest address and never exposes request contents.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

OUTPUT = Path("/var/lib/expose-network/network-status.json")
TIMEOUT_SECONDS = 8
CHAPTERS = (
    ("miamiok", "Miami, OK", "miami.exposeoklahoma.com", "/data/automation-status.json"),
    ("okc", "Oklahoma City, OK", "okc.exposeoklahoma.com", "/data/automation.json"),
    ("tulsa", "Tulsa, OK", "tulsa.exposeoklahoma.com", "/data/automation.json"),
    ("claremore", "Claremore, OK", "claremore.exposeoklahoma.com", "/data/automation.json"),
    ("sanangelo", "San Angelo, TX", "sanangelo.exposetexas.org", "/data/automation.json"),
    ("houston", "Houston, TX", "houston.exposetexas.org", "/data/automation.json"),
    ("dallas", "Dallas, TX", "dallas.exposetexas.org", "/data/automation.json"),
    ("austin", "Austin, TX", "austin.exposetexas.org", "/data/automation.json"),
    ("sanantonio", "San Antonio, TX", "sanantonio.exposetexas.org", "/data/automation.json"),
    ("lubbock", "Lubbock, TX", "lubbock.exposetexas.org", "/data/automation.json"),
    ("abilene", "Abilene, TX", "abilene.exposetexas.org", "/data/automation.json"),
    ("mississippi", "Southaven, MS", "southaven.exposemississippi.com", "/data/automation.json"),
    ("jackson", "Jackson, MS", "jackson.exposemississippi.com", "/data/automation.json"),
    ("olivebranch", "Olive Branch, MS", "olivebranch.exposemississippi.com", "/data/automation.json"),
)


def fetch_json(url):
    request = Request(url, headers={"User-Agent": "ExposeNetworkCollector/1.0"})
    with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        if response.status != 200:
            raise RuntimeError("HTTP {}".format(response.status))
        return json.loads(response.read(2_000_000).decode("utf-8"))


def check_home(host):
    request = Request("https://{}/".format(host), headers={"User-Agent": "ExposeNetworkCollector/1.0"})
    with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        response.read(1024)
        return response.status


def automation_summary(data):
    jobs = data.get("jobs", []) if isinstance(data, dict) else []
    failure_count = data.get("failure_count") if isinstance(data, dict) else None
    if failure_count is None:
        failure_count = sum(
            1
            for job in jobs
            if str(job.get("status", "")).lower() in {"error", "failed", "fail", "down"}
        )
    generated_at = data.get("generated_at") if isinstance(data, dict) else None
    status = "error" if failure_count else "ok"
    detail = "{} failed jobs".format(failure_count) if failure_count else "Automation report loaded"
    return {"status": status, "detail": detail, "last_success_at": generated_at}


def collect_chapter(chapter):
    key, label, host, automation_path = chapter
    result = {
        "key": key,
        "label": label,
        "host": host,
        "health": {"status": "unknown", "detail": "Check not completed"},
        "automation": {"status": "unknown", "detail": "Report not loaded"},
        "requests": {"connected": False, "total": 0, "pending": 0},
    }
    try:
        code = check_home(host)
        result["health"] = {"status": "ok", "detail": "HTTPS {}".format(code)}
    except (HTTPError, URLError, TimeoutError, RuntimeError) as error:
        result["health"] = {"status": "down", "detail": str(error)[:180]}
    try:
        result["automation"] = automation_summary(fetch_json("https://{}{}".format(host, automation_path)))
    except (HTTPError, URLError, TimeoutError, RuntimeError, ValueError) as error:
        result["automation"] = {"status": "error", "detail": str(error)[:180]}
    return result


def miami_request_counts():
    command = [
        "pct",
        "exec",
        "170",
        "--",
        "python3",
        "-c",
        (
            "import json;"
            "d=json.load(open('/var/www/exposemiamiok/data/foia/requests.json'));"
            "r=d.get('requests',[]);"
            "print(json.dumps({'total':len(r),'pending':sum(x.get('status')=='pending_review' for x in r)}))"
        ),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, timeout=15, check=True)
    counts = json.loads(completed.stdout)
    return {"connected": True, "total": counts["total"], "pending": counts["pending"]}


def main():
    errors = []
    chapters = []
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(collect_chapter, chapter): chapter[0] for chapter in CHAPTERS}
        for future in as_completed(futures):
            key = futures[future]
            try:
                chapters.append(future.result())
            except Exception as error:
                errors.append("{}: {}".format(key, str(error)[:180]))
    chapters.sort(key=lambda item: next(i for i, row in enumerate(CHAPTERS) if row[0] == item["key"]))
    try:
        next(item for item in chapters if item["key"] == "miamiok")["requests"] = miami_request_counts()
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        errors.append("miami request aggregate: {}".format(str(error)[:180]))

    snapshot = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "chapters": chapters,
        "errors": errors,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    temporary = OUTPUT.with_suffix(".tmp")
    temporary.write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")
    temporary.replace(OUTPUT)
    subprocess.run(
        [
            "pct",
            "push",
            "170",
            str(OUTPUT),
            "/var/www/exposemiamiok/data/foia/network-status.json",
            "--perms",
            "0640",
        ],
        capture_output=True,
        text=True,
        timeout=20,
        check=True,
    )


if __name__ == "__main__":
    main()
