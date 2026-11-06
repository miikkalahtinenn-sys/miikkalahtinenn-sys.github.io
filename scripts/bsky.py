#!/usr/bin/env python3
"""Julkaisee aamun suomalaiskatsauksen Blueskyyn kerran pelipäivää kohden.

Tarvitsee GitHubin salaisuudet BSKY_HANDLE (esim. punalamppu.bsky.social) ja BSKY_APP_PASSWORD
(Blueskyn asetuksista luotu sovellussalasana – EI tilin varsinainen salasana).
Ilman salaisuuksia skripti ei tee mitään.
"""
import datetime as dt
import json
import os
import sys
import urllib.request
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE = os.path.join(ROOT, "data", "bsky.json")
PDS = "https://bsky.social/xrpc"
BASE = "https://punalamppu.com"


def call(method, body, token=None):
    req = urllib.request.Request(f"{PDS}/{method}", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def main():
    handle, pw = os.environ.get("BSKY_HANDLE"), os.environ.get("BSKY_APP_PASSWORD")
    if not handle or not pw:
        print("Bluesky: salaisuuksia ei ole asetettu, ohitetaan")
        return
    rec = json.load(open(os.path.join(ROOT, "_site", "recap.json"), encoding="utf-8"))
    st = json.load(open(STATE)) if os.path.exists(STATE) else {}
    now = dt.datetime.now(ZoneInfo("Europe/Helsinki"))
    force = os.environ.get("BSKY_FORCE") == "true"
    if st.get("last") == rec["gameDate"] and not force:
        print("Bluesky: jo julkaistu", rec["gameDate"])
        return
    if not rec.get("games") or rec.get("pending") or not rec.get("text"):
        print("Bluesky: yön ottelut eivät ole vielä valmiita")
        return
    if not (6 <= now.hour < 13) and not force:
        print("Bluesky: julkaistaan vain aamulla")
        return
    url = BASE + rec["url"]
    text = rec["text"]
    tail = "\nKaikki tulokset ja maalikoosteet: "
    link = url.replace("https://", "")
    if len(text) + len(tail) + len(link) > 295:
        text = text[: 295 - len(tail) - len(link) - 1].rsplit(",", 1)[0] + "…"
    full = text + tail + link
    start = len((text + tail).encode("utf-8"))
    facets = [{"index": {"byteStart": start, "byteEnd": start + len(link.encode("utf-8"))},
               "features": [{"$type": "app.bsky.richtext.facet#link", "uri": url}]}]
    tag = "#NHL"
    full += " " + tag
    ts = len(full.encode("utf-8")) - len(tag.encode("utf-8"))
    facets.append({"index": {"byteStart": ts, "byteEnd": ts + len(tag.encode("utf-8"))}, "features": [{"$type": "app.bsky.richtext.facet#tag", "tag": "NHL"}]})
    s = call("com.atproto.server.createSession", {"identifier": handle, "password": pw})
    record = {"$type": "app.bsky.feed.post", "text": full, "facets": facets, "langs": ["fi"],
              "createdAt": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
              "embed": {"$type": "app.bsky.embed.external", "external": {"uri": url, "title": f"NHL-tulokset ja suomalaiset – Punalamppu",
                                                                         "description": "Yön NHL-tulokset, maalit, suomalaisten tehot ja maalikoosteet suomeksi."}}}
    r = call("com.atproto.repo.createRecord", {"repo": s["did"], "collection": "app.bsky.feed.post", "record": record}, s["accessJwt"])
    st = {"last": rec["gameDate"], "uri": r.get("uri"), "at": now.isoformat(timespec="minutes")}
    json.dump(st, open(STATE, "w"))
    print("Bluesky: julkaistu", r.get("uri"))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # julkaisu ei saa kaataa sivuston päivitystä
        print("Bluesky epäonnistui:", e)
        sys.exit(0)
