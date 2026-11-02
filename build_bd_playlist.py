#!/usr/bin/env python3
"""Build a Bangladesh-only M3U + placeholder XMLTV EPG from iptv-org's API.

Run:  pip install requests && python build_bd_playlist.py
Outputs: bangla-iptv.m3u, epg.xml
NOTE: written against the iptv-org API schema as I know it; if a field
name has changed, adjust the keys below.
"""
import concurrent.futures as cf
from datetime import datetime, timedelta, timezone
from xml.sax.saxutils import escape

import requests

API = "https://iptv-org.github.io/api"
COUNTRY = "BD"          # channel's country, so Indian (IN) channels drop out
CHECK_STREAMS = True    # drop dead links
EPG_DAYS = 2            # placeholder guide length

def get(name):
    r = requests.get(f"{API}/{name}.json", timeout=30)
    r.raise_for_status()
    return r.json()

def alive(url):
    try:
        r = requests.get(url, stream=True, timeout=8,
                         headers={"User-Agent": "Mozilla/5.0"})
        ok = r.status_code < 400
        r.close()
        return ok
    except requests.RequestException:
        return False

channels = {c["id"]: c for c in get("channels")
            if c.get("country") == COUNTRY and not c.get("is_nsfw")}
streams = [s for s in get("streams") if s.get("channel") in channels]

try:
    logos = {}
    for l in get("logos"):
        logos.setdefault(l["channel"], l["url"])
except Exception:
    logos = {}

if CHECK_STREAMS:
    with cf.ThreadPoolExecutor(20) as ex:
        flags = list(ex.map(lambda s: alive(s["url"]), streams))
    streams = [s for s, ok in zip(streams, flags) if ok]

# one stream per channel (first working one)
seen, picked = set(), []
for s in streams:
    if s["channel"] not in seen:
        seen.add(s["channel"])
        picked.append(s)

# --- M3U ---
lines = ["#EXTM3U x-tvg-url=\"https://YOUR-HOST/epg.xml\""]
for s in picked:
    c = channels[s["channel"]]
    cats = ";".join(c.get("categories") or []) or "General"
    logo = logos.get(c["id"], "")
    lines.append(
        f'#EXTINF:-1 tvg-id="{c["id"]}" tvg-name="{c["name"]}" '
        f'tvg-logo="{logo}" group-title="{cats}",{c["name"]}')
    if s.get("user_agent"):
        lines.append(f'#EXTVLCOPT:http-user-agent={s["user_agent"]}')
    if s.get("referrer"):
        lines.append(f'#EXTVLCOPT:http-referrer={s["referrer"]}')
    lines.append(s["url"])
open("bangla-iptv.m3u", "w", encoding="utf-8").write("\n".join(lines) + "\n")

# --- placeholder XMLTV: 2-hour "Live" blocks so the guide grid isn't empty ---
fmt = "%Y%m%d%H%M%S +0000"
start = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
x = ['<?xml version="1.0" encoding="UTF-8"?>', "<tv>"]
for s in picked:
    c = channels[s["channel"]]
    x.append(f'<channel id="{c["id"]}"><display-name>{escape(c["name"])}</display-name></channel>')
for s in picked:
    c = channels[s["channel"]]
    t = start
    while t < start + timedelta(days=EPG_DAYS):
        e = t + timedelta(hours=2)
        x.append(f'<programme start="{t.strftime(fmt)}" stop="{e.strftime(fmt)}" channel="{c["id"]}">'
                 f'<title>{escape(c["name"])} Live</title></programme>')
        t = e
x.append("</tv>")
open("epg.xml", "w", encoding="utf-8").write("\n".join(x))

print(f"{len(picked)} Bangladeshi channels written")
