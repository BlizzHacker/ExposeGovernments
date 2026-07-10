#!/usr/bin/env python3
"""Build a redacted public Mayor Watch feed from the raw Facebook scrape."""
import json
from datetime import datetime, timezone
from pathlib import Path

RAW_FEED = Path("/opt/facebook-scrape/mayor-watch-feed.json")
PUBLIC_FEED = Path("/opt/facebook-scrape/mayor-watch-public.json")
FB_TOKENS = Path("/opt/fb-tokens.json")
FB_CREDENTIALS = Path("/opt/miamiok-work/facebook_credentials.json")


def read_json(path, fallback):
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return fallback


def redacted_item(item, index):
    return {
        "id": index,
        "label": f"Public-source item {index}",
        "type": item.get("type") or "public_source",
        "severity": item.get("severity") or "review",
        "captured": item.get("captured"),
        "posted_at": item.get("posted_at"),
        "status": "pending_moderator_review",
        "public_note": "Raw Facebook text, author names, and source URLs are held for staff review before anything is published.",
    }


def main():
    raw = read_json(RAW_FEED, {})
    evidence = raw.get("evidence") or []
    stats = raw.get("stats") or {}
    now = datetime.now(timezone.utc).isoformat()
    public = {
        "generated": now,
        "raw_generated": raw.get("generated"),
        "source": {
            "name": "Promote4.me / Facebook public-source monitor",
            "facebook_connected": FB_TOKENS.exists() or FB_CREDENTIALS.exists(),
            "raw_feed_private": True,
        },
        "stats": {
            "monitored_posts": int(stats.get("total_posts") or 0),
            "items_pending_review": len(evidence),
            "high_priority_items": int(stats.get("high_priority") or 0),
            "published_allegations": 0,
        },
        "moderation": {
            "public_policy": "Only reviewed public-records context, official-source links, and moderator-approved summaries should be published.",
            "private_policy": "Raw names, screenshots, personal claims, and Facebook URLs remain admin-only until verified.",
        },
        "review_queue": [redacted_item(item, index + 1) for index, item in enumerate(evidence[:12])],
    }
    PUBLIC_FEED.write_text(json.dumps(public, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(PUBLIC_FEED)


if __name__ == "__main__":
    main()
