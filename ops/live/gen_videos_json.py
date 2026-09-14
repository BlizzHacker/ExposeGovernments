#!/usr/bin/env python3
"""Generate /api/videos.json from official Granicus crawl plus local YouTube markers."""
import glob
import json
import os
import sys
from pathlib import Path

MEETINGS_DIR = Path("/var/www/exposemiamiok/html/meetings")
MANIFEST_FILE = Path("/opt/meetings_manifest.json")
OFFICIAL_FILE = Path("/opt/miamiok-granicus-videos.json")
OUTPUT = Path("/var/www/exposemiamiok/html/api/videos.json")


def load_json(path, default):
    if not path.exists():
        return default
    with path.open() as f:
        return json.load(f)


def uploaded_map():
    uploads = {}
    for marker in glob.glob(str(MEETINGS_DIR / "*" / "youtube_uploaded.json")):
        clip_id = os.path.basename(os.path.dirname(marker))
        try:
            with open(marker) as f:
                payload = json.load(f)
        except (OSError, json.JSONDecodeError) as error:
            print(f"Skipping invalid YouTube upload marker {marker}: {error}", file=sys.stderr)
            continue
        if not isinstance(payload, dict):
            print(f"Skipping non-object YouTube upload marker {marker}", file=sys.stderr)
            continue
        uploads[clip_id] = payload
    return uploads


def main():
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    manifest = {str(m.get("clip_id")): m for m in load_json(MANIFEST_FILE, [])}
    official = {str(v.get("clip_id")): v for v in load_json(OFFICIAL_FILE, [])}
    uploads = uploaded_map()

    clip_ids = set(manifest) | set(official) | set(uploads)
    videos = []
    for clip_id in clip_ids:
        m = manifest.get(clip_id, {})
        o = official.get(clip_id, {})
        y = uploads.get(clip_id, {})
        local_dir = MEETINGS_DIR / clip_id

        youtube_id = y.get("video_id", "")
        youtube_url = y.get("url", "")
        official_url = (
            o.get("video_page_url")
            or m.get("official_video_url")
            or (f"https://miamiok.granicus.com/MediaPlayer.php?view_id=1&clip_id={clip_id}" if o else "")
        )
        official_embed = (
            o.get("embed_url")
            or m.get("official_embed_url")
            or (f"https://miamiok.granicus.com/player/clip/{clip_id}" if o else "")
        )

        videos.append(
            {
                "clip_id": clip_id,
                "title": y.get("title") or m.get("name") or o.get("name") or f"Meeting #{clip_id}",
                "date": m.get("date") or o.get("date") or "",
                "duration": m.get("duration") or o.get("duration") or "",
                "youtube_video_id": youtube_id,
                "youtube_url": youtube_url,
                "youtube_embed_url": f"https://www.youtube.com/embed/{youtube_id}" if youtube_id else "",
                "uploaded_at": y.get("uploaded_at", ""),
                "official_video_url": official_url,
                "official_embed_url": official_embed,
                "agenda_url": m.get("agenda_url") or m.get("city_agenda_url") or o.get("agenda_granicus_url") or "",
                "minutes_url": m.get("minutes_url") or m.get("city_minutes_url") or o.get("minutes_granicus_url") or "",
                "has_transcript": (local_dir / "transcript.json").exists(),
                "has_captions": (local_dir / "captions.srt").exists(),
                "status": "youtube_uploaded" if youtube_id else "official_video",
                "primary_embed_url": official_embed or (f"https://www.youtube.com/embed/{youtube_id}" if youtube_id else ""),
                "primary_source": "Official Miami Web TV" if official_embed else "YouTube",
            }
        )

    videos.sort(key=lambda v: int(v["clip_id"]) if str(v["clip_id"]).isdigit() else 0, reverse=True)
    OUTPUT.write_text(json.dumps(videos, indent=2))
    print(f"Generated {OUTPUT} with {len(videos)} videos ({len(uploads)} YouTube uploads)")


if __name__ == "__main__":
    main()
