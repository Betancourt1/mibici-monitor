#!/usr/bin/env python3
import gzip
import hashlib
import json
import logging
import os
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from google.cloud import storage


BASE_URL = "https://guadalajara.publicbikesystem.net/customer/gbfs/v3.0"
FAST_FEEDS = ("station_status",)
HOURLY_FEEDS = (
    "station_information",
    "system_information",
    "system_pricing_plans",
    "system_regions",
    "vehicle_types",
    "geofencing_zones",
)
DAILY_FEEDS = ("gbfs", "gbfs_versions")

BUCKET = os.environ["MIBICI_BUCKET"]
BUFFER_DIR = Path(os.getenv("MIBICI_BUFFER_DIR", "/var/lib/mibici-collector/buffer"))
LOCAL_TZ = ZoneInfo("America/Mexico_City")
HTTP_TIMEOUT_SECONDS = 20

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(message)s",
)
session = requests.Session()
storage_client = storage.Client()
bucket = storage_client.bucket(BUCKET)


def interval_seconds(now: datetime) -> int:
    """15 s near/inside service hours; 5 min during the overnight lull."""
    local = now.astimezone(LOCAL_TZ)
    minutes = local.hour * 60 + local.minute
    return 15 if minutes >= 4 * 60 + 45 or minutes < 1 * 60 + 15 else 300


def feed_url(feed: str) -> str:
    return f"{BASE_URL}/{feed}.json" if feed == "gbfs" else f"{BASE_URL}/{feed}"


def fetch(feed: str, observed_at: datetime) -> None:
    url = feed_url(feed)
    response = session.get(url, timeout=HTTP_TIMEOUT_SECONDS)
    response.raise_for_status()
    payload = response.json()
    raw = response.content
    record = {
        "observed_at": observed_at.isoformat(),
        "feed": feed,
        "source_url": url,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "payload": payload,
    }
    hour = observed_at.strftime("%Y-%m-%dT%H")
    target_dir = BUFFER_DIR / feed
    target_dir.mkdir(parents=True, exist_ok=True)
    with (target_dir / f"{hour}.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")


def upload_completed_hours(now: datetime) -> None:
    current_hour = now.strftime("%Y-%m-%dT%H")
    for source in BUFFER_DIR.glob("*/*.jsonl"):
        if source.stem >= current_hour:
            continue
        feed = source.parent.name
        parsed = datetime.strptime(source.stem, "%Y-%m-%dT%H").replace(tzinfo=timezone.utc)
        compressed = source.with_suffix(".jsonl.gz")
        with source.open("rb") as incoming, gzip.open(compressed, "wb") as outgoing:
            shutil.copyfileobj(incoming, outgoing)
        object_name = (
            f"gbfs/{feed}/year={parsed:%Y}/month={parsed:%m}/day={parsed:%d}/"
            f"hour={parsed:%H}/{source.stem}.jsonl.gz"
        )
        bucket.blob(object_name).upload_from_filename(
            compressed, content_type="application/gzip", if_generation_match=0
        )
        logging.info("uploaded gs://%s/%s", BUCKET, object_name)
        source.unlink()
        compressed.unlink()


def due(last_run: dict[str, float], feed: str, period: int, now_ts: float) -> bool:
    return now_ts - last_run.get(feed, 0) >= period


def main() -> None:
    BUFFER_DIR.mkdir(parents=True, exist_ok=True)
    last_run: dict[str, float] = {}
    while True:
        started = time.time()
        now = datetime.now(timezone.utc)
        schedule = {**{f: interval_seconds(now) for f in FAST_FEEDS},
                    **{f: 3600 for f in HOURLY_FEEDS},
                    **{f: 86400 for f in DAILY_FEEDS}}
        for feed, period in schedule.items():
            if not due(last_run, feed, period, started):
                continue
            try:
                fetch(feed, now)
                last_run[feed] = started
            except Exception:
                logging.exception("failed to collect %s", feed)
        try:
            upload_completed_hours(now)
        except Exception:
            logging.exception("failed to upload completed hour")
        sleep_for = max(1, interval_seconds(now) - (time.time() - started))
        time.sleep(sleep_for)


if __name__ == "__main__":
    main()
