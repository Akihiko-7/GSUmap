"""Download the openly licensed GSU photographs listed in CREDITS.md from Wikimedia Commons.

Each is fetched at 1024 px wide, checked to be a real JPEG, and written to static/photos/commons/<local name>.
Files already present are skipped, so the script can be re-run safely.
Usage: python tools/fetch_photos.py
"""
import io
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "static" / "photos" / "commons"
UA = "GSU-Compass/0.1 (open-source campus guide; hackathon)"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = re.findall(r"^\| (\S+\.jpe?g) \| ([^|]+) \| ([^|]+) \| (https://commons\.wikimedia\.org/wiki/File:\S+) \|", (ROOT / "CREDITS.md").read_text().split("## Crop leaves")[0], re.M)
    ok = fail = 0
    for local, _lic, _author, url in rows:
        dest = OUT / local
        if dest.exists():
            ok += 1
            continue
        title = urllib.parse.unquote(url.split("/wiki/File:", 1)[1])
        src = "https://commons.wikimedia.org/wiki/Special:FilePath/" + urllib.parse.quote(title) + "?width=1024"
        for attempt in range(3):
            try:
                req = urllib.request.Request(src, headers={"User-Agent": UA})
                data = urllib.request.urlopen(req, timeout=60).read()
                im = Image.open(io.BytesIO(data))
                im.verify()
                dest.write_bytes(data)
                ok += 1
                print("ok  ", local, len(data) // 1024, "KB", flush=True)
                break
            except Exception as e:  # network hiccups and rate limits: wait and retry
                print("retry", local, e, flush=True)
                time.sleep(5 * (attempt + 1))
        else:
            fail += 1
            print("FAIL", local, flush=True)
        time.sleep(1.0)
    print(f"done: {ok} present, {fail} failed")


if __name__ == "__main__":
    main()
