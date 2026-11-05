#!/usr/bin/env python3
"""Punalamppu – hakee NHL:n julkiset tulos- ja tilastotiedot ja rakentaa staattisen sivuston kansioon _site/.

Ajetaan GitHub Actionsissa (.github/workflows/update.yml). Käyttää vain Pythonin vakiokirjastoa.

Ympäristömuuttujat testaukseen:
  KA_FIXTURES=<kansio>  lukee rajapintavastaukset tiedostoista verkon sijaan
  KA_NOW=<ISO-aika>     korvaa nykyhetken (esim. 2026-11-05T04:00:00Z)
"""
import csv
import datetime as dt
import io
import html
import json
import os
import re
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET_XML
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "_site")
DATA = os.path.join(ROOT, "data")
WEB = os.path.join(ROOT, "web")
HEL = ZoneInfo("Europe/Helsinki")
ET = ZoneInfo("America/New_York")
API = "https://api-web.nhle.com/v1"
STATS = "https://api.nhle.com/stats/rest/en"
CFG = json.load(open(os.path.join(ROOT, "config.json"), encoding="utf-8"))
FIXTURES = os.environ.get("KA_FIXTURES")
FINAL = {"FINAL", "OFF"}
LIVE = {"LIVE", "CRIT"}
NOT_STARTED = {"FUT", "PRE"}

TEAMS = {
    "ANA": ("Anaheim Ducks", "Ducks"), "BOS": ("Boston Bruins", "Bruins"), "BUF": ("Buffalo Sabres", "Sabres"),
    "CAR": ("Carolina Hurricanes", "Hurricanes"), "CBJ": ("Columbus Blue Jackets", "Blue Jackets"),
    "CGY": ("Calgary Flames", "Flames"), "CHI": ("Chicago Blackhawks", "Blackhawks"), "COL": ("Colorado Avalanche", "Avalanche"),
    "DAL": ("Dallas Stars", "Stars"), "DET": ("Detroit Red Wings", "Red Wings"), "EDM": ("Edmonton Oilers", "Oilers"),
    "FLA": ("Florida Panthers", "Panthers"), "LAK": ("Los Angeles Kings", "Kings"), "MIN": ("Minnesota Wild", "Wild"),
    "MTL": ("Montréal Canadiens", "Canadiens"), "NJD": ("New Jersey Devils", "Devils"), "NSH": ("Nashville Predators", "Predators"),
    "NYI": ("New York Islanders", "Islanders"), "NYR": ("New York Rangers", "Rangers"), "OTT": ("Ottawa Senators", "Senators"),
    "PHI": ("Philadelphia Flyers", "Flyers"), "PIT": ("Pittsburgh Penguins", "Penguins"), "SEA": ("Seattle Kraken", "Kraken"),
    "SJS": ("San Jose Sharks", "Sharks"), "STL": ("St. Louis Blues", "Blues"), "TBL": ("Tampa Bay Lightning", "Lightning"),
    "TOR": ("Toronto Maple Leafs", "Maple Leafs"), "UTA": ("Utah Mammoth", "Mammoth"), "VAN": ("Vancouver Canucks", "Canucks"),
    "VGK": ("Vegas Golden Knights", "Golden Knights"), "WPG": ("Winnipeg Jets", "Jets"), "WSH": ("Washington Capitals", "Capitals"),
}
COLORS = {"ANA": "#F47A38", "BOS": "#B8860B", "BUF": "#003087", "CAR": "#CE1126", "CBJ": "#002654", "CGY": "#C8102E", "CHI": "#CF0A2C",
          "COL": "#6F263D", "DAL": "#006847", "DET": "#CE1126", "EDM": "#FF4C00", "FLA": "#C8102E", "LAK": "#3a3a3a", "MIN": "#154734",
          "MTL": "#AF1E2D", "NJD": "#CE1126", "NSH": "#B8860B", "NYI": "#00539B", "NYR": "#0038A8", "OTT": "#C52032", "PHI": "#F74902",
          "PIT": "#9c7c0c", "SEA": "#00837a", "SJS": "#006D75", "STL": "#002F87", "TBL": "#002868", "TOR": "#00205B", "UTA": "#4a8fc4",
          "VAN": "#00205B", "VGK": "#8a7a4f", "WPG": "#041E42", "WSH": "#C8102E"}
# Yhtenäinen kuvakesarja (24x24, viiva = currentColor)
ICONS = ('<svg width="0" height="0" style="position:absolute" aria-hidden="true">'
         '<symbol id="i-search" viewBox="0 0 24 24"><g fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.6-3.6"/></g></symbol>'
         '<symbol id="i-star" viewBox="0 0 24 24"><path fill="currentColor" d="M12 3.2l2.6 5.5 6 .8-4.4 4.1 1.1 5.9L12 16.6l-5.3 2.9 1.1-5.9L3.4 9.5l6-.8z"/></symbol>'
         '<symbol id="i-goalie" viewBox="0 0 24 24"><g fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"><path d="M3 19V8l3-3h12l3 3v11"/><path d="M3 19h18M7 19v-7h10v7M7 12l-3-3M17 12l3-3"/></g></symbol>'
         '<symbol id="i-pin" viewBox="0 0 24 24"><g fill="none" stroke="currentColor" stroke-width="2"><path d="M12 21s-6.5-6.2-6.5-11A6.5 6.5 0 0 1 18.5 10c0 4.8-6.5 11-6.5 11z"/><circle cx="12" cy="10" r="2.3"/></g></symbol>'
         '<symbol id="i-play" viewBox="0 0 24 24"><path fill="currentColor" d="M8 5.5v13a1 1 0 0 0 1.5.86l10.4-6.5a1 1 0 0 0 0-1.72L9.5 4.64A1 1 0 0 0 8 5.5z"/></symbol>'
         '<symbol id="i-clock" viewBox="0 0 24 24"><g fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/></g></symbol>'
         '<symbol id="i-chev" viewBox="0 0 24 24"><path fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" d="m9 6 6 6-6 6"/></symbol>'
         '</svg>')


def ic(name, cls="ic"):
    return f'<svg class="{cls}" aria-hidden="true"><use href="#i-{name}"/></svg>'


FLAG = '<span class="flag" aria-hidden="true"></span>'


def tbadge(a, cls="badge"):
    if not a:
        return f'<span class="{cls}" style="background:#2a3646" title="Ei NHL-joukkuetta">–</span>'
    return f'<span class="{cls}" style="background:{COLORS.get(a, "#445")}" title="{esc(TEAMS.get(a, (a,))[0])}">{esc(a)}</span>'


NAV = [("/", "Tulokset"), ("/otteluohjelma/", "Ohjelma"), ("/suomalaiset/", "Suomalaiset"), ("/pisteporssi/", "Pistepörssi"),
       ("/sarjataulukko/", "Sarjataulukko"), ("/ottelut/", "Arkisto")]


def site_header(path=""):
    def on(h):
        return h == path or (h != "/" and path.startswith(h)) or (h == "/ottelut/" and path.startswith("/ottelut/"))
    nav = "".join(f'<a href="{h}"{" class=on" if on(h) else ""}>{FLAG if h == "/suomalaiset/" else ""}{t}</a>' for h, t in NAV)
    return (ICONS + '<header class="top"><a class="brand" href="/" aria-label="Punalamppu – etusivu"><img src="/logo-mark.svg" alt="" width="36" height="36"><span>PUNALAMPPU</span></a>'
            f'<form class="q" action="/" method="get" role="search">{ic("search")}<input type="search" name="q" placeholder="Hae pelaajaa tai joukkuetta" aria-label="Hae pelaajaa tai joukkuetta"></form></header>'
            f'<nav class="pills" aria-label="Päävalikko">{nav}</nav>')


def boxify(html):
    """Jakaa artikkelin <h2>-otsikoiden kohdalta korttiosioiksi."""
    m = re.match(r"(?s)^\s*<article>(.*)</article>\s*$", html)
    inner = m.group(1) if m else html
    parts = re.split(r"(?=<h2[ >])", inner)
    out = parts[0]
    parts = [re.sub(r"(?s)(?<!<div class='tw'>)(<table class='t'>.*?</table>)", r"<div class='tw'>\1</div>", x) for x in parts]
    for prt in parts[1:]:
        out += f'<section class="box">{prt}</section>'
    return f"<article>{out}</article>" if m else out


ALIAS = {"LA": "LAK", "TB": "TBL", "NJ": "NJD", "SJ": "SJS", "UTAH": "UTA"}
CONF = {"Eastern": "Itä", "Western": "Länsi", "E": "Itä", "W": "Länsi"}
DIV_ORDER = ["Atlantic", "Metropolitan", "Central", "Pacific"]


# ---------------------------------------------------------------- apurit
def log(*a):
    print("[build]", *a, file=sys.stderr)


def L(v):
    """NHL-rajapinta palauttaa monet tekstit muodossa {"default": "..."}."""
    if isinstance(v, dict):
        return v.get("default") or next(iter(v.values()), None)
    return v


def team(v):
    t = (L(v) or "").upper()
    return ALIAS.get(t, t)


def fixture_path(url):
    name = re.sub(r"[^A-Za-z0-9]+", "_", url.split("://", 1)[-1]).strip("_")
    return os.path.join(FIXTURES, name[:180] + ".json")


def get(url, required=False):
    if FIXTURES:
        p = fixture_path(url)
        if os.path.exists(p):
            return json.load(open(p, encoding="utf-8"))
        log("fixture puuttuu:", url)
        if required:
            raise RuntimeError("fixture puuttuu: " + url)
        return None
    req = urllib.request.Request(url, headers={"User-Agent": CFG["userAgent"], "Accept": "application/json"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=25) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            log("HTTP", e.code, url)
        except Exception as e:  # verkkovirhe
            log("virhe", type(e).__name__, url)
        time.sleep(2 ** attempt)
    if required:
        raise RuntimeError("haku epäonnistui: " + url)
    return None


def get_text(url, ext=".xml"):
    if FIXTURES:
        p = fixture_path(url)[:-5] + ext
        return open(p, encoding="utf-8").read() if os.path.exists(p) else None
    req = urllib.request.Request(url, headers={"User-Agent": CFG["userAgent"]})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.read().decode("utf-8")
    except Exception as e:
        log("virhe", type(e).__name__, url)
        return None


NICK = {v[1].lower(): k for k, v in TEAMS.items()}
NICK.update({"utah": "UTA", "canadiens": "MTL", "golden knights": "VGK", "maple leafs": "TOR", "blue jackets": "CBJ", "red wings": "DET"})
MONTHS_EN = {m: i + 1 for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august",
                                             "september", "october", "november", "december"])}


def fetch_videos():
    """NHL:n virallisen YouTube-kanavan syötteestä ottelukoosteiden video-id:t.
    Otsikkomuoto: "NHL Highlights | Sharks vs. Kings | November 04, 2026". Tallennetaan data/videos.json."""
    path = os.path.join(DATA, "videos.json")
    known = load_json(path, {})
    cid = CFG.get("youtubeChannelId")
    if not cid:
        return known
    xml = get_text(f"https://www.youtube.com/feeds/videos.xml?channel_id={cid}")
    if not xml:
        return known
    try:
        root = ET_XML.fromstring(xml)
    except ET_XML.ParseError:
        return known
    ns = {"a": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015"}
    pat = re.compile(r"NHL Highlights\s*\|\s*(.+?)\s+(?:vs\.?|at|@)\s+(.+?)\s*\|\s*([A-Za-z]+)\s+(\d{1,2}),\s*(\d{4})", re.I)
    changed = False
    for e in root.findall("a:entry", ns):
        title = (e.findtext("a:title", default="", namespaces=ns) or "").strip()
        vid = e.findtext("yt:videoId", default="", namespaces=ns)
        m = pat.search(title)
        if not (m and vid):
            continue
        a, h = NICK.get(m.group(1).strip().lower()), NICK.get(m.group(2).strip().lower())
        mon = MONTHS_EN.get(m.group(3).lower())
        if not (a and h and mon):
            continue
        key = f"{m.group(5)}-{mon:02d}-{int(m.group(4)):02d}|{a}|{h}"
        if known.get(key) != vid:
            known[key] = vid
            changed = True
    if changed:
        known = dict(sorted(known.items())[-600:])
        save_json(path, known)
    return known


def now_utc():
    if os.environ.get("KA_NOW"):
        return dt.datetime.fromisoformat(os.environ["KA_NOW"].replace("Z", "+00:00"))
    return dt.datetime.now(dt.timezone.utc)


def season_id(d):
    y = d.year if d.month >= 7 else d.year - 1
    return f"{y}{y + 1}"


def load_json(path, default):
    try:
        return json.load(open(path, encoding="utf-8"))
    except Exception:
        return default


def save_json(path, obj, pretty=True):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1 if pretty else None, separators=None if pretty else (",", ":"))


def full_name(p):
    fn, ln = L(p.get("firstName")), L(p.get("lastName"))
    if fn and ln:
        return f"{fn} {ln}"
    return L(p.get("name")) or L(p.get("skaterFullName")) or L(p.get("goalieFullName")) or ""


def slugify(s):
    s = s.lower()
    for a, b in (("ä", "a"), ("ö", "o"), ("å", "a"), ("é", "e"), ("ü", "u")):
        s = s.replace(a, b)
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def fi_time(iso):
    t = dt.datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(HEL)
    return t.strftime("%H.%M")


def esc(s):
    return html.escape(str(s if s is not None else ""), quote=True)


# ---------------------------------------------------------------- tiedot
def stats_rows(kind, report, sid):
    q = urllib.parse.quote(f"gameTypeId=2 and seasonId={sid}")
    url = f"{STATS}/{kind}/{report}?isAggregate=false&isGame=false&limit=-1&cayenneExp={q}"
    d = get(url)
    return (d or {}).get("data") or []


def last_team(abbrs):
    parts = [p.strip() for p in str(abbrs or "").split(",") if p.strip()]
    return team(parts[-1]) if parts else ""


NAMES = {}  # playerId -> koko nimi (tilastopalvelusta)
FIN_IDS = set()
FINN_PID = {}  # nimi -> playerId
PROFILES = {}  # playerId -> profiili
NAME_FIX = CFG.get("nameFixes") or {}


def fixname(n):
    """NHL:n tilastopalvelu palauttaa nimet ilman ääkkösiä (Teravainen) – korjataan config.json:n nameFixes-listalla."""
    if not n:
        return n
    for a, b in NAME_FIX.items():
        n = re.sub(r"\b" + re.escape(a) + r"\b", b, n)
    return n


def pname(obj):
    return NAMES.get(obj.get("playerId")) or fixname(full_name(obj))


def merge_rows(rows, sum_keys):
    """isAggregate=false voi palauttaa pelaajalle useamman rivin (seurasiirto) – yhdistetään playerId:n mukaan."""
    out = {}
    for r in rows:
        pid = r.get("playerId")
        if pid not in out:
            out[pid] = dict(r)
            out[pid]["_teams"] = [r.get("teamAbbrevs") or r.get("teamAbbrev") or ""]
            continue
        o = out[pid]
        for k in sum_keys:
            o[k] = (o.get(k) or 0) + (r.get(k) or 0)
        o["_teams"].append(r.get("teamAbbrevs") or r.get("teamAbbrev") or "")
        if (r.get("gamesPlayed") or 0) > (o.get("_maxgp") or 0):
            o["_maxgp"] = r.get("gamesPlayed") or 0
            for k in ("savePct", "goalsAgainstAverage"):
                if k in r:
                    o[k] = r[k]
    return list(out.values())


def leader_teams():
    """Varalähde pelaajan nykyiselle joukkueelle: NHL:n pörssilistat sisältävät teamAbbrev-kentän."""
    m = {}
    for path, cats in (("skater-stats-leaders", "points"), ("goalie-stats-leaders", "wins")):
        d = get(f"{API}/{path}/current?categories={cats}&limit=-1") or {}
        for p in d.get(cats) or []:
            if p.get("id") and p.get("teamAbbrev"):
                m[p["id"]] = team(p["teamAbbrev"])
    return m


def fetch_players(sid):
    """Kenttäpelaajat, maalivahdit ja suomalaiset NHL:n tilastopalvelusta."""
    sk = merge_rows(stats_rows("skater", "summary", sid), ("gamesPlayed", "goals", "assists", "points"))
    gk = merge_rows(stats_rows("goalie", "summary", sid), ("gamesPlayed", "wins", "losses", "otLosses", "shutouts"))
    skb = {r.get("playerId"): r for r in stats_rows("skater", "bios", sid)}
    gkb = {r.get("playerId"): r for r in stats_rows("goalie", "bios", sid)}
    lt = None

    def team_of(r, bio):
        nonlocal lt
        t = team((bio or {}).get("currentTeamAbbrev")) if (bio or {}).get("currentTeamAbbrev") else ""
        if not t:
            t = last_team(",".join(x for x in r.get("_teams", []) if x))
        if not t:
            if lt is None:
                lt = leader_teams()
            t = lt.get(r.get("playerId"), "")
        return t

    def is_fin(bio):
        return bool(bio) and ("FIN" in (bio.get("nationalityCode"), bio.get("birthCountryCode")))

    skaters, finns, fin_ids = [], [], set()
    for r in sk:
        pid = r.get("playerId")
        name = fixname(r.get("skaterFullName") or full_name(r))
        NAMES[pid] = name
        t = team_of(r, skb.get(pid))
        row = [name, t, r.get("gamesPlayed") or 0, r.get("goals") or 0, r.get("assists") or 0, r.get("points") or 0]
        skaters.append(row)
        if is_fin(skb.get(pid)):
            fin_ids.add(pid)
            FINN_PID[name] = pid
            pos = "P" if (r.get("positionCode") or skb[pid].get("positionCode")) == "D" else "H"
            finns.append([name, t, pos] + row[2:] + [slugify(name)])
    skaters.sort(key=lambda x: (-x[5], -x[3], x[2]))
    finns.sort(key=lambda x: (-(x[6] or 0), -(x[4] or 0)))

    goalies, fgk = [], []
    for r in gk:
        pid = r.get("playerId")
        name = fixname(r.get("goalieFullName") or full_name(r))
        NAMES[pid] = name
        t = team_of(r, gkb.get(pid))
        sv = r.get("savePct")
        gaa = r.get("goalsAgainstAverage")
        svs = f"{sv:.3f}".lstrip("0") if isinstance(sv, (int, float)) else "–"
        gaas = f"{gaa:.2f}" if isinstance(gaa, (int, float)) else "–"
        row = [name, t, r.get("gamesPlayed") or 0, r.get("wins") or 0, r.get("losses") or 0, r.get("otLosses") or 0, svs, gaas, r.get("shutouts") or 0]
        goalies.append(row)
        if is_fin(gkb.get(pid)):
            fin_ids.add(pid)
            FINN_PID[name] = pid
            fgk.append(row[:8] + [slugify(name)])
    goalies.sort(key=lambda x: -x[2])
    FIN_IDS.update(fin_ids)
    return skaters[:100], goalies, finns, fgk, fin_ids


def fetch_roster_finns(today):
    """Kaikki NHL-kokoonpanoissa olevat suomalaiset (myös loukkaantuneet ja ne, jotka eivät ole vielä pelanneet).
    Kokoonpanot haetaan kerran päivässä ja tallennetaan data/rosters.json."""
    path = os.path.join(DATA, "rosters.json")
    cache = load_json(path, {})
    if cache.get("date") != today.isoformat() or not cache.get("players") or "allIds" not in cache:
        players, all_ids = [], []
        for abbr in TEAMS:
            d = get(f"{API}/roster/{abbr}/current") or {}
            for grp, pos in (("forwards", "H"), ("defensemen", "P"), ("goalies", "MV")):
                for p in d.get(grp) or []:
                    if p.get("id"):
                        all_ids.append(p["id"])
                    if (p.get("birthCountry") or "").upper() != "FIN":
                        continue
                    players.append({"id": p.get("id"), "name": fixname(full_name(p)), "team": abbr, "pos": pos})
        if players:
            cache = {"date": today.isoformat(), "players": players, "allIds": sorted(set(all_ids))}
            save_json(path, cache)
    ROSTER_IDS.clear()
    ROSTER_IDS.update(cache.get("allIds") or [])
    return cache.get("players") or []


ROSTER_IDS = set()


def fetch_profiles(pids, today):
    """Pelaajien taustatiedot ja uratilastot (/v1/player/<id>/landing), päivitetään kerran päivässä."""
    out = {}
    pdir = os.path.join(DATA, "players")
    os.makedirs(pdir, exist_ok=True)
    for pid in pids:
        if not pid:
            continue
        path = os.path.join(pdir, f"{pid}.json")
        pr = load_json(path, {})
        if pr.get("_fetched") != today.isoformat():
            d = get(f"{API}/player/{pid}/landing")
            if d:
                keep = {k: d.get(k) for k in ("playerId", "firstName", "lastName", "currentTeamAbbrev", "position", "sweaterNumber",
                                               "birthDate", "birthCity", "birthStateProvince", "birthCountry", "heightInCentimeters",
                                               "weightInKilograms", "shootsCatches", "draftDetails", "featuredStats", "careerTotals",
                                               "last5Games", "isActive")}
                keep["seasonTotals"] = [x for x in (d.get("seasonTotals") or []) if x.get("leagueAbbrev") == "NHL"]
                keep["_fetched"] = today.isoformat()
                pr = keep
                save_json(path, pr)
        if pr:
            out[pid] = pr
    return out


# ---------------------------------------------------------------- MoneyPuck (edistyneet tilastot)
# MoneyPuck.com: "free to use for non-commercial purposes" kun MoneyPuck.com mainitaan lähteenä.
# Käytetään vain datasivulla (moneypuck.com/data.htm) listattuja valmiita CSV-tiedostoja,
# haetaan enintään kahdesti vuorokaudessa ja tallennetaan vain suomalaisten rivit.
MP = {}
MP_URL = "https://moneypuck.com/moneypuck/playerData/seasonSummary/{y}/regular/{kind}.csv"


def _f(row, *keys):
    for k in keys:
        v = row.get(k)
        if v not in (None, ""):
            try:
                return float(v)
            except ValueError:
                pass
    return None


def fetch_moneypuck(sid, pids, now):
    path = os.path.join(DATA, "moneypuck.json")
    cache = load_json(path, {})
    try:
        age = (now - dt.datetime.fromisoformat(cache.get("_fetched"))).total_seconds() / 3600
    except Exception:
        age = 1e9
    want = {str(p) for p in pids if p}
    if age < 12 and cache.get("season") == sid and want <= set(cache.get("skaters", {})) | set(cache.get("goalies", {})) | set(cache.get("_missing", [])):
        return cache
    y = str(sid)[:4]
    out = {"season": sid, "_fetched": now.isoformat(timespec="minutes"), "skaters": {}, "goalies": {}}
    for kind in ("skaters", "goalies"):
        txt = get_text(MP_URL.format(y=y, kind=kind), ext=".csv")
        if not txt:
            log("MoneyPuck: ei dataa", kind)
            if cache.get("season") == sid:
                out[kind] = cache.get(kind, {})
            continue
        for row in csv.DictReader(io.StringIO(txt)):
            pid = (row.get("playerId") or "").strip()
            if pid not in want:
                continue
            sit = row.get("situation")
            if sit not in ("all", "5on5", "5on4"):
                continue
            d = out[kind].setdefault(pid, {})
            if kind == "skaters":
                d[sit] = {"gp": _f(row, "games_played"), "toi": _f(row, "icetime"),
                          "xg": _f(row, "I_F_xGoals"), "g": _f(row, "I_F_goals"),
                          "oxf": _f(row, "OnIce_F_xGoals"), "oxa": _f(row, "OnIce_A_xGoals"),
                          "oxp": _f(row, "onIce_xGoalsPercentage")}
            else:
                d[sit] = {"gp": _f(row, "games_played"), "xga": _f(row, "xGoals"), "ga": _f(row, "goals"), "sog": _f(row, "ongoal")}
    out["_missing"] = sorted(want - set(out["skaters"]) - set(out["goalies"]))
    log("MoneyPuck:", len(out["skaters"]), "kenttäpelaajaa,", len(out["goalies"]), "maalivahtia")
    save_json(path, out)
    return out


def fi_num(v, d=1, sign=False):
    if v is None:
        return "–"
    s = f"{v:+.{d}f}" if sign else f"{v:.{d}f}"
    return s.replace(".", ",").replace("-", "−")


def mp_block(name, pid, is_goalie, data):
    if not pid:
        return ""
    src = ("<p class='mute'>Data: <a href='https://moneypuck.com/' rel='noopener'>MoneyPuck.com</a> "
           "(edistyneet tilastot, runkosarja). Maaliodottama (xG) kertoo, montako maalia laukausten paikkojen ja tyypin perusteella "
           "olisi keskimäärin odottanut syntyvän.</p>")
    if is_goalie:
        a = (MP.get("goalies", {}).get(str(pid)) or {}).get("all")
        if not a or a.get("xga") is None or a.get("ga") is None:
            return ""
        gsax = a["xga"] - a["ga"]
        allg = sorted(((v.get("all") or {}).get("xga", 0) - (v.get("all") or {}).get("ga", 0), k) for k, v in MP.get("goalies", {}).items()
                      if (v.get("all") or {}).get("xga") is not None)
        rank = next((i + 1 for i, (_, k) in enumerate(sorted(allg, reverse=True)) if k == str(pid)), None)
        word = "enemmän" if gsax >= 0 else "vähemmän"
        rows = [("Odotetut päästetyt maalit (xGA)", fi_num(a["xga"])), ("Päästetyt maalit", fi_num(a["ga"], 0)),
                ("Torjutut maalit yli odotetun (GSAx)", f"<b>{fi_num(gsax, 1, True)}</b>")]
        if rank and len(allg) > 1:
            rows.append(("Sija suomalaisten maalivahtien GSAx-vertailussa", f"{rank}./{len(allg)}"))
        lead = f"<p>{esc(name)} on torjunut tällä kaudella {fi_num(abs(gsax))} maalia {word} kuin laukausten laatu olisi antanut odottaa.</p>"
    else:
        m = MP.get("skaters", {}).get(str(pid)) or {}
        a, ev, pp = m.get("all"), m.get("5on5") or {}, m.get("5on4") or {}
        if not a or a.get("xg") is None:
            return ""
        diff = (a.get("g") or 0) - a["xg"]
        allx = sorted((((v.get("all") or {}).get("xg") or 0), k) for k, v in MP.get("skaters", {}).items())
        rank = next((i + 1 for i, (_, k) in enumerate(sorted(allx, reverse=True)) if k == str(pid)), None)
        oxp = ev.get("oxp")
        if oxp is None and ev.get("oxf") is not None and (ev.get("oxf") or 0) + (ev.get("oxa") or 0) > 0:
            oxp = ev["oxf"] / (ev["oxf"] + ev["oxa"])
        rows = [("Maaliodottama (xG), kaikki tilanteet", f"<b>{fi_num(a['xg'])}</b>"), ("Toteutuneet maalit", fi_num(a.get("g"), 0)),
                ("Maalit yli/alle odotetun", fi_num(diff, 1, True)),
                ("xG tasakentällisin (5v5)", fi_num(ev.get("xg"))), ("xG ylivoimalla (5v4)", fi_num(pp.get("xg")))]
        if oxp is not None:
            rows.append(("Joukkueen xG-osuus pelaajan ollessa kentällä (5v5)", fi_num(oxp * 100) + " %"))
        if rank and len(allx) > 1:
            rows.append(("Sija suomalaisten xG-vertailussa", f"{rank}./{len(allx)}"))
        lead = (f"<p>{esc(name)} on tehnyt {fi_num(a.get('g'), 0)} maalia, kun maaliodottama on {fi_num(a['xg'])}. "
                + ("Hän on siis viimeistellyt odotettua paremmin.</p>" if diff > 0.5 else "Hän on siis tehnyt odotettua vähemmän maaleja.</p>" if diff < -0.5 else "Maalit vastaavat siis odotettua.</p>"))
    return ("<h2>Edistyneet tilastot</h2>" + lead + "<table class='t'>" + "".join(f"<tr><td>{k}</td><td>{v}</td></tr>" for k, v in rows)
            + "</table>" + src)


def fetch_standings():
    d = get(f"{API}/standings/now") or {}
    divs = {}
    for r in d.get("standings") or []:
        dn = L(r.get("divisionName")) or "?"
        divs.setdefault(dn, {"name": dn, "conf": CONF.get(L(r.get("conferenceName")) or "", "?"), "teams": []})
        divs[dn]["teams"].append([team(r.get("teamAbbrev")), r.get("gamesPlayed", 0), r.get("wins", 0), r.get("losses", 0),
                                  r.get("otLosses", 0), r.get("points", 0), r.get("goalFor", 0), r.get("goalAgainst", 0)])
    return [divs[k] for k in DIV_ORDER if k in divs] + [v for k, v in divs.items() if k not in DIV_ORDER]


def fetch_upcoming(et_today):
    d = get(f"{API}/schedule/{et_today.isoformat()}") or {}
    ups = []
    for day in d.get("gameWeek") or []:
        for g in day.get("games") or []:
            if g.get("gameState") not in NOT_STARTED:
                continue
            e = {"day": day.get("date"), "away": team(g["awayTeam"].get("abbrev")), "home": team(g["homeTeam"].get("abbrev")),
                 "start": g.get("startTimeUTC")}
            if g.get("neutralSite"):
                e["venue"] = L(g.get("venue")) or ""
            ups.append(e)
    return ups


def goal_entry(goal, fin_ids):
    pd = goal.get("periodDescriptor") or {}
    ptype = pd.get("periodType") or "REG"
    if ptype == "SO":
        return None
    p = "JA" if ptype == "OT" else str(goal.get("period") or pd.get("number") or "")
    strength = (goal.get("strength") or "").lower()
    tag = {"pp": "YV", "sh": "AV"}.get(strength, "")
    if (goal.get("goalModifier") or "") == "empty-net":
        tag = "TM"
    return {
        "p": p, "t": goal.get("timeInPeriod") or "", "team": team(goal.get("teamAbbrev")),
        "who": pname(goal), "tag": tag,
        "ast": [pname(a) for a in goal.get("assists") or []],
        "fin": goal.get("playerId") in fin_ids,
    }


def game_details(gid):
    """Maalivahdit (boxscore) ja kolme tähteä (landing) päättyneestä ottelusta."""
    out = {"goalies": "", "threeStars": [], "venue": "", "finStats": []}
    bx = get(f"{API}/gamecenter/{gid}/boxscore") or {}
    parts = []
    abbrs = {side: team((bx.get(side) or {}).get("abbrev")) for side in ("awayTeam", "homeTeam")}
    for side in ("awayTeam", "homeTeam"):
        tm = abbrs[side]
        opp = abbrs["homeTeam" if side == "awayTeam" else "awayTeam"]
        pg = (bx.get("playerByGameStats") or {}).get(side) or {}
        for grp in ("forwards", "defense"):
            for p in pg.get(grp) or []:
                if p.get("playerId") in FIN_IDS:
                    out["finStats"].append({"name": NAMES.get(p.get("playerId")) or fixname(L(p.get("name"))), "team": tm, "opp": opp,
                                            "pos": "P" if grp == "defense" else "H", "g": p.get("goals") or 0, "a": p.get("assists") or 0,
                                            "p": p.get("points") if p.get("points") is not None else (p.get("goals") or 0) + (p.get("assists") or 0),
                                            "pm": p.get("plusMinus"), "sog": p.get("sog", p.get("shots")), "toi": p.get("toi") or ""})
        for g in pg.get("goalies") or []:
            if g.get("playerId") in FIN_IDS and (g.get("toi") or "00:00") not in ("00:00", "0:00"):
                sv, sa = g.get("saves"), g.get("shotsAgainst")
                if (sv is None or sa is None) and g.get("saveShotsAgainst"):
                    try:
                        sv, sa = (int(x) for x in str(g["saveShotsAgainst"]).split("/"))
                    except ValueError:
                        pass
                out["finStats"].append({"name": NAMES.get(g.get("playerId")) or fixname(L(g.get("name"))), "team": tm, "opp": opp,
                                        "pos": "MV", "saves": sv, "shots": sa, "dec": g.get("decision") or "", "toi": g.get("toi") or ""})
        for gk in ((bx.get("playerByGameStats") or {}).get(side) or {}).get("goalies") or []:
            if not gk.get("decision") and not gk.get("starter"):
                continue
            saves = gk.get("saves")
            if saves is None and gk.get("saveShotsAgainst"):
                saves = str(gk["saveShotsAgainst"]).split("/")[0]
            if saves is None:
                continue
            parts.append(f"{NAMES.get(gk.get('playerId')) or L(gk.get('name'))} ({tm}) {saves} torjuntaa")
    out["goalies"] = " · ".join(parts)
    out["venue"] = L(bx.get("venue")) or ""
    ld = get(f"{API}/gamecenter/{gid}/landing") or {}
    for s in ((ld.get("summary") or {}).get("threeStars") or []):
        out["threeStars"].append({
            "star": s.get("star"), "name": NAMES.get(s.get("playerId")) or full_name(s) or L(s.get("name")), "team": team(s.get("teamAbbrev")),
            "pos": s.get("position"), "goals": s.get("goals"), "assists": s.get("assists"), "points": s.get("points"),
            "svp": s.get("savePctg"),
        })
    return out


def star_line(s):
    if s.get("pos") == "G":
        return f"torjunta-% {s['svp']:.3f}".replace("0.", ".") if isinstance(s.get("svp"), (int, float)) else "maalivahti"
    g, a = s.get("goals") or 0, s.get("assists") or 0
    bits = []
    if g:
        bits.append(f"{g} maali" + ("a" if g > 1 else ""))
    if a:
        bits.append(f"{a} syöttö" + ("ä" if a > 1 else ""))
    return ", ".join(bits) or "–"


def night_stars(games):
    cands = []
    for g in games:
        for s in g.get("threeStars") or []:
            if s.get("pos") == "G":
                score = 3.5 + ((s.get("svp") or 0.9) - 0.9) * 20
            else:
                score = (s.get("points") or 0) * 1.5 + (s.get("goals") or 0)
            score += (4 - (s.get("star") or 3)) * 0.3
            cands.append((score, s))
    cands.sort(key=lambda x: -x[0])
    seen, out = set(), []
    for _, s in cands:
        if s["name"] in seen:
            continue
        seen.add(s["name"])
        out.append({"name": s["name"], "team": s["team"], "line": star_line(s)})
        if len(out) == 3:
            break
    return out


def game_note(goals, fin_names):
    per = {}
    for x in goals:
        if x["who"]:
            per.setdefault(x["who"], [0, 0, x["team"]])[0] += 1
        for a in x.get("ast") or []:
            per.setdefault(a, [0, 0, x["team"]])[1] += 1
    notes = [f"{n} hattutemppu" for n, v in per.items() if v[0] >= 3]
    fins = [f"{n.split(' ')[-1]} {v[0]}+{v[1]}" for n, v in per.items() if n in fin_names]
    if fins:
        notes.append("Suomalaiset: " + ", ".join(fins))
    return " · ".join(notes)


def pending_status(g):
    st = g.get("gameState")
    if st in NOT_STARTED:
        return f"Alkaa klo {fi_time(g['startTimeUTC'])}" if g.get("startTimeUTC") else "Ei alkanut"
    if st in LIVE:
        pd = g.get("periodDescriptor") or {}
        clock = g.get("clock") or {}
        if pd.get("periodType") == "SO":
            return "Voittolaukaukset"
        if clock.get("inIntermission"):
            return f"{pd.get('number', '')}. erätauko"
        if pd.get("periodType") == "OT":
            return f"Jatkoaika · {clock.get('timeRemaining', '')}".strip(" ·")
        return f"{pd.get('number', '')}. erä · {clock.get('timeRemaining', '')}".strip(" ·")
    return {"PPD": "Siirretty", "SUSP": "Keskeytetty"}.get(st, "Kesken")


# ---------------------------------------------------------------- pääohjelma
def collect():
    now = now_utc()
    et_today = now.astimezone(ET).date()
    hel_today = now.astimezone(HEL).date()
    sid = season_id(et_today)
    prev = get(CFG["baseUrl"].rstrip("/") + "/data.json") if not FIXTURES else None
    prev = prev if isinstance(prev, dict) else {}

    # Yön pelipäivä: tämän päivän otteluita näytetään vasta kun ensimmäinen on alkanut.
    sc_today = get(f"{API}/score/{et_today.isoformat()}") or {}
    started = any(g.get("gameState") not in NOT_STARTED for g in sc_today.get("games") or [])
    if started:
        gd, sc = et_today, sc_today
    else:
        gd = et_today - dt.timedelta(days=1)
        sc = get(f"{API}/score/{gd.isoformat()}") or {}

    try:
        skaters, goalies, finns, fgk, fin_ids = fetch_players(sid)
    except Exception as e:
        log("tilastot epäonnistuivat", e)
        skaters, goalies, finns, fgk, fin_ids = [], [], [], [], set()
    if not skaters and prev:  # varmistus: pidä edelliset tilastot
        skaters, goalies = prev.get("skaters", []), prev.get("goalies", [])
        finns = [f[:7] + [slugify(f[0])] for f in prev.get("finns", [])]
        fgk = [f[:8] + [slugify(f[0])] for f in prev.get("finnGoalies", [])]
    try:
        roster = fetch_roster_finns(hel_today)
    except Exception as e:
        log("kokoonpanot epäonnistuivat", e)
        roster = []
    have = {f[0] for f in finns} | {f[0] for f in fgk}
    for r in roster:
        FIN_IDS.add(r["id"])
        fin_ids.add(r["id"])
        if r["name"] in have:
            # korjaa joukkue kokoonpanon mukaan (seurasiirrot)
            for f in finns + fgk:
                if f[0] == r["name"] and r["team"]:
                    f[1] = r["team"]
            continue
        FINN_PID[r["name"]] = r["id"]
        if r["pos"] == "MV":
            fgk.append([r["name"], r["team"], 0, 0, 0, 0, "–", "–", slugify(r["name"])])
        else:
            finns.append([r["name"], r["team"], r["pos"], 0, 0, 0, 0, slugify(r["name"])])
    # kauden tilastoissa mutta ei nyt minkään joukkueen NHL-kokoonpanossa (esim. farmissa)
    finn_off = sorted(f[0] for f in finns + fgk
                      if len(ROSTER_IDS) > 500 and f[1] and FINN_PID.get(f[0]) and FINN_PID[f[0]] not in ROSTER_IDS)
    # paljon haetut suomalaiset, jotka eivät juuri nyt ole NHL-kokoonpanossa (config.json: extraFinns)
    have = {f[0] for f in finns} | {f[0] for f in fgk}
    extra = []
    for e in CFG.get("extraFinns") or []:
        if e.get("name") in have or not e.get("id"):
            continue
        FINN_PID[e["name"]] = e["id"]
        FIN_IDS.add(e["id"])
        row = [e["name"], "", e.get("pos", "H"), 0, 0, 0, 0, slugify(e["name"])]
        finns.append(row)
        extra.append(row)
    try:
        PROFILES.update(fetch_profiles([FINN_PID.get(f[0]) for f in finns + fgk], hel_today))
    except Exception as e:
        log("profiilit epäonnistuivat", e)
    try:
        MP.update(fetch_moneypuck(sid, [FINN_PID.get(f[0]) for f in finns + fgk], now))
    except Exception as e:
        log("MoneyPuck epäonnistui", e)
    for row in extra:
        pr = PROFILES.get(FINN_PID[row[0]]) or {}
        got = fixname(full_name(pr)) if pr else ""
        if got and got != row[0]:  # väärä id config.json:ssa – ei näytetä väärän pelaajan tietoja
            log("extraFinns: id ei vastaa nimeä", row[0], got)
            PROFILES.pop(FINN_PID[row[0]], None)
        elif pr.get("currentTeamAbbrev"):
            row[1] = team(pr["currentTeamAbbrev"])
    fin_names = {f[0] for f in finns} | {f[0] for f in fgk}

    videos = fetch_videos()
    arch_path = os.path.join(DATA, "archive", f"{gd.isoformat()}.json")
    arch = load_json(arch_path, {"gameDate": gd.isoformat(), "games": {}})
    games, pending = [], []
    for g in sc.get("games") or []:
        a, h = g.get("awayTeam") or {}, g.get("homeTeam") or {}
        base = {"id": g.get("id"), "away": team(a.get("abbrev")), "home": team(h.get("abbrev")),
                "awayScore": a.get("score"), "homeScore": h.get("score"), "start": g.get("startTimeUTC")}
        if g.get("gameState") in FINAL:
            key = str(g.get("id"))
            old = arch["games"].get(key) or {}
            goals = [x for x in (goal_entry(x, fin_ids) for x in g.get("goals") or []) if x]
            lpt = (g.get("gameOutcome") or {}).get("lastPeriodType") or (g.get("periodDescriptor") or {}).get("periodType")
            det = old.get("details")
            if not det or "finStats" not in det or re.match(r"^[A-Z]\. ", det.get("goalies", "")):
                det = game_details(g.get("id"))
            recap = g.get("threeMinRecap") or ""
            entry = dict(base, final={"OT": "JA", "SO": "VL"}.get(lpt, ""), goals=goals, goalies=det.get("goalies", ""),
                         threeStars=det.get("threeStars", []), venue=det.get("venue", ""), finStats=det.get("finStats", []),
                         note=game_note(goals, fin_names),
                         recapUrl=("https://www.nhl.com" + recap) if recap.startswith("/") else recap,
                         videoId=videos.get(f"{gd.isoformat()}|{base['away']}|{base['home']}") or old.get("videoId") or "",
                         details=det)
            arch["games"][key] = entry
            games.append({k: v for k, v in entry.items() if k != "details"})
        else:
            pending.append(dict(base, status=pending_status(g)))
    # jo arkistoidut ottelut, joille koostevideo ilmestyi myöhemmin
    for k, e in arch["games"].items():
        if not e.get("videoId"):
            v = videos.get(f"{gd.isoformat()}|{e['away']}|{e['home']}")
            if v:
                e["videoId"] = v
                for g in games:
                    if str(g.get("id")) == k:
                        g["videoId"] = v
    if games:
        save_json(arch_path, arch)

    standings = fetch_standings() or prev.get("standings", [])
    upcoming = fetch_upcoming(et_today) or prev.get("upcoming", [])

    # suomalaisten kauden kehitys
    hist_path = os.path.join(DATA, "history.json")
    hist = load_json(hist_path, [])
    if finns:
        top = {f[0]: f[6] for f in finns[:5]}
        known = {n for hday in hist[-30:] for n in (hday.get("players") or {})}
        for f in finns:
            if f[0] in known:
                top.setdefault(f[0], f[6])
        entry = {"date": hel_today.isoformat(), "total": sum((f[6] or 0) for f in finns), "players": top}
        hist = [x for x in hist if x.get("date") != entry["date"]] + [entry]
        hist = hist[-200:]
        save_json(hist_path, hist)

    notice = None
    for n in CFG.get("notices") or []:
        if n.get("from", "0000") <= hel_today.isoformat() <= n.get("to", "9999"):
            notice = {"title": n["title"], "text": n["text"]}

    any_live = any(p["status"] and not p["status"].startswith(("Alkaa", "Siirretty", "Ei alkanut")) for p in pending)
    return {
        "site": CFG["siteName"],
        "updated": now.astimezone(HEL).isoformat(timespec="minutes"),
        "gameDate": gd.isoformat(),
        "notice": notice,
        "games": games,
        "pending": pending,
        "refreshNote": "Sivu päivittyy otteluiden aikana noin 10 minuutin välein." if any_live else None,
        "stars": night_stars(games),
        "upcoming": upcoming,
        "standings": standings,
        "skaters": skaters,
        "goalies": goalies,
        "finns": [f[:7] for f in finns],
        "finnGoalies": [f[:8] for f in fgk],
        "finnSlugs": {f[0]: f[-1] for f in finns + fgk},
        "finnNames": sorted(fin_names),
        "finnOff": finn_off,
        "tvInfo": CFG.get("tvInfo"),
        "history": hist[-120:],
        "sources": [{"name": "NHL.com (julkiset tulos- ja tilastotiedot)", "url": "https://www.nhl.com/"}]
                   + ([{"name": "MoneyPuck.com (edistyneet tilastot pelaajasivuilla)", "url": "https://moneypuck.com/"}] if MP.get("skaters") or MP.get("goalies") else []),
    }


# ---------------------------------------------------------------- sivut
# ---------------------------------------------------------------- jakokuvat (Open Graph, 1200x630)
OG_FONTS = os.path.join(ROOT, "assets", "fonts")
try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:  # kuvat ovat valinnaisia; ilman Pillowia käytetään yleiskuvaa
    Image = None


def _font(name, size):
    return ImageFont.truetype(os.path.join(OG_FONTS, name + ".ttf"), size)


def _hex(c):
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


S2 = 2  # piirretään kaksinkertaisena ja pienennetään -> pehmeät reunat
W, H = 1200 * S2, 630 * S2
BG = (11, 17, 24)
INK, MUTE, ICE = (238, 243, 248), (138, 155, 176), (127, 211, 255)


def _canvas(c1=None, c2=None):
    im = Image.new("RGB", (W, H), BG)
    for col, left in ((c1, True), (c2, False)):
        if not col:
            continue
        g1 = Image.new("L", (256, 1))
        g1.putdata([int(150 * ((255 - i) / 255) ** 1.6) for i in range(256)] if left else [int(150 * (i / 255) ** 1.6) for i in range(256)])
        grad = g1.resize((W // 2, H))
        layer = Image.new("RGB", (W // 2, H), _hex(col))
        im.paste(layer, (0 if left else W // 2, 0), grad)
    return im


_LOGO = None


def _logo(im, x, y, sz):
    global _LOGO
    if _LOGO is None:
        _LOGO = Image.open(os.path.join(ROOT, "assets", "logo-512.png")).convert("RGBA")
    lg = _LOGO.resize((int(sz), int(sz)), Image.LANCZOS)
    im.paste(lg, (int(x), int(y)), lg)


def _brand(d, x, y, sz=64):
    _logo(d._image, x, y, sz)
    f = _font("fraunces-latin-700-normal", int(sz * .62))
    d.text((x + sz * 1.2, y + sz / 2 + sz * .03), "PUNALAMPPU", font=f, fill=INK, anchor="lm")


def _fit(d, text, name, size, maxw):
    while size > 20:
        f = _font(name, size)
        if d.textlength(text, font=f) <= maxw:
            return f
        size -= 4
    return _font(name, size)


def _save(im, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    im.resize((1200, 630), Image.LANCZOS).save(path, "PNG", optimize=True)


def og_default(path):
    im = _canvas()
    d = ImageDraw.Draw(im)
    glow = Image.new("RGB", (W, H), (60, 14, 20))
    mask = Image.radial_gradient("L").resize((W, H)).point(lambda v: 255 - v)
    im.paste(glow, (0, 0), mask)
    d = ImageDraw.Draw(im)
    _logo(im, W // 2 - 140 * S2, 90 * S2, 280 * S2)
    f = _font("fraunces-latin-700-normal", 104 * S2)
    d.text((W // 2, 450 * S2), "PUNALAMPPU", font=f, fill=INK, anchor="mm")
    d.text((W // 2, 555 * S2), "Yön NHL-tulokset, maalikoosteet ja suomalaiset suomeksi", font=_font("inter-latin-500-normal", 30 * S2), fill=MUTE, anchor="mm")
    _save(im, path)


def og_game(path, gd, g):
    a, h = g["away"], g["home"]
    im = _canvas(COLORS.get(a), COLORS.get(h))
    d = ImageDraw.Draw(im)
    _brand(d, 56 * S2, 46 * S2, 56 * S2)
    d.text((W - 56 * S2, 74 * S2), fi_date(gd).capitalize(), font=_font("inter-latin-500-normal", 28 * S2), fill=INK, anchor="rm")
    bs, cy = 190 * S2, 300 * S2
    fb = _font("barlow-condensed-latin-800-normal", 84 * S2)
    for team_, cx in ((a, 230 * S2), (h, W - 230 * S2)):
        d.rounded_rectangle((cx - bs // 2, cy - bs // 2, cx + bs // 2, cy + bs // 2), 40 * S2, fill=_hex(COLORS.get(team_, "#445")))
        d.text((cx, cy + 4 * S2), team_, font=fb, fill="white", anchor="mm")
        d.text((cx, cy + bs // 2 + 44 * S2), tname(team_), font=_fit(d, tname(team_), "inter-latin-700-normal", 30 * S2, 360 * S2), fill=INK, anchor="mm")
    aw = (g.get("awayScore") or 0) > (g.get("homeScore") or 0)
    fs = _font("barlow-condensed-latin-800-normal", 250 * S2)
    sa, sh = str(g.get("awayScore")), str(g.get("homeScore"))
    wa, wh = d.textlength(sa, font=fs), d.textlength(sh, font=fs)
    wd = 70 * S2
    x0 = W / 2 - (wa + wd + wh) / 2
    d.text((x0, cy), sa, font=fs, fill=INK if aw else MUTE, anchor="lm")
    d.rounded_rectangle((x0 + wa + 16 * S2, cy + 6 * S2, x0 + wa + wd - 16 * S2, cy + 22 * S2), 6 * S2, fill=MUTE)
    d.text((x0 + wa + wd, cy), sh, font=fs, fill=MUTE if aw else INK, anchor="lm")
    st = "PÄÄTTYI" + (f" · {g['final']}" if g.get("final") else "")
    d.text((W / 2, cy + 150 * S2), st, font=_font("inter-latin-700-normal", 26 * S2), fill=ICE, anchor="mm")
    fins = [r for r in (g.get("finStats") or []) if r.get("pos") != "MV" and r.get("p")]
    line = ("Suomalaiset: " + ", ".join(f"{short_name(r['name'])} {r['g']}+{r['a']}" for r in sorted(fins, key=lambda r: -r["p"])[:4])) if fins else "Maalit, maalikooste ja suomalaiset – punalamppu.com"
    yb = H - 66 * S2
    d.rectangle((0, yb - 46 * S2, W, H), fill=(18, 27, 37))
    d.text((56 * S2, yb), line, font=_fit(d, line, "inter-latin-500-normal", 30 * S2, W - 112 * S2), fill=INK, anchor="lm")
    _save(im, path)


def og_player(path, name, t, posn, tiles, season):
    im = _canvas(COLORS.get(t) if t else None)
    d = ImageDraw.Draw(im)
    _brand(d, 56 * S2, 46 * S2, 56 * S2)
    d.text((W - 56 * S2, 74 * S2), f"Kausi {season}", font=_font("inter-latin-500-normal", 28 * S2), fill=INK, anchor="rm")
    bs = 150 * S2
    x, y = 56 * S2, 170 * S2
    d.rounded_rectangle((x, y, x + bs, y + bs), 34 * S2, fill=_hex(COLORS.get(t, "#2a3646")))
    d.text((x + bs / 2, y + bs / 2 + 4 * S2), t or "–", font=_font("barlow-condensed-latin-800-normal", 66 * S2), fill="white", anchor="mm")
    tx = x + bs + 36 * S2
    d.text((tx, y + 58 * S2), name, font=_fit(d, name, "fraunces-latin-700-normal", 92 * S2, W - tx - 56 * S2), fill=INK, anchor="lm")
    d.text((tx, y + 126 * S2), f"{tname(t) if t else 'Ei NHL-joukkuetta'} · {posn}", font=_font("inter-latin-500-normal", 32 * S2), fill=(210, 222, 234), anchor="lm")
    tw_, gap, ty = (W - 112 * S2 - 3 * 20 * S2) / 4, 20 * S2, 382 * S2
    fv, fl = _font("barlow-condensed-latin-800-normal", 104 * S2), _font("inter-latin-500-normal", 26 * S2)
    for i, (lbl, val) in enumerate(tiles):
        x0 = 56 * S2 + i * (tw_ + gap)
        d.rounded_rectangle((x0, ty, x0 + tw_, ty + 190 * S2), 24 * S2, fill=(18, 27, 37), outline=(34, 48, 64), width=2 * S2)
        vt = str(val if val not in (None, "") else "–")
        d.text((x0 + 28 * S2, ty + 82 * S2), vt, font=_fit(d, vt, "barlow-condensed-latin-800-normal", 104 * S2, tw_ - 56 * S2), fill=INK, anchor="lm")
        d.text((x0 + 30 * S2, ty + 158 * S2), lbl, font=fl, fill=MUTE, anchor="lm")
    _save(im, path)


def page(title, desc, path, body, jsonld=None, og=None):
    base = CFG["baseUrl"].rstrip("/")
    ld = f'<script type="application/ld+json">{json.dumps(jsonld, ensure_ascii=False)}</script>' if jsonld else ""
    return f"""<!DOCTYPE html>
<html lang="fi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title><meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{base}{path}"><meta property="og:title" content="{esc(title)}"><meta property="og:description" content="{esc(desc)}">
<meta property="og:type" content="website"><meta property="og:url" content="{base}{path}"><meta property="og:locale" content="fi_FI">
<meta property="og:image" content="{base}{og or '/og.png'}"><meta property="og:image:width" content="1200"><meta property="og:image:height" content="630"><meta name="twitter:card" content="summary_large_image">
<link rel="icon" href="/favicon.svg" type="image/svg+xml"><link rel="apple-touch-icon" href="/apple-touch-icon.png"><meta name="theme-color" content="#0B1118"><link rel="stylesheet" href="/static.css">{ld}</head>
<body><div class="wrap">{site_header(path)}
<main>{boxify(body)}</main>{footer()}</div></body></html>"""


def footer():
    return ('<footer class="foot"><div class="fgrid">'
            '<div class="fbrand"><a class="brand sm" href="/"><img src="/logo-mark.svg" alt="" width="26" height="26"><span>PUNALAMPPU</span></a>'
            '<p>Yön NHL-tulokset, maalikoosteet ja suomalaiset suomeksi. Päivittyy automaattisesti joka yö ja aamu.</p></div>'
            '<div><h4>NHL</h4><a href="/">Yön tulokset</a><a href="/otteluohjelma/">Otteluohjelma</a><a href="/sarjataulukko/">Sarjataulukko</a><a href="/pisteporssi/">Pistepörssi</a><a href="/ottelut/">Otteluarkisto</a></div>'
            '<div><h4>Suomalaiset</h4><a href="/suomalaiset/">Kaikki suomalaiset</a><a href="/#suomalaiset">Yön suomalaistilastot</a></div>'
            '<div><h4>Sivusto</h4><a href="/tietoa.html">Tietoa sivustosta</a><a href="/yhteys.html">Ota yhteyttä</a><a href="/tietosuoja.html">Tietosuoja</a></div>'
            '</div>'
            f'<p class="legal">{esc(CFG["siteName"])} on itsenäinen harrastussivusto, jolla ei ole yhteyttä National Hockey Leagueen (NHL) '
            'tai sen joukkueisiin. NHL ja joukkueiden nimet ovat omistajiensa tavaramerkkejä. Tulos- ja tilastotiedot: NHL.com. '
            'Edistyneet tilastot: MoneyPuck.com. Maalikoosteet: NHL / YouTube.</p></footer>')


def tname(a):
    return TEAMS.get(a, (a, a))[0]


def game_slug(gd, g):
    return f"{gd}-{g['away'].lower()}-{g['home'].lower()}"


def yt_url(gd, g):
    y, m, d = gd.split("-")
    months = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
    q = f"NHL Highlights | {TEAMS.get(g['away'], ('', g['away']))[1]} vs. {TEAMS.get(g['home'], ('', g['home']))[1]} | {months[int(m) - 1]} {d}, {y}"
    return "https://www.youtube.com/results?search_query=" + urllib.parse.quote(q)


def video_block(g, gd):
    vid = g.get("videoId")
    if not vid or not re.fullmatch(r"[A-Za-z0-9_-]{6,20}", vid):
        return (f'<section id="kooste" class="yt wait"><b>{ic("clock")}Maalikooste tulossa</b>'
                '<p class="mute">Kooste ilmestyy tälle sivulle automaattisesti, kun NHL julkaisee sen YouTubessa – yleensä muutaman tunnin kuluessa ottelun päättymisestä.</p></section>')
    return (f'<section id="kooste" class="yt" data-id="{vid}"><button type="button" class="play" onclick="kaYT(this.parentNode)"><span>{ic("play")}</span>Katso maalikooste</button>'
            f'<p class="mute">Video: NHL / YouTube. Video ladataan YouTubesta vasta painettaessa (YouTube voi tällöin asettaa evästeitä).</p></section>'
            '<script>function kaYT(d){d.innerHTML=\'<iframe src="https://www.youtube-nocookie.com/embed/\'+d.dataset.id+\'?autoplay=1&rel=0&playsinline=1" title="Maalikooste – NHL / YouTube" allow="autoplay; encrypted-media; picture-in-picture; fullscreen" allowfullscreen></iframe><p class="mute">Video: NHL / YouTube</p>\'}</script>')


def fi_date(gd):
    y, m, d = gd.split("-")
    wd = ["maanantai", "tiistai", "keskiviikko", "torstai", "perjantai", "lauantai", "sunnuntai"][dt.date(int(y), int(m), int(d)).weekday()]
    return f"{wd} {int(d)}.{int(m)}.{y}"


def score_txt(g):
    s = f"{g['awayScore']}–{g['homeScore']}"
    return s + (f" {g['final']}" if g.get("final") else "")


def fin_table(g, slugs):
    rows = g.get("finStats") or []
    if not rows:
        return ""
    lk = lambda n: f'<a href="/suomalaiset/{slugs[n]}.html">{esc(n)}</a>' if n in slugs else esc(n)
    sk = sorted([r for r in rows if r.get("pos") != "MV"], key=lambda r: (-r.get("p", 0), -r.get("g", 0)))
    gk = [r for r in rows if r.get("pos") == "MV"]
    out = f"<h2>{FLAG}Suomalaiset ottelussa</h2>"
    if sk:
        pm = lambda v: "–" if v is None else (f"+{v}" if v > 0 else str(v))
        out += ("<div class='tw'><table class='t'><tr><th>Pelaaja</th><th>M</th><th>S</th><th>P</th><th>+/-</th><th>L</th><th>Aika</th></tr>"
                + "".join(f"<tr><td>{lk(r['name'])} <span class='mute'>{esc(r['team'])}</span></td><td>{r['g']}</td><td>{r['a']}</td><td><b>{r['p']}</b></td>"
                          f"<td>{pm(r.get('pm'))}</td><td>{r.get('sog') if r.get('sog') is not None else '–'}</td><td>{esc(r.get('toi') or '')}</td></tr>" for r in sk)
                + "</table></div>")
    if gk:
        dec = {"W": "voitto", "L": "tappio", "O": "JA-tappio"}
        out += ("<div class='tw' style='margin-top:8px'><table class='t'><tr><th>Maalivahti</th><th>Torjunnat</th><th>TO%</th><th>Tulos</th></tr>"
                + "".join(f"<tr><td>{lk(r['name'])} <span class='mute'>{esc(r['team'])}</span></td><td>{r.get('saves', '–')}/{r.get('shots', '–')}</td>"
                          f"<td><b>{(('%.3f' % (r['saves'] / r['shots'])).lstrip('0')) if r.get('shots') and r.get('saves') is not None else '–'}</b></td><td>{esc(dec.get(r.get('dec'), ''))}</td></tr>" for r in gk)
                + "</table></div>")
    return out


def render_game_page(gd, g, slugs, others=()):
    a, h = tname(g["away"]), tname(g["home"])
    title = f"{a} – {h} {score_txt(g)} ({fi_date(gd).split(' ', 1)[1]}) | {CFG['siteName']}"
    scorers = ", ".join(sorted({x['who'].split(' ')[-1] for x in g.get('goals', []) if x.get('who')}))
    desc = f"NHL {fi_date(gd)}: {a} – {h} {score_txt(g)}. Maalintekijät: {scorers or '–'}. Maalit, maalivahdit ja maalikooste."
    rows = []
    for x in g.get("goals", []):
        who = esc(x["who"])
        if x["who"] in slugs:
            who = f'<a href="/suomalaiset/{slugs[x["who"]]}.html">{who}</a> <span class="fi">FIN</span>'
        ast = f' <span class="mute">({esc(", ".join(x.get("ast") or []))})</span>' if x.get("ast") else ""
        tag = f' <span class="tag">{esc(x["tag"])}</span>' if x.get("tag") else ""
        per = "JA" if x["p"] == "JA" else f"{x['p']}. erä"
        rows.append(f"<li class='grow'><span class='gt'>{per}<br>{esc(x['t'])}</span>{tbadge(x['team'], 'mini')}<span>{who}{tag}{ast}</span></li>")
    stars = "".join(f"<li class='grow'><span class='gt'>{s.get('star') or 1}. tähti</span>{tbadge(s['team'], 'mini')}<span>{esc(s['name'])} <span class='mute'>– {esc(star_line(s))}</span></span></li>" for s in g.get("threeStars", []))
    aw = (g.get("awayScore") or 0) > (g.get("homeScore") or 0)
    fin = "Päättyi" + (f" · {g['final']}" if g.get("final") else "")
    body = f"""<article><header class="ghero"><p class="gdate">{esc(fi_date(gd).capitalize())}{(' · ' + ic('pin') + esc(g['venue'])) if g.get('venue') else ''}</p>
<div class="score"><div class="team">{tbadge(g['away'], 'badge lg')}<b>{esc(a)}</b><small>vieras</small></div>
<div class="mid"><div class="nums"><span class="{'' if aw else 'l'}">{g.get('awayScore')}</span>–<span class="{'l' if aw else ''}">{g.get('homeScore')}</span></div><div class="fin">{esc(fin)}</div></div>
<div class="team">{tbadge(g['home'], 'badge lg')}<b>{esc(h)}</b><small>koti</small></div></div>
<h1>{esc(a)} – {esc(h)} {esc(score_txt(g))}</h1>{f'<p class="gnote">{esc(g["note"])}</p>' if g.get('note') else ''}</header>
{video_block(g, gd)}
{fin_table(g, slugs)}
<h2>Maalit</h2><ol class="rows">{''.join(rows) or '<li class="mute">Ei maalitietoja.</li>'}</ol>
{f'<h2>Maalivahdit</h2><p>{ic("goalie")}{esc(g["goalies"])}</p>' if g.get('goalies') else ''}
{f'<h2>Ottelun tähdet</h2><ul class="rows">{stars}</ul>' if stars else ''}
{('<h2>Saman yön muut ottelut</h2><ul class="rows">' + ''.join(f"<li><a class='mrow' href='/ottelut/{game_slug(gd, o)}.html'>{tbadge(o['away'], 'mini')}<span>{esc(tname(o['away']))} – {esc(tname(o['home']))}</span>{tbadge(o['home'], 'mini')}<b>{esc(score_txt(o))}</b>{ic('play', 'ic vid') if o.get('videoId') else ''}{ic('chev')}</a></li>" for o in others) + '</ul>') if others else ''}
</article>"""
    jsonld = {"@context": "https://schema.org", "@type": "SportsEvent", "name": f"{a} – {h}", "sport": "Jääkiekko",
              "startDate": g.get("start") or gd, "eventStatus": "https://schema.org/EventScheduled",
              "awayTeam": {"@type": "SportsTeam", "name": a}, "homeTeam": {"@type": "SportsTeam", "name": h},
              "location": {"@type": "Place", "name": g.get("venue") or h},
              "description": desc}
    return title, desc, body, jsonld


def player_og(slug, name, t, posn, tiles, gd):
    if not Image:
        return None
    try:
        p_ = f"/og/suomalaiset/{slug}.png"
        og_player(os.path.join(OUT, p_.lstrip("/")), name, t, posn, tiles, season_label(gd))
        return p_
    except Exception as e:
        log("og-kuva epäonnistui", slug, e)
        return None


def build_site(data):
    if os.path.exists(OUT):
        shutil.rmtree(OUT)
    shutil.copytree(WEB, OUT)
    base = CFG["baseUrl"].rstrip("/")
    slugs = data["finnSlugs"]
    urls = ["/", "/ottelut/", "/suomalaiset/", "/tietoa.html", "/tietosuoja.html", "/yhteys.html"]
    gd = data["gameDate"]

    # --- etusivu: esirenderöity sisältö hakukoneille, JS korvaa sen
    items = "".join(f"<li>{esc(tname(g['away']))} – {esc(tname(g['home']))} <b>{esc(score_txt(g))}</b> · "
                    f"<a href='/ottelut/{game_slug(gd, g)}.html'>maalit ja kooste</a></li>" for g in data["games"])
    ssr = (f"<h2>Yön tulokset ({esc(fi_date(gd))})</h2><ul class='ssr'>{items or '<li>Ei otteluita.</li>'}</ul>")
    desc = (f"NHL-tulokset {fi_date(gd)}: " + "; ".join(f"{g['away']}–{g['home']} {score_txt(g)}" for g in data["games"][:6])
            if data["games"] else CFG["tagline"])
    idx = open(os.path.join(WEB, "index.html"), encoding="utf-8").read()
    idx = (idx.replace("{{SITE}}", esc(CFG["siteName"])).replace("{{TAGLINE}}", esc(CFG["tagline"]))
              .replace("{{DESC}}", esc(desc[:300])).replace("{{CANONICAL}}", base + "/").replace("{{SSR}}", ssr)
              .replace("{{FOOTER}}", footer()).replace("{{ICONS}}", ICONS))
    idx = idx.replace("{{JSONLD}}", json.dumps({"@context": "https://schema.org", "@type": "WebSite", "name": CFG["siteName"],
                                                 "url": base + "/", "inLanguage": "fi"}, ensure_ascii=False))
    open(os.path.join(OUT, "index.html"), "w", encoding="utf-8").write(idx)
    save_json(os.path.join(OUT, "data.json"), data, pretty=False)

    # --- tieto- ja tietosuojasivut
    for fn in ("tietoa.html", "tietosuoja.html", "404.html", "yhteys.html"):
        p = os.path.join(OUT, fn)
        if os.path.exists(p):
            s = open(p, encoding="utf-8").read()
            s = (s.replace("{{SITE}}", esc(CFG["siteName"])).replace("{{BASE}}", base)
                  .replace("{{FORMKEY}}", esc(CFG.get("contactFormKey") or ""))
                  .replace("{{OWNER}}", esc(CFG.get("ownerName") or "Punalampun ylläpitäjä"))
                  .replace("{{FOOTER}}", footer()).replace("{{HEADER}}", site_header("/" + fn)))
            s = re.sub(r"(?s)<main>(.*?)</main>", lambda m: "<main>" + boxify(m.group(1)) + "</main>", s)
            open(p, "w", encoding="utf-8").write(s)

    # --- ottelusivut arkistosta
    os.makedirs(os.path.join(OUT, "ottelut"), exist_ok=True)
    days = []
    if Image:
        try:
            og_default(os.path.join(OUT, "og.png"))
        except Exception as e:
            log("og-oletuskuva epäonnistui", e)
    for di, fn in enumerate(sorted(os.listdir(os.path.join(DATA, "archive")), reverse=True)):
        if not fn.endswith(".json"):
            continue
        a = load_json(os.path.join(DATA, "archive", fn), {})
        d = a.get("gameDate") or fn[:-5]
        glist = {}
        for g in (a.get("games") or {}).values():  # sama ottelu vain kerran (rikkaimmat tiedot)
            k = game_slug(d, g)
            if k not in glist or len(g.get("finStats") or []) + len(g.get("goals") or []) > len(glist[k].get("finStats") or []) + len(glist[k].get("goals") or []):
                glist[k] = g
        glist = list(glist.values())
        lis = []
        for g in glist:
            title, desc_g, body, jl = render_game_page(d, g, slugs, [o for o in {game_slug(d, x): x for x in glist}.values() if game_slug(d, o) != game_slug(d, g)])
            path = f"/ottelut/{game_slug(d, g)}.html"
            ogp = None
            if Image and di < 4:
                try:
                    ogp = f"/og/ottelut/{game_slug(d, g)}.png"
                    og_game(os.path.join(OUT, ogp.lstrip("/")), d, g)
                except Exception as e:
                    log("og-kuva epäonnistui", path, e)
                    ogp = None
            open(os.path.join(OUT, path.lstrip("/")), "w", encoding="utf-8").write(page(title, desc_g, path, body, jl, ogp))
            urls.append(path)
            lis.append(f"<li><a class='mrow' href='{path}'>{tbadge(g['away'], 'mini')}<span>{esc(tname(g['away']))} – {esc(tname(g['home']))}</span>{tbadge(g['home'], 'mini')}<b>{esc(score_txt(g))}</b>{ic('chev')}</a></li>")
        if lis:
            days.append(f"<h2>{esc(fi_date(d).capitalize())}</h2><ul>{''.join(lis)}</ul>")
    open(os.path.join(OUT, "ottelut", "index.html"), "w", encoding="utf-8").write(
        page(f"NHL-ottelut ja tulokset | {CFG['siteName']}", "Kaikki NHL-ottelut, tulokset, maalintekijät ja maalikoosteet suomeksi.",
             "/ottelut/", "<h1>NHL-ottelut ja tulokset</h1>" + ("".join(days) or "<p>Ei vielä otteluita.</p>")))

    # --- suomalaisten sivut
    os.makedirs(os.path.join(OUT, "suomalaiset"), exist_ok=True)
    rows = []
    for f in data["finns"]:
        name, t, pos, gp, g_, a_, p_ = f
        path = f"/suomalaiset/{slugs[name]}.html"
        title, desc_p, body, jl = render_player(name, t, pos, f, False, data, gd, slugs)
        ogp = player_og(slugs[name], name, t, {"P": "puolustaja", "H": "hyökkääjä"}.get(pos, pos), [("Ottelut", gp), ("Maalit", g_), ("Syötöt", a_), ("Pisteet", p_)], gd)
        open(os.path.join(OUT, path.lstrip("/")), "w", encoding="utf-8").write(page(title, desc_p, path, body, jl, ogp))
        urls.append(path)
        rows.append(f"<tr><td><a href='{path}'>{esc(name)}</a></td><td>{esc(t)}</td><td>{gp}</td><td>{g_}</td><td>{a_}</td><td><b>{p_}</b></td></tr>")
    for f in data["finnGoalies"]:
        name, t = f[0], f[1]
        path = f"/suomalaiset/{slugs[name]}.html"
        title, desc_p, body, jl = render_player(name, t, "MV", f, True, data, gd, slugs)
        ogp = player_og(slugs[name], name, t, "maalivahti", [("Ottelut", f[2]), ("V–H–JA", f"{f[3]}–{f[4]}–{f[5]}"), ("TO%", f[6]), ("PMK", f[7])], gd)
        open(os.path.join(OUT, path.lstrip("/")), "w", encoding="utf-8").write(page(title, desc_p, path, body, jl, ogp))
        urls.append(path)
    open(os.path.join(OUT, "suomalaiset", "index.html"), "w", encoding="utf-8").write(page(
        f"Suomalaiset NHL:ssä {season_label(gd)} – pisteet ja tilastot | {CFG['siteName']}",
        f"Kaikki suomalaiset NHL-pelaajat kaudella {season_label(gd)}: pisteet, maalit ja maalivahtitilastot päivittäin.",
        "/suomalaiset/",
        f"<h1>Suomalaiset NHL:ssä {season_label(gd)}</h1><h2>Kenttäpelaajat</h2><div class='tw'><table class='t'><tr><th>Pelaaja</th><th>Joukkue</th><th>O</th><th>M</th><th>S</th><th>P</th></tr>{''.join(rows)}</table></div>"
        + "<h2>Maalivahdit</h2><ul>" + "".join(f"<li><a href='/suomalaiset/{slugs[f[0]]}.html'>{esc(f[0])}</a> ({esc(f[1])}) {f[2]} ott., TO% {esc(f[6])}</li>" for f in data["finnGoalies"]) + "</ul>"))

    # --- hakusanojen mukaiset koostesivut
    sl = season_label(gd)

    def write(path, title, desc_, body):
        os.makedirs(os.path.join(OUT, path.strip("/")), exist_ok=True)
        open(os.path.join(OUT, path.strip("/"), "index.html"), "w", encoding="utf-8").write(page(title, desc_, path, body))
        urls.append(path)

    def plrow(i, p):
        nm = esc(p[0])
        if p[0] in slugs:
            nm = f"<a href='/suomalaiset/{slugs[p[0]]}.html'>{nm}</a> <span class='fi'>FIN</span>"
        return f"<tr><td>{i}. {nm}</td><td>{tbadge(p[1], 'mini')}</td><td>{p[2]}</td><td>{p[3]}</td><td>{p[4]}</td><td><b>{p[5]}</b></td></tr>"
    head = "<tr><th>Pelaaja</th><th>Joukkue</th><th>O</th><th>M</th><th>S</th><th>P</th></tr>"
    sk = data["skaters"]
    by_g = sorted(sk, key=lambda x: (-x[3], -x[5]))[:20]
    top3 = ", ".join(f"{p[0]} {p[5]} p" for p in sk[:3])
    write("/pisteporssi/", f"NHL-pistepörssi {sl} – pisteet, maalit ja syötöt | {CFG['siteName']}",
          f"NHL:n pistepörssi kaudella {sl} päivittäin päivitettynä. Kärjessä: {top3}. Myös maalipörssi, syöttöpörssi ja suomalaiset.",
          f"<h1>NHL-pistepörssi {sl}</h1><p class='mute'>Päivitetty {esc(data['updated'][:10])}. Suomalaisten oma pörssi: <a href='/suomalaiset/'>suomalaiset NHL:ssä</a>.</p>"
          f"<h2>Pistepörssi – top 50</h2><div class='tw'><table class='t'>{head}{''.join(plrow(i + 1, p) for i, p in enumerate(sk[:50]))}</table></div>"
          f"<h2>Maalipörssi</h2><div class='tw'><table class='t'>{head}{''.join(plrow(i + 1, p) for i, p in enumerate(by_g))}</table></div>")
    srows = ""
    for dv in data["standings"]:
        tl = sorted(dv["teams"], key=lambda t: (-t[5], t[1]))
        srows += (f"<h2>{esc(dv['name'])} ({esc(dv['conf'])})</h2><table class='t'><tr><th>Joukkue</th><th>O</th><th>V</th><th>H</th><th>JA</th><th>P</th></tr>"
                  + "".join(f"<tr><td>{i + 1}. {esc(tname(t[0]))}</td><td>{t[1]}</td><td>{t[2]}</td><td>{t[3]}</td><td>{t[4]}</td><td><b>{t[5]}</b></td></tr>" for i, t in enumerate(tl))
                  + "</table>")
    write("/sarjataulukko/", f"NHL-sarjataulukko {sl} – divisioonat ja konferenssit | {CFG['siteName']}",
          f"NHL:n sarjataulukko kaudella {sl}: Atlantic, Metropolitan, Central ja Pacific. Päivittyy jokaisen ottelupäivän jälkeen.",
          f"<h1>NHL-sarjataulukko {sl}</h1><p class='mute'>Päivitetty {esc(data['updated'][:10])}. Villit kortit ja oma joukkue: <a href='/#sarjataulukko'>interaktiivinen taulukko</a>.</p>{srows}")
    days = {}
    for u in data["upcoming"]:
        days.setdefault(u["day"], []).append(u)
    orows = ""
    for d, lst in sorted(days.items()):
        orows += f"<h2>{esc(fi_date(d).capitalize())}</h2><ul>" + "".join(
            f"<li><b>{esc(fi_time(u['start']))}</b> {esc(tname(u['away']))} – {esc(tname(u['home']))}{(' · ' + esc(u['venue'])) if u.get('venue') else ''}"
            + (f" <span class='fins'>{FLAG}{esc(', '.join(short_name(n) for n in finn_by_team(data, u['away'], u['home'])))}</span>" if finn_by_team(data, u['away'], u['home']) else "")
            + "</li>" for u in sorted(lst, key=lambda x: x["start"] or "")) + "</ul>"
    write("/otteluohjelma/", f"NHL-otteluohjelma – tulevat ottelut Suomen aikaa | {CFG['siteName']}",
          "NHL:n otteluohjelma seuraavalle viikolle Suomen ajassa. Näet myös, missä otteluissa suomalaiset pelaavat.",
          f"<h1>NHL-otteluohjelma Suomen aikaa</h1><p class='mute'>Kellonajat Suomen aikaa. Otsikon päivä on NHL:n pelipäivä Pohjois-Amerikassa; ottelut pelataan Suomessa seuraavana yönä.</p>{tv_html(data)}{orows or '<p>Ei tulevia otteluita tiedossa.</p>'}")

    # --- sitemap & robots
    today = now_utc().astimezone(HEL).date().isoformat()
    sm = "".join(f"<url><loc>{base}{u}</loc><lastmod>{today}</lastmod></url>" for u in urls)
    open(os.path.join(OUT, "sitemap.xml"), "w", encoding="utf-8").write(
        f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{sm}</urlset>')
    open(os.path.join(OUT, "robots.txt"), "w", encoding="utf-8").write(f"User-agent: *\nAllow: /\nSitemap: {base}/sitemap.xml\n")
    domain = re.sub(r"^https?://", "", base).split("/")[0]
    if not domain.endswith("github.io"):
        open(os.path.join(OUT, "CNAME"), "w").write(domain + "\n")
    log("valmis:", len(urls), "sivua,", len(data["games"]), "ottelua,", len(data["pending"]), "kesken")


_GOALS_CACHE = None


def recent_goals(name, limit=5):
    global _GOALS_CACHE
    if _GOALS_CACHE is None:
        _GOALS_CACHE = []
        for fn in sorted(os.listdir(os.path.join(DATA, "archive")), reverse=True)[:40]:
            a = load_json(os.path.join(DATA, "archive", fn), {})
            d = a.get("gameDate") or fn[:-5]
            for g in (a.get("games") or {}).values():
                for x in g.get("goals", []):
                    _GOALS_CACHE.append((d, g, x))
    out = []
    for d, g, x in _GOALS_CACHE:
        if x.get("who") == name:
            opp = g["home"] if x["team"] == g["away"] else g["away"]
            out.append(f"<li><a class='mrow' href='/ottelut/{game_slug(d, g)}.html'><span class='gt'>{esc(fi_short(d))}</span><span>Maali vs {esc(tname(opp))}</span>{tbadge(opp, 'mini')}{ic('chev')}</a></li>")
        if len(out) >= limit:
            break
    return "".join(out)


FI_MONTHS = ["tammikuuta", "helmikuuta", "maaliskuuta", "huhtikuuta", "toukokuuta", "kesäkuuta", "heinäkuuta", "elokuuta",
             "syyskuuta", "lokakuuta", "marraskuuta", "joulukuuta"]
TEAM_GEN = {}  # joukkueen nimi genetiivissä: "Montréal Canadiensin"


def tgen(a):
    return TEAM_GEN.get(a) or (tname(a) + ("in" if not tname(a).endswith("s") else "in"))


def season_txt(sid):
    s_ = str(sid)
    return f"{s_[:4]}–{s_[6:8]}" if len(s_) == 8 else s_


def render_player(name, t, pos, f, is_goalie, data, gd, slugs):
    pr = PROFILES.get(FINN_PID.get(name)) or {}
    sl = season_label(gd)
    posn = {"P": "puolustaja", "H": "hyökkääjä", "MV": "maalivahti"}[pos]
    team_full = tname(t) if t else ""
    # syntymä ja ikä
    born, age = "", None
    if pr.get("birthDate"):
        try:
            bd = dt.date.fromisoformat(pr["birthDate"])
            today = now_utc().astimezone(HEL).date()
            age = today.year - bd.year - ((today.month, today.day) < (bd.month, bd.day))
            city = L(pr.get("birthCity")) or ""
            country = {"FIN": "Suomi", "SWE": "Ruotsi", "USA": "Yhdysvallat", "CAN": "Kanada"}.get(pr.get("birthCountry") or "", "")
            born = f"Hän on syntynyt {bd.day}. {FI_MONTHS[bd.month - 1]} {bd.year}." + (f" Syntymäpaikka: {city}" + (f", {country}" if country else "") + "." if city else "")
        except ValueError:
            pass
    off = name in (data.get("finnOff") or [])
    lead = f"{esc(name)} on {str(age) + '-vuotias ' if age else ''}suomalainen {posn}"
    if team_full and off:
        lead += f", joka ei ole tällä hetkellä {esc(team_full)} -joukkueen NHL-kokoonpanossa (esimerkiksi farmissa). Tämän kauden NHL-ottelunsa hän on pelannut {esc(team_full)} -joukkueessa."
    else:
        lead += f", joka pelaa NHL:ssä {esc(team_full)} -joukkueessa." if team_full else "."
    if is_goalie:
        gp, w, l, otl, sv, gaa = f[2], f[3], f[4], f[5], f[6], f[7]
        season_line = (f"Kaudella {sl} hän on pelannut {gp} ottelua (voitot–tappiot–JA {w}–{l}–{otl}), torjuntaprosentti {sv} ja päästettyjen maalien keskiarvo {gaa}."
                       if gp else f"Kaudella {sl} hän ei ole vielä pelannut NHL-ottelua.")
        stat_tbl = (f"<table class='t'><tr><th>Ottelut</th><th>V-H-JA</th><th>TO%</th><th>PMK</th></tr>"
                    f"<tr><td>{gp}</td><td>{w}-{l}-{otl}</td><td><b>{esc(sv)}</b></td><td>{esc(gaa)}</td></tr></table>")
        desc_p = f"{name} ({team_full or 'NHL'}, maalivahti): kauden {sl} tilastot, torjuntaprosentti, viimeisimmät ottelut ja NHL-ura."
    else:
        gp, g_, a_, p_ = f[3], f[4], f[5], f[6]
        season_line = (f"Kaudella {sl} hän on tehnyt {gp} ottelussa {g_} maalia ja {a_} syöttöä eli {p_} pistettä."
                       if gp else f"Kaudella {sl} hän ei ole vielä pelannut NHL-ottelua.")
        sub = (((pr.get("featuredStats") or {}).get("regularSeason") or {}).get("subSeason")) or {}
        extra_h = extra_d = ""
        for k, lbl in (("plusMinus", "+/-"), ("powerPlayGoals", "YVM"), ("shots", "L")):
            if sub.get(k) is not None:
                extra_h += f"<th>{lbl}</th>"
                extra_d += f"<td>{sub[k]:+d}</td>" if k == "plusMinus" else f"<td>{sub[k]}</td>"
        stat_tbl = (f"<table class='t'><tr><th>Ottelut</th><th>Maalit</th><th>Syötöt</th><th>Pisteet</th>{extra_h}</tr>"
                    f"<tr><td>{gp}</td><td>{g_}</td><td>{a_}</td><td><b>{p_}</b></td>{extra_d}</tr></table>")
        desc_p = (f"{name} ({team_full or 'NHL'}): kaudella {sl} {gp} ottelua, {g_}+{a_}={p_} pistettä. Tilastot, viimeisimmät ottelut, maalit ja NHL-ura."
                  if gp else f"{name} ({team_full or 'NHL'}, {posn}): tilastot, NHL-ura ja ottelut kaudella {sl}.")
    dd = pr.get("draftDetails") or {}
    draft = (f"NHL-varaus: {dd.get('year')}, {esc(tname(team(dd.get('teamAbbrev'))))}, {dd.get('round')}. kierros ({dd.get('overallPick')}. kokonaisuudessaan)."
             if dd.get("year") else "")
    phys = []
    if pr.get("heightInCentimeters"):
        phys.append(f"pituus {pr['heightInCentimeters']} cm")
    if pr.get("weightInKilograms"):
        phys.append(f"paino {pr['weightInKilograms']} kg")
    if pr.get("shootsCatches"):
        phys.append(("kätisyys " if not is_goalie else "kiinniottokäsi ") + {"L": "vasen", "R": "oikea"}.get(pr["shootsCatches"], pr["shootsCatches"]))
    if pr.get("sweaterNumber"):
        phys.append(f"pelinumero {pr['sweaterNumber']}")

    # viimeisimmät ottelut
    l5 = pr.get("last5Games") or []
    l5html = ""
    if l5:
        if is_goalie:
            l5html = "<h2>Viimeisimmät ottelut</h2><table class='t'><tr><th>Pvm</th><th>Vastustaja</th><th>Tulos</th><th>Torj.</th><th>TO%</th></tr>" + "".join(
                f"<tr><td>{esc(fi_short(x.get('gameDate')))}</td><td>{esc(x.get('opponentAbbrev') or '')}</td><td>{esc({'W': 'V', 'L': 'H', 'O': 'JA'}.get(x.get('decision') or '', '–'))}</td>"
                f"<td>{(x.get('shotsAgainst') or 0) - (x.get('goalsAgainst') or 0)}/{x.get('shotsAgainst') or 0}</td><td>{fmt_sv(x.get('savePctg'))}</td></tr>" for x in l5) + "</table>"
        else:
            l5html = "<h2>Viimeisimmät ottelut</h2><table class='t'><tr><th>Pvm</th><th>Vastustaja</th><th>M</th><th>S</th><th>P</th><th>+/-</th></tr>" + "".join(
                f"<tr><td>{esc(fi_short(x.get('gameDate')))}</td><td>{esc(x.get('opponentAbbrev') or '')}</td><td>{x.get('goals', 0)}</td><td>{x.get('assists', 0)}</td>"
                f"<td><b>{x.get('points', 0)}</b></td><td>{x.get('plusMinus', 0):+d}</td></tr>" for x in l5) + "</table>"
    # NHL-ura kausittain
    st = [x for x in pr.get("seasonTotals") or [] if x.get("gameTypeId") == 2]
    career = ""
    if st:
        if is_goalie:
            career = "<h2>NHL-ura</h2><table class='t'><tr><th>Kausi</th><th>Joukkue</th><th>O</th><th>V</th><th>TO%</th><th>PMK</th></tr>" + "".join(
                f"<tr><td>{season_txt(x.get('season'))}</td><td>{esc(L(x.get('teamName')) or '')}</td><td>{x.get('gamesPlayed', 0)}</td><td>{x.get('wins', 0)}</td>"
                f"<td>{fmt_sv(x.get('savePctg'))}</td><td>{fmt_gaa(x.get('goalsAgainstAvg'))}</td></tr>" for x in reversed(st)) + "</table>"
        else:
            career = "<h2>NHL-ura</h2><table class='t'><tr><th>Kausi</th><th>Joukkue</th><th>O</th><th>M</th><th>S</th><th>P</th></tr>" + "".join(
                f"<tr><td>{season_txt(x.get('season'))}</td><td>{esc(L(x.get('teamName')) or '')}</td><td>{x.get('gamesPlayed', 0)}</td><td>{x.get('goals', 0)}</td>"
                f"<td>{x.get('assists', 0)}</td><td><b>{x.get('points', 0)}</b></td></tr>" for x in reversed(st)) + "</table>"
        ct = ((pr.get("careerTotals") or {}).get("regularSeason")) or {}
        if ct and not is_goalie:
            career += f"<p>Runkosarjaura yhteensä: <b>{ct.get('gamesPlayed', 0)}</b> ottelua, {ct.get('goals', 0)} maalia, {ct.get('assists', 0)} syöttöä, <b>{ct.get('points', 0)}</b> pistettä.</p>"
        elif ct:
            career += f"<p>Runkosarjaura yhteensä: <b>{ct.get('gamesPlayed', 0)}</b> ottelua, {ct.get('wins', 0)} voittoa, {ct.get('shutouts', 0)} nollapeliä.</p>"
    # seuraava ottelu
    nxt = next((u for u in sorted(data["upcoming"], key=lambda u: u.get("start") or "") if t and t in (u["away"], u["home"])), None)
    nxt_html = ""
    if nxt:
        opp = nxt["home"] if nxt["away"] == t else nxt["away"]
        st_ = dt.datetime.fromisoformat(nxt["start"].replace("Z", "+00:00")).astimezone(HEL)
        nxt_html = (f"<h2>Seuraava ottelu</h2><p>{esc(team_full)} – {esc(tname(opp))}: {['ma', 'ti', 'ke', 'to', 'pe', 'la', 'su'][st_.weekday()]} {st_.day}.{st_.month}. klo {st_:%H.%M} Suomen aikaa"
                    + (f" ({esc(nxt['venue'])})" if nxt.get("venue") else "") + ". <a href='/otteluohjelma/'>Koko otteluohjelma</a></p>")
    mates = [n for n in finn_by_team(data, t) if n != name] if t else []
    mates_html = ("<ul class='rows'>" + "".join(f"<li><a class='mrow' href='/suomalaiset/{slugs[n]}.html'>{tbadge(t, 'mini')}<span>{esc(n)}</span>{ic('chev')}</a></li>" for n in mates if n in slugs) + "</ul>") if mates else ""
    recent = recent_goals(name)
    # usein kysytyt
    faq = [(f"Missä joukkueessa {name} pelaa?",
            f"{name} kuuluu {team_full} -organisaatioon, mutta ei ole tällä hetkellä joukkueen NHL-kokoonpanossa." if team_full and off
            else f"{name} pelaa NHL:ssä {team_full} -joukkueessa." if team_full else f"{name} ei ole tällä hetkellä NHL-kokoonpanossa.")]
    faq.append((f"Paljonko {name} on tehnyt pisteitä kaudella {sl}?" if not is_goalie else f"Millaiset tilastot {name} on tehnyt kaudella {sl}?", season_line))
    faq_html = "<h2>Usein kysyttyä</h2>" + "".join(f"<h3>{esc(q)}</h3><p>{esc(a)}</p>" for q, a in faq)
    if is_goalie:
        tiles = [("Ottelut", f[2]), ("V–H–JA", f"{f[3]}–{f[4]}–{f[5]}"), ("TO%", f[6]), ("PMK", f[7])]
    else:
        tiles = [("Ottelut", f[3]), ("Maalit", f[4]), ("Syötöt", f[5]), ("Pisteet", f[6])]
    facts = []
    if age:
        facts.append(("Ikä", f"{age} v"))
    if pr.get("birthDate"):
        try:
            bd = dt.date.fromisoformat(pr["birthDate"])
            facts.append(("Syntynyt", f"{bd.day}.{bd.month}.{bd.year}" + (f", {L(pr.get('birthCity'))}" if L(pr.get("birthCity")) else "")))
        except ValueError:
            pass
    if pr.get("heightInCentimeters"):
        facts.append(("Pituus", f"{pr['heightInCentimeters']} cm"))
    if pr.get("weightInKilograms"):
        facts.append(("Paino", f"{pr['weightInKilograms']} kg"))
    if pr.get("shootsCatches"):
        facts.append(("Kiinniottokäsi" if is_goalie else "Kätisyys", {"L": "vasen", "R": "oikea"}.get(pr["shootsCatches"], pr["shootsCatches"])))
    if dd.get("year"):
        facts.append(("NHL-varaus", f"{dd.get('year')}, {dd.get('round')}. kierros ({dd.get('overallPick')}.), {team(dd.get('teamAbbrev')) or ''}"))
    numtxt = f" · #{pr['sweaterNumber']}" if pr.get("sweaterNumber") else ""
    hero = (f"<header class='phero' style='--tc:{COLORS.get(t, '#2a3646')}'>{tbadge(t, 'badge lg')}<div><h1>{esc(name)}</h1>"
            f"<p class='sub'>{FLAG}{esc(team_full or 'Ei NHL-joukkuetta')} · {posn}{numtxt}</p>"
            + ("<p class='offtag'>Ei tällä hetkellä NHL-kokoonpanossa</p>" if off else "") + "</div></header>"
            "<div class='tiles'>" + "".join(f"<div class='tile'><b>{v if v not in (None, '') else '–'}</b><small>{k}</small></div>" for k, v in tiles) + "</div>")
    facts_html = ("<dl class='facts'>" + "".join(f"<div><dt>{k}</dt><dd>{esc(v)}</dd></div>" for k, v in facts) + "</dl>") if facts else ""
    body = (f"<article>{hero}<p class='lead'>{lead} {esc(born)} {esc(season_line)}</p>{facts_html}"
            + f"<h2>Kausi {sl}</h2><div class='tw'>{stat_tbl}</div>{mp_block(name, FINN_PID.get(name), is_goalie, data)}{l5html}"
            + (f"<h2>Viimeisimmät maalit</h2><ul class='rows'>{recent}</ul>" if recent else "")
            + nxt_html + career + (f"<h2>Joukkuetoverit</h2>{mates_html}" if mates_html else "") + faq_html
            + "</article>")
    title = f"{name} – tilastot, pisteet ja ottelut {sl} | {CFG['siteName']}" if not is_goalie else f"{name} – maalivahtitilastot ja ottelut {sl} | {CFG['siteName']}"
    base = CFG["baseUrl"].rstrip("/")
    person = {"@type": "Person", "name": name, "nationality": {"@type": "Country", "name": "Suomi"}, "jobTitle": f"jääkiekon {posn}",
              "url": f"{base}/suomalaiset/{slugs[name]}.html"}
    if team_full:
        person["memberOf"] = {"@type": "SportsTeam", "name": team_full, "sport": "Jääkiekko"}
    if pr.get("birthDate"):
        person["birthDate"] = pr["birthDate"]
    if L(pr.get("birthCity")):
        person["birthPlace"] = {"@type": "Place", "name": L(pr.get("birthCity"))}
    if pr.get("heightInCentimeters"):
        person["height"] = {"@type": "QuantitativeValue", "value": pr["heightInCentimeters"], "unitCode": "CMT"}
    jl = {"@context": "https://schema.org", "@graph": [
        person,
        {"@type": "FAQPage", "mainEntity": [{"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faq]}]}
    return title, desc_p, body, jl


def short_name(n):
    w = (n or "").split()
    return n if len(w) < 2 else "-".join(x[:1] + "." for x in w[0].split("-")) + " " + " ".join(w[1:])


def fi_short(iso):
    try:
        d = dt.date.fromisoformat(str(iso)[:10])
        return f"{d.day}.{d.month}."
    except ValueError:
        return str(iso or "")


def fmt_sv(v):
    return f"{v:.3f}".lstrip("0") if isinstance(v, (int, float)) else "–"


def fmt_gaa(v):
    return f"{v:.2f}" if isinstance(v, (int, float)) else "–"


def tv_html(data):
    tv = data.get("tvInfo")
    if not tv:
        return ""
    rows = "".join(f"<li><b>{esc(n)}</b><span>{esc(t)}</span></li>" for n, t in tv["items"])
    more = f"<p class='small'><a href='{esc(tv['more'][1])}' rel='noopener'>{esc(tv['more'][0])} {ic('chev')}</a></p>" if tv.get("more") else ""
    return f"<h2>Missä NHL näkyy Suomessa {esc(tv.get('season', ''))}</h2><ul class='tvlist'>{rows}</ul><p class='mute small'>{esc(tv.get('note', ''))}</p>{more}"


def finn_by_team(data, *teams):
    off = set(data.get("finnOff") or [])
    return [f[0] for f in data["finns"] + data["finnGoalies"] if f[1] in teams and f[0] not in off]


def season_label(gd):
    y, m = int(gd[:4]), int(gd[5:7])
    s = y if m >= 7 else y - 1
    return f"{s}–{str(s + 1)[2:]}"


if __name__ == "__main__":
    data = collect()
    build_site(data)
