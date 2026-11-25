"""Freesound helper (no login): search CC0/CC-BY sounds, read licence info from the public sound page,
download the public HQ preview MP3.

Usage (run with python3.11 -I):
  audio_fs.py search "rubber duck squeak" [--any-licence] [--page N]
  audio_fs.py info 36734 214319 ...
  audio_fs.py get 36734 ...          # downloads HQ previews into tools/audio_src/freesound/<id>/
"""
import html
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
SRC = os.path.join(ROOT, "tools", "audio_src", "freesound")
PAGES = os.path.join(SRC, "pages")
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"


def _curl(url, out=None):
    if out:
        # the CDN sometimes stalls mid-transfer: abort slow transfers and resume (-C -) a few times
        for attempt in range(8):
            r = subprocess.run(["curl", "-s", "-L", "-f", "-C", "-", "--speed-limit", "3000", "--speed-time", "12",
                                "--max-time", "600", "-A", UA, "-o", out, url])
            if r.returncode in (0, 33):  # 33: range not satisfiable = already complete
                return None
            time.sleep(1 + attempt)
        raise RuntimeError("download failed: %s" % url)
    cmd = ["curl", "-s", "-L", "--max-time", "300", "-A", UA, url]
    return subprocess.run(cmd, check=True, capture_output=True).stdout.decode("utf-8", "replace")


def _attr(block, name):
    m = re.search(r'%s="([^"]*)"' % re.escape(name), block)
    return html.unescape(m.group(1)) if m else ""


def search(query, cc0_only=True, page=1):
    q = {"q": query, "page": str(page)}
    if cc0_only:
        q["f"] = 'license:"Creative Commons 0"'
    url = "https://freesound.org/search/?" + urllib.parse.urlencode(q)
    text = _curl(url)
    res = []
    for blk in re.split(r'data-similar-sounds-modal-url=', text)[1:]:
        m = re.search(r'"/people/([^/]+)/sounds/(\d+)/', blk)
        if not m:
            continue
        res.append({
            "id": int(m.group(2)), "user": m.group(1),
            "title": _attr(blk, "data-title"),
            "duration": float(_attr(blk, "data-duration") or 0),
            "samplerate": _attr(blk, "data-samplerate"),
            "lq": _attr(blk, "data-mp3"),
        })
    return res


def info(sid, refresh=False):
    os.makedirs(PAGES, exist_ok=True)
    path = os.path.join(PAGES, "%d.html" % sid)
    if refresh or not os.path.exists(path):
        _curl("https://freesound.org/s/%d/" % sid, path)
        time.sleep(0.4)
    text = open(path, encoding="utf-8", errors="replace").read()
    d = {"id": sid}
    m = re.search(r'og:url" content="https://freesound.org/people/([^/]+)/sounds/(\d+)/"', text)
    d["user"] = html.unescape(m.group(1)) if m else ""
    d["page"] = "https://freesound.org/people/%s/sounds/%d/" % (d["user"], sid)
    m = re.search(r'og:audio:title" content="([^"]*)"', text)
    d["title"] = html.unescape(m.group(1)) if m else ""
    m = re.search(r'title="Go to the full license text" href="([^"]+)"[^>]*>([^<]+)</a>', text)
    d["licence_url"], d["licence"] = (m.group(1), m.group(2).strip()) if m else ("", "?")
    m = re.search(r'data-duration="([0-9.]+)"', text)
    d["duration"] = float(m.group(1)) if m else 0.0
    m = re.search(r'data-static-file-url="([^"]+-hq\.mp3)"', text)
    if not m:
        m = re.search(r'data-mp3="([^"]+)-lq\.mp3"', text)
        d["hq"] = (m.group(1) + "-hq.mp3") if m else ""
    else:
        d["hq"] = m.group(1)
    d["tags"] = sorted(set(re.findall(r'href="/browse/tags/([^/"]+)/"', text)))
    # description: text block just before the tag list
    m = re.search(r'(?s)<div[^>]*id="soundDescriptionSection"[^>]*>(.*?)</div>', text)
    if not m:
        m = re.search(r'(?s)class="[^"]*sound-description[^"]*"[^>]*>(.*?)</div>', text)
    if m:
        desc = re.sub(r"<[^>]+>", " ", m.group(1))
    else:
        i = text.find('/browse/tags/', text.find('og:image:alt') + 1)
        j = text.rfind('</div>', 0, text.find('href="/browse/tags/', 600 * 0 + text.find('Flag it') - 3000 if text.find('Flag it') > 3000 else 0))
        seg = text[max(0, text.find('Flag it') - 3000):text.find('Flag it')]
        desc = re.sub(r"<[^>]+>", " ", seg)
    d["description"] = re.sub(r"\s+", " ", html.unescape(desc)).strip()[-400:]
    m = re.search(r'(?s)Channels</p>\s*<p[^>]*>([^<]+)<', text)
    d["channels"] = m.group(1).strip() if m else ""
    m = re.search(r'(?s)Sample rate</p>\s*<p[^>]*>([^<]+)<', text)
    d["samplerate"] = m.group(1).strip() if m else ""
    return d


def ok_licence(d):
    lic = d["licence"].lower()
    if "noncommercial" in lic or "non-commercial" in lic or "sampling" in lic:
        return False
    return lic.startswith("creative commons 0") or lic.startswith("attribution")


def get(sid):
    d = info(sid)
    if not ok_licence(d):
        raise SystemExit("licence not allowed for %d: %s" % (sid, d["licence"]))
    out_dir = os.path.join(SRC, str(sid))
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, os.path.basename(d["hq"]))
    if not os.path.exists(out) or os.path.getsize(out) < 1000:
        part = out + ".part"
        _curl(d["hq"], part)  # raises on timeout, so a partial file never takes the final name
        os.replace(part, out)
    with open(os.path.join(out_dir, "info.json"), "w") as f:
        json.dump(d, f, indent=1)
    return out, d


def main(argv):
    if not argv:
        print(__doc__)
        return
    cmd = argv[0]
    if cmd == "search":
        cc0 = "--any-licence" not in argv
        page = 1
        if "--page" in argv:
            page = int(argv[argv.index("--page") + 1])
        for r in search(argv[1], cc0, page):
            print("%7d  %6.1fs  %-22s %s" % (r["id"], r["duration"], r["user"][:22], r["title"][:70]))
    elif cmd == "info":
        for s in argv[1:]:
            d = info(int(s))
            print("%(id)d | %(title)s | by %(user)s | %(licence)s | %(duration).1fs | %(channels)s %(samplerate)s" % d)
            print("    tags:", " ".join(d["tags"][:25]))
            print("    desc:", d["description"][-300:])
    elif cmd == "get":
        for s in argv[1:]:
            out, d = get(int(s))
            print(d["id"], d["licence"], out, os.path.getsize(out))


if __name__ == "__main__":
    main(sys.argv[1:])
