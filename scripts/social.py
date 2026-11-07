#!/usr/bin/env python3
"""Julkaisee aamun suomalaiskatsauksen someen kerran pelipäivää kohden: Bluesky, Telegram ja Threads.

Kukin palvelu on käytössä vain, jos sen GitHub-salaisuudet on asetettu:
  Bluesky:  BSKY_HANDLE, BSKY_APP_PASSWORD (sovellussalasana)
  Telegram: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID (esim. @punalamppu)
  Threads:  THREADS_TOKEN (pitkäikäinen käyttötunnus). Tunnus uusitaan automaattisesti ~50 päivän välein;
            uusittu tunnus tallennetaan salattuna tiedostoon data/threads.enc (avaimena alkuperäinen THREADS_TOKEN).
Ympäristömuuttuja SOCIAL_FORCE=true julkaisee heti (testi), aikarajasta ja aiemmista julkaisuista välittämättä.
"""
import datetime as dt
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE = os.path.join(ROOT, "data", "social.json")
OLD_BSKY = os.path.join(ROOT, "data", "bsky.json")
TENC = os.path.join(ROOT, "data", "threads.enc")
BASE = "https://punalamppu.com"
HEL = ZoneInfo("Europe/Helsinki")


def http(url, body=None, headers=None, form=False, method=None):
    data = None
    h = dict(headers or {})
    if body is not None:
        if form:
            data = urllib.parse.urlencode(body).encode()
            h["Content-Type"] = "application/x-www-form-urlencoded"
        else:
            data = json.dumps(body).encode()
            h["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode() or "{}")


# ---------------------------------------------------------------- Bluesky
def post_bsky(rec, url):
    handle = (os.environ.get("BSKY_HANDLE") or "").strip().lstrip("@").strip()
    pw = (os.environ.get("BSKY_APP_PASSWORD") or "").strip()
    if not handle or not pw:
        return None
    if "." not in handle and "@" not in handle:
        handle += ".bsky.social"
    pds = "https://bsky.social/xrpc"
    text = rec["text"]
    tail = "\nKaikki tulokset ja maalikoosteet: "
    link = url.replace("https://", "")
    if len(text) + len(tail) + len(link) > 270:
        text = text[: 270 - len(tail) - len(link) - 1].rsplit(",", 1)[0] + "…"
    full = text + tail + link
    start = len((text + tail).encode())
    facets = [{"index": {"byteStart": start, "byteEnd": start + len(link.encode())}, "features": [{"$type": "app.bsky.richtext.facet#link", "uri": url}]}]
    for tag in ("NHL", "NHLfi", "jääkiekko"):
        full += f" #{tag}"
        end = len(full.encode())
        facets.append({"index": {"byteStart": end - len(("#" + tag).encode()), "byteEnd": end}, "features": [{"$type": "app.bsky.richtext.facet#tag", "tag": tag}]})
    try:
        s = http(f"{pds}/com.atproto.server.createSession", {"identifier": handle, "password": pw})
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"kirjautuminen epäonnistui ({e.code}); salasanan pituus {len(pw)} (sovellussalasana on 19)")
    record = {"$type": "app.bsky.feed.post", "text": full, "facets": facets, "langs": ["fi"],
              "createdAt": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
              "embed": {"$type": "app.bsky.embed.external", "external": {"uri": url, "title": "NHL-tulokset ja suomalaiset – Punalamppu",
                                                                         "description": "Yön NHL-tulokset, suomalaisten tehot ja maalikoosteet suomeksi."}}}
    r = http(f"{pds}/com.atproto.repo.createRecord", {"repo": s["did"], "collection": "app.bsky.feed.post", "record": record},
             {"Authorization": f"Bearer {s['accessJwt']}"})
    return r.get("uri")


def bsky_avatar():
    """Päivittää Bluesky-profiilin kuvan tiedostosta assets/avatar.png (vain käsin käynnistettäessä)."""
    handle = (os.environ.get("BSKY_HANDLE") or "").strip().lstrip("@").strip()
    pw = (os.environ.get("BSKY_APP_PASSWORD") or "").strip()
    if not handle or not pw:
        print("bsky-avatar: tunnuksia ei asetettu")
        return
    if "." not in handle:
        handle += ".bsky.social"
    pds = "https://bsky.social/xrpc"
    s = http(f"{pds}/com.atproto.server.createSession", {"identifier": handle, "password": pw})
    auth = {"Authorization": f"Bearer {s['accessJwt']}"}
    img = open(os.path.join(ROOT, "assets", "avatar.png"), "rb").read()
    req = urllib.request.Request(f"{pds}/com.atproto.repo.uploadBlob", data=img, headers=dict(auth, **{"Content-Type": "image/png"}))
    with urllib.request.urlopen(req, timeout=60) as r:
        blob = json.loads(r.read().decode())["blob"]
    try:
        cur = http(f"{pds}/com.atproto.repo.getRecord?" + urllib.parse.urlencode({"repo": s["did"], "collection": "app.bsky.actor.profile", "rkey": "self"}), headers=auth)
        rec = cur.get("value") or {}
    except urllib.error.HTTPError:
        rec = {}
    rec["$type"] = "app.bsky.actor.profile"
    rec["avatar"] = blob
    rec.setdefault("displayName", "Punalamppu")
    http(f"{pds}/com.atproto.repo.putRecord", {"repo": s["did"], "collection": "app.bsky.actor.profile", "rkey": "self", "record": rec}, auth)
    print("bsky-avatar: profiilikuva päivitetty")


# ---------------------------------------------------------------- Telegram
def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def post_telegram(rec, url):
    tok = (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
    chat = (os.environ.get("TELEGRAM_CHAT_ID") or "").strip()
    if not tok or not chat:
        return None
    if not chat.startswith(("@", "-")) and not chat.isdigit():
        chat = "@" + chat
    title = rec["text"].split("\n")[0]
    lines = rec.get("lines") or []
    msg = f"<b>{esc(title)}</b>\n\n" + ("\n".join(f"• {esc(x)}" for x in lines[:14]) if lines else esc(rec["text"].split("\n", 1)[-1]))
    msg += f'\n\n<a href="{url}">Tulokset, tehot ja maalikoosteet →</a>'
    r = http(f"https://api.telegram.org/bot{tok}/sendMessage",
             {"chat_id": chat, "text": msg[:4000], "parse_mode": "HTML", "link_preview_options": {"is_disabled": True}})
    if not r.get("ok"):
        raise RuntimeError(r.get("description") or "tuntematon virhe")
    return str(r["result"].get("message_id"))


# ---------------------------------------------------------------- Threads
def _openssl(args, data, key):
    env = dict(os.environ, PL_KEY=key)
    p = subprocess.run(["openssl", "enc", "-aes-256-cbc", "-pbkdf2", "-iter", "200000", "-a", "-A", "-pass", "env:PL_KEY"] + args,
                       input=data.encode(), capture_output=True, env=env)
    if p.returncode != 0:
        raise RuntimeError("salaus epäonnistui")
    return p.stdout.decode().strip()


def threads_token(state):
    base = (os.environ.get("THREADS_TOKEN") or "").strip()
    if not base:
        return None
    tok = base
    if os.path.exists(TENC) and state.get("threads_base") == base[-8:]:
        try:
            tok = _openssl(["-d"], open(TENC).read().strip() + "\n", base)
        except Exception:
            tok = base
    # uusi tunnus, kun se on yli 40 päivää vanha (voimassa 60 päivää)
    since = state.get("threads_refreshed")
    age = (dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(since)).days if since else 999
    if age >= 40 or state.get("threads_base") != base[-8:]:
        try:
            r = http("https://graph.threads.net/refresh_access_token?" + urllib.parse.urlencode({"grant_type": "th_refresh_token", "access_token": tok}))
            if r.get("access_token"):
                tok = r["access_token"]
                open(TENC, "w").write(_openssl([], tok, base) + "\n")
                state["threads_refreshed"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes")
                state["threads_base"] = base[-8:]
                print("Threads: käyttötunnus uusittu")
        except urllib.error.HTTPError as e:
            print("Threads: tunnuksen uusinta ei onnistunut", e.code)
    return tok


def post_threads(rec, url, state):
    tok = threads_token(state)
    if not tok:
        return None
    title = rec["text"].split("\n")[0]
    body = rec["text"].split("\n", 1)[-1]
    text = f"{title}\n{body}"
    tail = f"\n\n{url}"
    if len(text) + len(tail) > 495:
        text = text[: 495 - len(tail) - 1].rsplit(",", 1)[0] + "…"
    gr = "https://graph.threads.net/v1.0"
    c = http(f"{gr}/me/threads", {"media_type": "TEXT", "text": text + tail, "access_token": tok}, form=True)
    time.sleep(5)
    r = http(f"{gr}/me/threads_publish", {"creation_id": c["id"], "access_token": tok}, form=True)
    return r.get("id")


# ---------------------------------------------------------------- pääohjelma
def main():
    rec = json.load(open(os.path.join(ROOT, "_site", "recap.json"), encoding="utf-8"))
    st = json.load(open(STATE)) if os.path.exists(STATE) else {}
    if not st and os.path.exists(OLD_BSKY):
        st = {"bsky": json.load(open(OLD_BSKY)).get("last")}
    force = os.environ.get("SOCIAL_FORCE") == "true"
    now = dt.datetime.now(HEL)
    if not force:
        if not rec.get("games") or rec.get("pending") or not rec.get("text"):
            print("Some: yön ottelut eivät ole vielä valmiita")
            return
        if not (6 <= now.hour < 13):
            print("Some: julkaistaan vain aamulla")
            return
    url = BASE + rec["url"]
    only = {x.strip() for x in (os.environ.get("SOCIAL_ONLY") or "").split(",") if x.strip()}
    changed = False
    for name, fn in (("bsky", lambda: post_bsky(rec, url)), ("telegram", lambda: post_telegram(rec, url)), ("threads", lambda: post_threads(rec, url, st))):
        if only and name not in only:
            continue
        if st.get(name) == rec["gameDate"] and not force:
            continue
        try:
            res = fn()
        except Exception as e:
            print(f"{name}: epäonnistui – {e}")
            continue
        if res is None:
            print(f"{name}: tunnuksia ei asetettu, ohitetaan")
            continue
        print(f"{name}: julkaistu {res}")
        st[name] = rec["gameDate"]
        changed = True
    if changed or os.path.exists(TENC):
        json.dump(st, open(STATE, "w"), indent=1)


if __name__ == "__main__":
    if os.environ.get("BSKY_AVATAR") == "true":
        try:
            bsky_avatar()
        except Exception as e:
            print("bsky-avatar epäonnistui:", e)
    try:
        main()
    except Exception as e:
        print("Some-julkaisu epäonnistui:", e)
    sys.exit(0)
