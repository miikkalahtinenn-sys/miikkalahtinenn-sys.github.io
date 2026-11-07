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
    "MTL": ("Montreal Canadiens", "Canadiens"), "NJD": ("New Jersey Devils", "Devils"), "NSH": ("Nashville Predators", "Predators"),
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
         '<symbol id="i-cal" viewBox="0 0 24 24"><g fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><rect x="3.5" y="5" width="17" height="15" rx="2.5"/><path d="M3.5 10h17M8 3v4M16 3v4"/></g></symbol>'
         '</svg>')


def ic(name, cls="ic"):
    return f'<svg class="{cls}" aria-hidden="true"><use href="#i-{name}"/></svg>'


FLAG = '<span class="flag" aria-hidden="true"></span>'


def tbadge(a, cls="badge"):
    if not a:
        return f'<span class="{cls}" style="background:#2a3646" title="Ei NHL-joukkuetta">–</span>'
    return f'<span class="{cls}" style="background:{COLORS.get(a, "#445")}" title="{esc(TEAMS.get(a, (a,))[0])}">{esc(a)}</span>'


NAV = [("/", "Tulokset"), ("/otteluohjelma/", "Ohjelma"), ("/suomalaiset/", "Suomalaiset"), ("/uutiset/", "Uutiset"), ("/nhl-tv/", "TV-lähetykset"),
       ("/pisteporssi/", "Pistepörssi"), ("/sarjataulukko/", "Sarjataulukko"), ("/joukkueet/", "Joukkueet"), ("/tulokset/", "Arkisto")]


def site_header(path=""):
    def on(h):
        return h == path or (h != "/" and path.startswith(h)) or (h == "/ottelut/" and path.startswith("/ottelut/"))
    nav = "".join(f'<a href="{h}"{" class=on" if on(h) else ""}>{FLAG if h == "/suomalaiset/" else ""}{t}</a>' for h, t in NAV)
    return (ICONS + '<header class="top"><a class="brand" href="/" aria-label="Punalamppu – etusivu"><img src="/logo-mark.svg" alt="" width="42" height="42"><span>PUNALAMPPU</span></a>'
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


FI_NAMES = {}  # NHL:n englanninkielinen nimi -> suomenkielinen kirjoitusasu (rajapinnan "fi"-kenttä)


def fi_translit(s):
    """NHL:n fi-kentän sh/zh-tyyliset translitteroinnit suomalaiseen asuun (Kotshetkov -> Kotšetkov)."""
    for a, b in (("Tsh", "Tš"), ("tsh", "tš"), ("Sh", "Š"), ("sh", "š"), ("Zh", "Ž"), ("zh", "ž")):
        s = s.replace(a, b)
    return s


def full_name(p):
    fn, ln = L(p.get("firstName")), L(p.get("lastName"))
    if fn and ln:
        fo, lo = p.get("firstName"), p.get("lastName")
        ffi = fo.get("fi") if isinstance(fo, dict) else None
        lfi = lo.get("fi") if isinstance(lo, dict) else None
        if (ffi and ffi != fn) or (lfi and lfi != ln):
            fi = fi_translit(f"{ffi or fn} {lfi or ln}")
            FI_NAMES[fixname_base(f"{fn} {ln}")] = fi
            return fi
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


def fixname_base(n):
    for a, b in NAME_FIX.items():
        n = re.sub(r"\b" + re.escape(a) + r"\b", b, n)
    return n


def fixname(n):
    """NHL:n tilastopalvelu palauttaa nimet ilman ääkkösiä (Teravainen) – korjataan config.json:n nameFixes-listalla.
    Venäläiset ym. nimet kirjoitetaan suomalaisittain (FI_NAMES)."""
    if not n:
        return n
    if n in FI_NAMES:
        return FI_NAMES[n]
    if fixname_base(n) in FI_NAMES:
        return FI_NAMES[fixname_base(n)]
    for a, b in NAME_FIX.items():
        n = re.sub(r"\b" + re.escape(a) + r"\b", b, n)
    return n


def pname(obj):
    n = NAMES.get(obj.get("playerId"))
    return fixname(n) if n else fixname(full_name(obj))


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
    if cache.get("date") != today.isoformat() or not cache.get("players") or "allIds" not in cache or "fiNames" not in cache:
        players, all_ids = [], []
        for abbr in TEAMS:
            d = get(f"{API}/roster/{abbr}/current") or {}
            for grp, pos in (("forwards", "H"), ("defensemen", "P"), ("goalies", "MV")):
                for p in d.get(grp) or []:
                    if p.get("id"):
                        all_ids.append(p["id"])
                        full_name(p)  # kerää suomenkieliset kirjoitusasut
                    if (p.get("birthCountry") or "").upper() != "FIN":
                        continue
                    players.append({"id": p.get("id"), "name": fixname(full_name(p)), "team": abbr, "pos": pos})
        if players:
            cache = {"date": today.isoformat(), "players": players, "allIds": sorted(set(all_ids)), "fiNames": dict(sorted(FI_NAMES.items()))}
            save_json(path, cache)
    ROSTER_IDS.clear()
    ROSTER_IDS.update(cache.get("allIds") or [])
    return cache.get("players") or []


ROSTER_IDS = set()
try:  # edellisen ajon suomenkieliset nimet käyttöön heti alussa
    FI_NAMES.update(json.load(open(os.path.join(DATA, "rosters.json"), encoding="utf-8")).get("fiNames") or {})
except Exception:
    pass


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


def fetch_teams(now):
    """Joukkueiden kauden otteluohjelma ja pelaajatilastot (NHL:n julkinen rajapinta). Haetaan enintään 4 tunnin välein."""
    path = os.path.join(DATA, "teams.json")
    cache = load_json(path, {})
    try:
        age = (now - dt.datetime.fromisoformat(cache.get("_fetched"))).total_seconds() / 3600
    except Exception:
        age = 1e9
    if age < 4 and len(cache.get("teams") or {}) >= 30:
        return cache
    out = {"_fetched": now.isoformat(timespec="minutes"), "teams": {}}
    old = cache.get("teams") or {}
    for a in TEAMS:
        sch = get(f"{API}/club-schedule-season/{a}/now")
        st = get(f"{API}/club-stats/{a}/now")
        if not sch and not st:
            if a in old:
                out["teams"][a] = old[a]
            continue
        games = []
        for g in (sch or {}).get("games") or []:
            if g.get("gameType") != 2:
                continue
            at, ht = g.get("awayTeam") or {}, g.get("homeTeam") or {}
            games.append({"id": g.get("id"), "date": g.get("gameDate"), "start": g.get("startTimeUTC"),
                          "away": team(at.get("abbrev")), "home": team(ht.get("abbrev")), "state": g.get("gameState"),
                          "as": at.get("score"), "hs": ht.get("score"),
                          "last": (g.get("gameOutcome") or {}).get("lastPeriodType") or ""})
        sk = []
        for r in (st or {}).get("skaters") or []:
            sk.append([pname(r), r.get("positionCode"), r.get("gamesPlayed", 0), r.get("goals", 0), r.get("assists", 0), r.get("points", 0), r.get("plusMinus", 0)])
        gk = []
        for r in (st or {}).get("goalies") or []:
            gk.append([pname(r), r.get("gamesPlayed", 0), r.get("wins", 0), r.get("losses", 0), r.get("overtimeLosses", 0),
                       r.get("savePercentage"), r.get("goalsAgainstAverage"), r.get("shutouts", 0)])
        out["teams"][a] = {"games": games or (old.get(a) or {}).get("games") or [], "skaters": sk or (old.get(a) or {}).get("skaters") or [],
                           "goalies": gk or (old.get(a) or {}).get("goalies") or []}
    log("joukkueet:", len(out["teams"]))
    if out["teams"]:
        save_json(path, out, pretty=False)
        return out
    return cache


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


def resolve_free_games(hel_today):
    """Ilmaiskanavien ottelut (config.json: freeGames) täydennettynä NHL:n otteluohjelmalla ja arkistolla.
    Tulevien otteluiden aloitusajat haetaan kerran päivässä (data/freetv.json)."""
    items = CFG.get("freeGames") or []
    path = os.path.join(DATA, "freetv.json")
    cache = load_json(path, {})
    sig = json.dumps(items, sort_keys=True)
    if cache.get("date") != hel_today.isoformat() or cache.get("sig") != sig:
        sched, weeks = {}, set()
        for it in items:
            d = dt.date.fromisoformat(it["date"])
            if not (hel_today - dt.timedelta(days=1) <= d <= hel_today + dt.timedelta(days=70)):
                continue
            if any(w <= d - dt.timedelta(days=1) and d <= w + dt.timedelta(days=6) for w in weeks):
                continue
            wk = d - dt.timedelta(days=1)
            data = get(f"{API}/schedule/{wk.isoformat()}") or {}
            weeks.add(wk)
            for day in data.get("gameWeek") or []:
                for g in day.get("games") or []:
                    a, h = team(g["awayTeam"].get("abbrev")), team(g["homeTeam"].get("abbrev"))
                    sched[f"{min(a, h)}-{max(a, h)}-{day.get('date')}"] = {"away": a, "home": h, "start": g.get("startTimeUTC"), "et": day.get("date")}
        cache = {"date": hel_today.isoformat(), "sig": sig, "sched": sched}
        save_json(path, cache)
    sched = cache.get("sched") or {}
    arch = {}
    for it in items:
        d = dt.date.fromisoformat(it["date"])
        for et in (d, d - dt.timedelta(days=1)):
            fn = os.path.join(DATA, "archive", f"{et.isoformat()}.json")
            if fn not in arch:
                arch[fn] = load_json(fn, {}).get("games") or {}
    out = []
    for it in items:
        d = dt.date.fromisoformat(it["date"])
        t1, t2 = sorted(it["teams"])
        e = {"ch": it["ch"], "date": it["date"], "away": it["teams"][0], "home": it["teams"][1], "start": None, "status": "upcoming"}
        for et in (d, d - dt.timedelta(days=1)):
            for g in arch.get(os.path.join(DATA, "archive", f"{et.isoformat()}.json"), {}).values():
                if sorted((g["away"], g["home"])) == [t1, t2]:
                    e.update(away=g["away"], home=g["home"], start=g.get("start"), status="final", score=score_txt(g), slug=game_slug(et.isoformat(), g))
            if e["status"] == "upcoming":
                m = sched.get(f"{t1}-{t2}-{et.isoformat()}")
                if m:
                    e.update(away=m["away"], home=m["home"], start=m["start"])
        if e["status"] != "final" and d < hel_today:
            e["status"] = "past"
        out.append(e)
    return out


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
            notice = {"title": n["title"], "text": n["text"], "url": n.get("url", "")}

    try:
        free_tv = resolve_free_games(hel_today)
    except Exception as e:
        log("ilmaisottelut epäonnistuivat", e)
        free_tv = []
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
        "freeTv": free_tv,
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
    f = _font("inter-latin-700-normal", int(sz * .5))
    xx = x + sz * 1.15
    for ch in "PUNALAMPPU":  # väljä kirjainväli kuten sivuston logossa
        d.text((xx, y + sz / 2), ch, font=f, fill=INK, anchor="lm")
        xx += d.textlength(ch, font=f) + sz * .07


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
    f = _font("inter-latin-700-normal", 84 * S2)
    sp = 14 * S2
    tw = sum(d.textlength(ch, font=f) for ch in "PUNALAMPPU") + sp * 9
    xx = W // 2 - tw / 2
    for ch in "PUNALAMPPU":
        d.text((xx, 450 * S2), ch, font=f, fill=INK, anchor="lm")
        xx += d.textlength(ch, font=f) + sp
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
<link rel="icon" href="/favicon.ico?v=2" sizes="any"><link rel="icon" href="/favicon.svg?v=2" type="image/svg+xml"><link rel="icon" href="/favicon-48.png?v=2" sizes="48x48" type="image/png"><link rel="icon" href="/favicon-96.png?v=2" sizes="96x96" type="image/png"><link rel="apple-touch-icon" href="/apple-touch-icon.png?v=2"><link rel="manifest" href="/manifest.webmanifest"><link rel="alternate" type="application/rss+xml" title="Punalamppu – suomalaiset yön NHL-kierroksella" href="/rss.xml"><meta name="theme-color" content="#0B1118"><meta name="robots" content="max-image-preview:large"><link rel="stylesheet" href="/static.css">{ld}</head>
<body><div class="wrap">{site_header(path)}
<main>{boxify(body)}</main>{footer()}</div><script data-goatcounter="https://punalamppu.goatcounter.com/count" async src="https://gc.zgo.at/count.js"></script><script>if("serviceWorker"in navigator)addEventListener("load",()=>navigator.serviceWorker.register("/sw.js").catch(()=>{{}}))</script></body></html>"""


def footer():
    return ('<footer class="foot"><div class="fgrid">'
            '<div class="fbrand"><a class="brand sm" href="/"><img src="/logo-mark.svg" alt="" width="26" height="26"><span>PUNALAMPPU</span></a>'
            '<p>Yön NHL-tulokset, maalikoosteet ja suomalaiset suomeksi. Päivittyy automaattisesti joka yö ja aamu.</p></div>'
            '<div><h4>NHL</h4><a href="/">Yön tulokset</a><a href="/tulokset/">Tulokset päivittäin</a><a href="/joukkueet/">Joukkueet</a><a href="/otteluohjelma/">Otteluohjelma</a><a href="/sarjataulukko/">Sarjataulukko</a><a href="/pisteporssi/">Pistepörssi</a><a href="/pudotuspelit/">Pudotuspelitodennäköisyydet</a><a href="/ottelut/">Otteluarkisto</a></div>'
            '<div><h4>Suomalaiset</h4><a href="/suomalaiset/">Kaikki suomalaiset</a><a href="/uutiset/">Uutiset</a><a href="/koosteet/">Päivittäiset koosteet</a><a href="/#suomalaiset">Yön suomalaistilastot</a><a href="/virstanpylvaat/">Virstanpylväät</a><a href="/kaikkien-aikojen-suomalaiset/">Kaikkien aikojen suomalaiset</a><a href="/kalenteri/suomalaiset.ics">Kalenteri (.ics)</a><a href="/rss.xml">RSS-syöte</a></div>'
            '<div><h4>Katso NHL:ää</h4><a href="/nhl-tv/">NHL tv-lähetykset</a><a href="/nhl-tv/#ilmaisottelut">Ilmaisottelut</a><a href="/nhl-helsinki-2026/">NHL Helsinki 2026</a></div>'
            '<div><h4>Sivusto</h4><a href="/tietoa.html">Tietoa sivustosta</a><a href="/yhteys.html">Ota yhteyttä</a><a href="/tietosuoja.html">Tietosuoja</a></div>'
            '</div>'
            f'<p class="legal">{esc(CFG["siteName"])} on itsenäinen harrastussivusto, jolla ei ole yhteyttä National Hockey Leagueen (NHL) '
            'tai sen joukkueisiin. NHL ja joukkueiden nimet ovat omistajiensa tavaramerkkejä. Tulos- ja tilastotiedot: NHL.com. '
            'Edistyneet tilastot: MoneyPuck.com. Maalikoosteet: NHL.com. '
            'Sivusto käyttää tekoälyä: sivusto ja sen automaattiset koosteet on tehty tekoälyn avulla, ja ylläpitäjä tarkastaa sisällön aina sitä muutettaessa. <a href="/tietoa.html#tekoaly">Lue lisää</a>.</p></footer>')


def tname(a):
    return TEAMS.get(a, (a, a))[0]


def game_slug(gd, g):
    return f"{gd}-{g['away'].lower()}-{g['home'].lower()}"


def yt_url(gd, g):
    y, m, d = gd.split("-")
    months = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
    q = f"NHL Highlights | {TEAMS.get(g['away'], ('', g['away']))[1]} vs. {TEAMS.get(g['home'], ('', g['home']))[1]} | {months[int(m) - 1]} {d}, {y}"
    return "https://www.youtube.com/results?search_query=" + urllib.parse.quote(q)


NHL_PLAYER = "https://players.brightcove.net/6415718365001/D3UCGynRWU_default/index.html?videoId="  # NHL.comin oma upotuslinkki ("Embed Video")


def nhl_vid(g):
    m = re.search(r"(\d{10,})/?$", g.get("recapUrl") or "")
    return m.group(1) if m else ""


def has_video(g):
    return bool(nhl_vid(g) or (g.get("videoId") and re.fullmatch(r"[A-Za-z0-9_-]{6,20}", g["videoId"])))


def video_block(g, gd):
    vid = g.get("videoId")
    nv = nhl_vid(g)
    if nv:
        return (f'<section id="kooste" class="yt" data-id="{nv}"><button type="button" class="play" onclick="kaNHL(this.parentNode)"><span>{ic("play")}</span>Katso maalikooste</button>'
                f'<p class="mute">Video: NHL.com (NHL:n virallinen upotussoitin). Video ladataan NHL:n palvelusta vasta painettaessa.</p></section>'
                '<script>function kaNHL(d){d.innerHTML=\'<iframe src="' + NHL_PLAYER + '\'+d.dataset.id+\'&autoplay=true" title="Maalikooste – NHL.com" allow="autoplay; encrypted-media; picture-in-picture; fullscreen" allowfullscreen></iframe><p class="mute">Video: NHL.com</p>\'}</script>')
    if not vid or not re.fullmatch(r"[A-Za-z0-9_-]{6,20}", vid):
        return (f'<section id="kooste" class="yt wait"><b>{ic("clock")}Maalikooste tulossa</b>'
                '<p class="mute">Kooste ilmestyy tälle sivulle automaattisesti, kun NHL julkaisee sen – yleensä noin tunnin kuluessa ottelun päättymisestä.</p></section>')
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
{('<h2>Saman yön muut ottelut</h2><ul class="rows">' + ''.join(f"<li><a class='mrow' href='/ottelut/{game_slug(gd, o)}.html'>{tbadge(o['away'], 'mini')}<span>{esc(tname(o['away']))} – {esc(tname(o['home']))}</span>{tbadge(o['home'], 'mini')}<b>{esc(score_txt(o))}</b>{ic('play', 'ic vid') if has_video(o) else ''}{ic('chev')}</a></li>" for o in others) + '</ul>') if others else ''}
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


TEAMDATA = {}


def build_site(data):
    TEAMDATA.update(fetch_teams(now_utc()))
    hel_today = now_utc().astimezone(HEL).date()
    ALLTIME.update(fetch_alltime(now_utc()))
    try:
        compute_milestones(data, hel_today)
    except Exception as e:
        log("virstanpylväät epäonnistuivat", e)
    try:
        ODDS.update(playoff_odds(data))
    except Exception as e:
        log("pudotuspelisimulaatio epäonnistui", e)
    for f in data["finns"] + data["finnGoalies"]:
        MILE_HTML[f[0]] = mile_html_for(f[0])
    rh, rt, rp = build_recap(data["gameDate"], data["games"], data, True) if data["games"] else ("", "", [])
    data["recap"] = rh
    hl = headline_for(data["games"], data) if data["games"] else ""
    if hl and rt:
        first, rest = (rt.split("\n", 1) + [""])[:2]
        rt = f"{first}\n{hl}.\n{rest}"
    data["odds"] = {a: round(v["p"], 3) for a, v in ODDS.items()}
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
    save_json(os.path.join(OUT, "recap.json"), {"gameDate": data["gameDate"], "text": rt, "lines": rp, "games": len(data["games"]),
                                                "pending": len(data["pending"]), "url": f"/koosteet/{data['gameDate']}/"})

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
    arch_days = {}
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
        arch_days[d] = glist
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
            days.append(f"<h2>{esc(fi_date(d).capitalize())}</h2><ul>{''.join(lis)}</ul><p class='small'><a href='/tulokset/{d}/'>Kaikki yön tulokset ja suomalaiset {ic('chev')}</a></p>")
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
        f"<h1>Suomalaiset NHL:ssä {season_label(gd)}</h1>" + cal_box("suomalaiset.ics", "Kaikki suomalaisten ottelut kalenteriin")
        + "<p class='small'><a href='/virstanpylvaat/'>Lähestyvät virstanpylväät</a> · <a href='/kaikkien-aikojen-suomalaiset/'>Kaikkien aikojen suomalaiset</a></p>"
        + f"<h2>Kenttäpelaajat</h2><div class='tw'><table class='t'><tr><th>Pelaaja</th><th>Joukkue</th><th>O</th><th>M</th><th>S</th><th>P</th></tr>{''.join(rows)}</table></div>"
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
    # --- NHL tv-lähetykset ja ilmaisottelut
    free = data.get("freeTv") or []
    def frow(e):
        when = ""
        if e.get("start"):
            st_ = dt.datetime.fromisoformat(e["start"].replace("Z", "+00:00")).astimezone(HEL)
            when = f"{['ma', 'ti', 'ke', 'to', 'pe', 'la', 'su'][st_.weekday()]} {st_.day}.{st_.month}. klo {st_:%H.%M}"
        else:
            d_ = dt.date.fromisoformat(e["date"])
            when = f"{['ma', 'ti', 'ke', 'to', 'pe', 'la', 'su'][d_.weekday()]} {d_.day}.{d_.month}."
        fins = finn_by_team(data, e["away"], e["home"])
        right = f"<b class='fsc'>{esc(e['score'])}</b>" if e.get("score") else ""
        inner = (f"<div class='ftop'><span class='gt'>{esc(when)}</span><span class='chan'>{esc(e['ch'])}</span></div>"
                 f"<div class='fmid'><span class='tm'>{tbadge(e['away'], 'mini')}{esc(tname(e['away']))}</span><span class='mute'>–</span><span class='tm'>{tbadge(e['home'], 'mini')}{esc(tname(e['home']))}</span>{right}</div>"
                 + (f"<div class='fins2'>{FLAG}{esc(', '.join(short_name(n) for n in fins))}</div>" if fins and e["status"] == "upcoming" else ""))
        return (f"<li class='frow'><a href='/ottelut/{e['slug']}.html'>{inner}</a></li>" if e.get("slug") else f"<li class='frow'>{inner}</li>")
    up_ = [e for e in free if e["status"] == "upcoming"]
    past_ = [e for e in free if e["status"] != "upcoming"][::-1]
    tv = CFG.get("tvInfo") or {}
    srcs = " · ".join(f"<a href='{esc(u)}' rel='noopener'>{esc(n)}</a>" for n, u in CFG.get("freeGamesSources") or [])
    nxt_free = up_[0] if up_ else None
    lead_free = (f"Seuraava ilmaisottelu: {tname(nxt_free['away'])} – {tname(nxt_free['home'])} ({nxt_free['ch']})." if nxt_free else "")
    faq_tv = [
        ("Mistä NHL näkyy Suomessa?", "Kaudella 2026–27 suurin osa otteluista näkyy Viaplayssa (noin 1 150 runkosarjaottelua). Disney+ näyttää 160 runkosarjaottelua ESPN:n lähetyksinä. Ilmaiskanavista MTV Sub näyttää yhden ottelun viikossa, yleensä sunnuntaisin, ja Star Channel valikoituja Disney+:n otteluita."),
        ("Näkyykö NHL ilmaiseksi?", "Kyllä, osa otteluista. MTV Sub näyttää NHL-ottelun lähes joka sunnuntai, ja Star Channel sekä Viaplay TV näyttävät yksittäisiä otteluita ilmaiseksi. Tulevat ilmaisottelut näet tältä sivulta."),
        ("Mistä näkee kaikki NHL-ottelut?", "Yksikään palvelu ei näytä Suomessa kaikkia otteluita. Viaplay näyttää suurimman osan, ja Disney+ näyttää 160 runkosarjaottelua yksinoikeudella."),
        ("Mihin aikaan NHL-ottelut alkavat Suomessa?", "Useimmat ottelut alkavat Suomen aikaa yöllä klo 1.30–5.00. Viikonloppuisin osa otteluista pelataan Suomen aikaa jo iltapäivällä tai illalla."),
    ]
    tvrows = "".join(f"<li><b>{esc(n)}</b><span>{esc(t)}</span></li>" for n, t in tv.get("items") or [])
    body_tv = (f"<h1>NHL tv-lähetykset Suomessa {esc(tv.get('season', ''))}</h1>"
               f"<p class='lead'>Missä NHL näkyy ja mitkä ottelut näkee ilmaiseksi? Kokosimme kauden lähetysoikeudet ja ilmaiskanavien ottelut samalle sivulle. {esc(lead_free)}</p>"
               f"<h2>Missä NHL näkyy</h2><ul class='tvlist'>{tvrows}</ul><p class='mute small'>{esc(tv.get('note', ''))}</p>"
               + (f"<p class='small'><a href='{esc(tv['more'][1])}' rel='noopener'>{esc(tv['more'][0])} {ic('chev')}</a></p>" if tv.get("more") else "")
               + f"<h2 id='ilmaisottelut'>Tulevat ilmaisottelut</h2>"
               + (f"<ul class='rows'>{''.join(frow(e) for e in up_)}</ul>" if up_ else "<p>Ei tiedossa olevia tulevia ilmaisotteluita.</p>")
               + f"<p class='mute small'>Kellonajat Suomen aikaa. Aika näkyy, kun NHL on vahvistanut ottelun aloitusajan. {esc(CFG.get('freeGamesNote', ''))}</p>"
               + (f"<h2>Kauden ilmaisottelut tähän mennessä</h2><ul class='rows'>{''.join(frow(e) for e in past_)}</ul>" if past_ else "")
               + "<h2>Usein kysyttyä</h2>" + "".join(f"<h3>{esc(q)}</h3><p>{esc(a)}</p>" for q, a in faq_tv)
               + (f"<h2>Lähteet</h2><p class='small'>{srcs}</p>" if srcs else ""))
    tv_jl = {"@context": "https://schema.org", "@type": "FAQPage",
             "mainEntity": [{"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faq_tv]}
    os.makedirs(os.path.join(OUT, "nhl-tv"), exist_ok=True)
    open(os.path.join(OUT, "nhl-tv", "index.html"), "w", encoding="utf-8").write(page(
        f"NHL tv-lähetykset Suomessa {tv.get('season', '')} – missä NHL näkyy ja ilmaisottelut | {CFG['siteName']}",
        f"Missä NHL näkyy Suomessa kaudella {tv.get('season', '')}? Viaplay, Disney+ (ESPN), MTV Sub ja Star Channel. Katso myös tulevat NHL-ilmaisottelut kellonaikoineen.",
        "/nhl-tv/", body_tv, tv_jl))
    urls.append("/nhl-tv/")

    # --- NHL Helsinki 2026 (Global Series Finland)
    gs = [e for e in free if e["date"] in ("2026-11-12", "2026-11-14") and {e["away"], e["home"]} == {"CAR", "SEA"}]
    if gs:
        sk_by = {f[0]: f for f in data["finns"]}
        gk_by = {f[0]: f for f in data["finnGoalies"]}
        def finlist(t):
            out = []
            for n in finn_by_team(data, t):
                f = sk_by.get(n) or gk_by.get(n)
                line = (f"{f[3]} ott., {f[4]}+{f[5]}={f[6]}" if n in sk_by else f"maalivahti, {f[2]} ott., TO% {f[6]}") if f else ""
                link = f"<a href='/suomalaiset/{slugs[n]}.html'>{esc(n)}</a>" if n in slugs else esc(n)
                out.append(f"<li><div class='mrow'>{tbadge(t, 'mini')}<span>{link}</span><span class='mute'>{esc(line)}</span></div></li>")
            return "".join(out)
        def gsrow(i, e):
            when = "to 12.11. klo 19.00" if e["date"] == "2026-11-12" else "la 14.11. klo 20.00"
            if e.get("start"):
                st_ = dt.datetime.fromisoformat(e["start"].replace("Z", "+00:00")).astimezone(HEL)
                when = f"{['ma', 'ti', 'ke', 'to', 'pe', 'la', 'su'][st_.weekday()]} {st_.day}.{st_.month}. klo {st_:%H.%M}"
            res = f"<b class='fsc'>{esc(e['score'])}</b>" if e.get("score") else ""
            inner = (f"<div class='ftop'><span class='gt'>Ottelu {i} · {esc(when)}</span><span class='chan'>Viaplay TV (ilmainen)</span></div>"
                     f"<div class='fmid'><span class='tm'>{tbadge(e['away'], 'mini')}{esc(tname(e['away']))}</span><span class='mute'>–</span>"
                     f"<span class='tm'>{tbadge(e['home'], 'mini')}{esc(tname(e['home']))}</span>{res}</div>"
                     + ("<div class='fins2'>Tulos, maalit ja maalikooste ottelusivulla →</div>" if e.get("slug") else ""))
            return f"<li class='frow'><a href='/ottelut/{e['slug']}.html'>{inner}</a></li>" if e.get("slug") else f"<li class='frow'>{inner}</li>"
        faq_h = [
            ("Milloin NHL pelaa Helsingissä 2026?", "NHL Global Series Finland pelataan Helsingin Veikkaus Arenalla torstaina 12.11.2026 klo 19.00 ja lauantaina 14.11.2026 klo 20.00 Suomen aikaa. Vastakkain ovat Carolina Hurricanes ja Seattle Kraken."),
            ("Missä Helsingin NHL-ottelut näkyvät tv:ssä?", "Molemmat ottelut näkyvät suorina ja ilmaiseksi Viaplay TV -kanavalla (kanavapaikka 21) studiolähetyksen kera sekä Viaplayssa."),
            ("Ketkä suomalaiset pelaavat Helsingin NHL-otteluissa?", "Carolinan riveissä pelaavat " + ", ".join(finn_by_team(data, "CAR")) + " ja Seattlen riveissä " + ", ".join(finn_by_team(data, "SEA")) + " (kokoonpanotilanne päivittyy automaattisesti)."),
            ("Mistä saa liput NHL Helsinki -otteluihin?", "Liput myydään Ticketmasterissa (ticketmaster.fi)."),
            ("Onko NHL pelannut Helsingissä aiemmin?", "On. Veikkaus Arena (entinen Hartwall Arena) on isännöinyt aiemmin seitsemää NHL:n runkosarjaottelua, viimeksi vuonna 2018, kun Florida Panthers ja Winnipeg Jets pelasivat kaksi ottelua. Suomessa NHL on pelannut myös Tampereella vuosina 2022 ja 2025."),
        ]
        body_h = ("<h1>NHL Helsinki 2026 – Global Series Finland</h1>"
                  "<p class='lead'>Carolina Hurricanes ja Seattle Kraken pelaavat kaksi NHL:n runkosarjaottelua Helsingin Veikkaus Arenalla 12. ja 14. marraskuuta 2026. "
                  "Kokosimme tälle sivulle otteluajat, tv-lähetykset, suomalaispelaajat ja otteluiden jälkeen tulokset ja maalikoosteet.</p>"
                  f"<h2>Ottelut</h2><ul class='rows'>{''.join(gsrow(i + 1, e) for i, e in enumerate(sorted(gs, key=lambda e: e['date'])))}</ul>"
                  "<p class='mute small'>Kellonajat Suomen aikaa. Paikka: Veikkaus Arena, Areenankuja 1, Helsinki.</p>"
                  "<h2>Tv-lähetykset</h2><p>Molemmat ottelut näkyvät <b>ilmaiseksi Viaplay TV -kanavalla</b> (kanavapaikka 21) studiolähetyksen kera sekä Viaplayssa. "
                  "<a href='/nhl-tv/'>Katso kaikki NHL:n tv-lähetykset ja ilmaisottelut</a>.</p>"
                  f"<h2>Suomalaiset Carolina Hurricanesissa</h2><ul class='rows'>{finlist('CAR') or '<li>Ei suomalaisia kokoonpanossa.</li>'}</ul>"
                  f"<h2>Suomalaiset Seattle Krakenissa</h2><ul class='rows'>{finlist('SEA') or '<li>Ei suomalaisia kokoonpanossa.</li>'}</ul>"
                  "<p class='mute small'>Kauden tilastot ja kokoonpanot päivittyvät automaattisesti NHL:n tiedoista.</p>"
                  "<h2>Liput</h2><p>Liput myydään Ticketmasterissa: <a href='https://www.ticketmaster.fi/artist/1197393?venueId=425' rel='noopener'>ticketmaster.fi</a>.</p>"
                  "<h2>Usein kysyttyä</h2>" + "".join(f"<h3>{esc(q)}</h3><p>{esc(a)}</p>" for q, a in faq_h)
                  + "<h2>Lähteet</h2><p class='small'><a href='https://www.nhl.com/news/carolina-seattle-to-play-in-2026-global-series-finland' rel='noopener'>NHL.com</a> · "
                  "<a href='https://www.nhl.com/fi/news/nhl-global-series-huipentaa-helsingin-kiekkoviikon' rel='noopener'>NHL.com/fi</a></p>")
        ev = []
        for e in sorted(gs, key=lambda e: e["date"]):
            ev.append({"@type": "SportsEvent", "name": f"{tname(e['away'])} – {tname(e['home'])} (NHL Global Series Finland)",
                       "startDate": e.get("start") or (e["date"] + ("T19:00:00+02:00" if e["date"].endswith("12") else "T20:00:00+02:00")),
                       "location": {"@type": "Place", "name": "Veikkaus Arena", "address": "Areenankuja 1, 00240 Helsinki"},
                       "awayTeam": {"@type": "SportsTeam", "name": tname(e["away"])}, "homeTeam": {"@type": "SportsTeam", "name": tname(e["home"])},
                       "eventStatus": "https://schema.org/EventScheduled"})
        jl_h = {"@context": "https://schema.org", "@graph": ev + [{"@type": "FAQPage", "mainEntity": [
            {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faq_h]}]}
        os.makedirs(os.path.join(OUT, "nhl-helsinki-2026"), exist_ok=True)
        open(os.path.join(OUT, "nhl-helsinki-2026", "index.html"), "w", encoding="utf-8").write(page(
            f"NHL Helsinki 2026 – ottelut, ajat, tv ja suomalaiset | {CFG['siteName']}",
            "NHL Global Series Helsinki 12.11. ja 14.11.2026: Carolina Hurricanes – Seattle Kraken Veikkaus Arenalla. Otteluajat, ilmainen tv-lähetys, suomalaiset ja tulokset.",
            "/nhl-helsinki-2026/", body_h, jl_h))
        urls.append("/nhl-helsinki-2026/")

    write("/otteluohjelma/", f"NHL-otteluohjelma – tulevat ottelut Suomen aikaa | {CFG['siteName']}",
          "NHL:n otteluohjelma seuraavalle viikolle Suomen ajassa. Näet myös, missä otteluissa suomalaiset pelaavat.",
          f"<h1>NHL-otteluohjelma Suomen aikaa</h1>{cal_box('suomalaiset.ics', 'Suomalaisten ottelut kalenteriin')}<p class='mute'>Kellonajat Suomen aikaa. Otsikon päivä on NHL:n pelipäivä Pohjois-Amerikassa; ottelut pelataan Suomessa seuraavana yönä.</p>{tv_html(data)}{orows or '<p>Ei tulevia otteluita tiedossa.</p>'}")

    # --- pelipäivien tulossivut
    build_day_pages(data, arch_days, urls)

    # --- joukkuesivut, kalenterit, virstanpylväät, pudotuspelit
    try:
        build_calendars(data, urls)
    except Exception as e:
        log("kalenterit epäonnistuivat", e)
    build_team_pages(data, arch_days, urls)
    build_alltime_pages(data, urls)
    build_odds_page(data, urls)

    # --- automaattiset uutiset
    try:
        build_news(data, arch_days, urls)
    except Exception as e:
        log("uutiset epäonnistuivat", e)

    # etusivun "Tuoreimmat uutiset" – data.json kirjoitetaan uudelleen uutislistan kanssa
    data["news"] = [{"t": t, "u": u, "k": k, "d": p[:10]} for p, t, u, k, ld in (NEWS.get("items") or [])[:6]]
    save_json(os.path.join(OUT, "data.json"), data, pretty=False)

    # --- RSS-syöte
    build_rss()

    # --- sitemap & robots
    today = now_utc().astimezone(HEL).date().isoformat()
    sm = "".join(f"<url><loc>{base}{u}</loc><lastmod>{today}</lastmod></url>" for u in urls)
    open(os.path.join(OUT, "sitemap.xml"), "w", encoding="utf-8").write(
        f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{sm}</urlset>')
    # Google News -sivukartta: viimeisen kahden vuorokauden koosteet
    cut = (now_utc().astimezone(HEL).date() - dt.timedelta(days=2)).isoformat()
    news = []
    for d, nice, h, ld in KOOSTEET:
        pubd = (dt.date.fromisoformat(d) + dt.timedelta(days=1)).isoformat()
        if pubd >= cut:
            news.append(f"<url><loc>{base}/koosteet/{d}/</loc><news:news><news:publication><news:name>Punalamppu</news:name>"
                        f"<news:language>fi</news:language></news:publication><news:publication_date>{pubd}T07:00:00+02:00</news:publication_date>"
                        f"<news:title>{html.escape(h)}</news:title></news:news></url>")
    for p, t, u, k, ld in (NEWS.get("items") or []):
        if k != "Kooste" and p[:10] >= cut:
            news.append(f"<url><loc>{base}{u}</loc><news:news><news:publication><news:name>Punalamppu</news:name>"
                        f"<news:language>fi</news:language></news:publication><news:publication_date>{p}</news:publication_date>"
                        f"<news:title>{html.escape(t)}</news:title></news:news></url>")
    open(os.path.join(OUT, "news-sitemap.xml"), "w", encoding="utf-8").write(
        '<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
        'xmlns:news="http://www.google.com/schemas/sitemap-news/0.9">' + "".join(news) + "</urlset>")
    open(os.path.join(OUT, "robots.txt"), "w", encoding="utf-8").write(f"User-agent: *\nAllow: /\nSitemap: {base}/sitemap.xml\nSitemap: {base}/news-sitemap.xml\n")
    domain = re.sub(r"^https?://", "", base).split("/")[0]
    if not domain.endswith("github.io"):
        open(os.path.join(OUT, "CNAME"), "w").write(domain + "\n")
    log("valmis:", len(urls), "sivua,", len(data["games"]), "ottelua,", len(data["pending"]), "kesken")


WD_SHORT = ["ma", "ti", "ke", "to", "pe", "la", "su"]


def tslug(a):
    return slugify(tname(a))


def fi_dshort(d):
    x = dt.date.fromisoformat(d)
    return f"{WD_SHORT[x.weekday()]} {x.day}.{x.month}."


def hel_when(iso):
    t = dt.datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(HEL)
    return f"{WD_SHORT[t.weekday()]} {t.day}.{t.month}. klo {t:%H.%M}"


def write_page(path, title, desc, body, jl=None, og=None, urls=None):
    os.makedirs(os.path.join(OUT, path.strip("/")), exist_ok=True)
    open(os.path.join(OUT, path.strip("/"), "index.html"), "w", encoding="utf-8").write(page(title, desc, path, body, jl, og))
    if urls is not None:
        urls.append(path)


def crumbs(items):
    base = CFG["baseUrl"].rstrip("/")
    return {"@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": i + 1, "name": n, "item": base + u} for i, (n, u) in enumerate(items)]}


def scorers_line(g, slugs):
    """Maalintekijät lyhyesti: "Aho 2, Kakko" – suomalaiset lihavoituna."""
    cnt = {}
    for x in g.get("goals") or []:
        if x.get("p") == "JA" and x.get("tag") == "VL":
            continue
        cnt.setdefault(x["who"], [0, x.get("fin")])
        cnt[x["who"]][0] += 1
    parts = []
    for n, (c, fin) in cnt.items():
        t = esc(short_name(n)) + (f" {c}" if c > 1 else "")
        parts.append(f"<b class='fi-n'>{t}</b>" if fin or n in slugs else t)
    return ", ".join(parts)


FEED = []
KOOSTEET = []


def build_rss():
    base = CFG["baseUrl"].rstrip("/")
    items = []
    for e in sorted(FEED, key=lambda x: x["date"], reverse=True)[:30]:
        x = dt.date.fromisoformat(e["date"])
        pub = dt.datetime(x.year, x.month, x.day, 9, 0, tzinfo=HEL) + dt.timedelta(days=1)
        link = f"{base}/koosteet/{e['date']}/"
        body = (f"<p><b>{html.escape(e.get('lead') or '')}</b></p>" if e.get("lead") else "") + (("<p>" + "</p><p>".join(html.escape(t) for t in e["plain"]) + "</p>") if e["plain"] else f"<p>{html.escape(e['desc'])}</p>")
        body += f'<p><a href="{base}/tulokset/{e["date"]}/">Kaikki tulokset, tehot ja maalikoosteet</a></p>'
        items.append((pub.isoformat(), f"<item><title>{html.escape(e.get('title') or 'Suomalaiset yön NHL-kierroksella ' + e['nice'])}</title><link>{link}</link><guid isPermaLink=\"true\">{link}</guid>"
                     f"<pubDate>{pub.strftime('%a, %d %b %Y %H:%M:%S %z')}</pubDate><description>{html.escape(body)}</description></item>"))
    for p, t, u, k, ld in (NEWS.get("items") or []):
        if k == "Kooste":
            continue
        pub = dt.datetime.fromisoformat(p)
        items.append((p, f"<item><title>{html.escape(t)}</title><link>{base}{u}</link><guid isPermaLink=\"true\">{base}{u}</guid>"
                         f"<pubDate>{pub.strftime('%a, %d %b %Y %H:%M:%S %z')}</pubDate><category>{html.escape(k)}</category>"
                         f"<description>{html.escape('<p>' + html.escape(ld) + '</p>')}</description></item>"))
    items = [x[1] for x in sorted([x if isinstance(x, tuple) else ("", x) for x in items], key=lambda x: x[0], reverse=True)][:40]
    xml = ('<?xml version="1.0" encoding="UTF-8"?><rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom"><channel>'
           f"<title>Punalamppu – NHL-uutiset ja suomalaiset</title><link>{base}/</link>"
           f'<atom:link href="{base}/rss.xml" rel="self" type="application/rss+xml"/>'
           "<description>Joka aamu: suomalaisten tehot yön NHL-otteluista, tulokset ja maalikoosteet.</description><language>fi</language>"
           + "".join(items) + "</channel></rss>")
    open(os.path.join(OUT, "rss.xml"), "w", encoding="utf-8").write(xml)


def build_day_pages(data, arch_days, urls):
    slugs = data["finnSlugs"]
    ds = sorted(d for d, gl in arch_days.items() if gl)
    links = []
    for i, d in enumerate(ds):
        gl = sorted(arch_days[d], key=lambda g: g.get("start") or "")
        x = dt.date.fromisoformat(d)
        nice = f"{x.day}.{x.month}.{x.year}"
        cards = []
        finrows = []
        for g in gl:
            slug = game_slug(d, g)
            sc = scorers_line(g, slugs)
            cards.append(f"<li class='frow'><a href='/ottelut/{slug}.html'>"
                         f"<div class='ftop'><span class='gt'>{esc(hel_when(g['start'])) if g.get('start') else ''}</span>"
                         + (f"<span class='chan'>{ic('play')}Kooste</span>" if has_video(g) else "") + "</div>"
                         f"<div class='fmid'><span class='tm'>{tbadge(g['away'], 'mini')}{esc(tname(g['away']))}</span><span class='mute'>–</span>"
                         f"<span class='tm'>{tbadge(g['home'], 'mini')}{esc(tname(g['home']))}</span><b class='fsc'>{esc(score_txt(g))}</b></div>"
                         + (f"<div class='fins2 sc'>Maalit: {sc}</div>" if sc else "") + "</a></li>")
            for f in g.get("finStats") or []:
                nm = f"<a href='/suomalaiset/{slugs[f['name']]}.html'>{esc(f['name'])}</a>" if f["name"] in slugs else esc(f["name"])
                if f.get("pos") == "MV":
                    line = f"{f.get('saves', '–')}/{f.get('shots', '–')} torjuntaa" + (" · voitto" if f.get("dec") == "W" else "")
                    finrows.append((-1, f"<tr><td>{tbadge(f['team'], 'mini')} {nm}</td><td colspan='4' class='mute'>MV · {esc(line)}</td></tr>"))
                else:
                    pm = f"{f['pm']:+d}" if isinstance(f.get("pm"), int) else "–"
                    finrows.append((f.get("p", 0) * 10 + f.get("g", 0), f"<tr><td>{tbadge(f['team'], 'mini')} {nm}</td><td>{f.get('g', 0)}</td><td>{f.get('a', 0)}</td><td><b>{f.get('p', 0)}</b></td><td>{pm}</td></tr>"))
        prev_ = f"<a href='/tulokset/{ds[i - 1]}/'>‹ {esc(fi_dshort(ds[i - 1]))}</a>" if i > 0 else "<span></span>"
        next_ = f"<a href='/tulokset/{ds[i + 1]}/'>{esc(fi_dshort(ds[i + 1]))} ›</a>" if i + 1 < len(ds) else "<span></span>"
        fin_pts = sorted([f for g in gl for f in g.get("finStats") or [] if f.get("p")], key=lambda f: -f.get("p", 0))
        best = "; ".join(f"{short_name(f['name'])} {f.get('g', 0)}+{f.get('a', 0)}" for f in fin_pts[:3])
        desc = (f"NHL-tulokset {nice}: " + ", ".join(f"{g['away']}–{g['home']} {g.get('awayScore')}–{g.get('homeScore')}" for g in gl[:5])
                + (f". Suomalaiset: {best}." if best else "."))[:300]
        rec_html, _, rec_plain = build_recap(d, gl, data, d == data["gameDate"])
        body = (f"<h1>NHL-tulokset {esc(fi_date(d))}</h1>"
                f"<p class='lead'>{len(gl)} ottelua. Kellonajat Suomen aikaa. Avaa ottelu nähdäksesi maalit, ottelun tähdet ja maalikoosteen.</p>"
                f"<nav class='daynav'>{prev_}<a href='/tulokset/'>Kaikki päivät</a>{next_}</nav>"
                + (f"<h2>{FLAG}Suomalaisten tehot</h2><table class='t'><tr><th>Pelaaja</th><th>M</th><th>S</th><th>P</th><th>+/-</th></tr>{''.join(r for _, r in sorted(finrows, key=lambda x: -x[0]))}</table>" if finrows else "")
                + (f"<p class='kref'><a href='/koosteet/{d}/'>Lue yön suomalaiskooste →</a></p>" if rec_html else "")
                + f"<h2>Tulokset</h2><ul class='rows'>{''.join(cards)}</ul>")
        FEED.append({"date": d, "nice": nice, "html": rec_html, "plain": rec_plain, "desc": desc})
        if rec_html:
            kdesc = (" ".join(rec_plain[:3]) or desc)[:300]
            res_list = "".join(f"<li><a class='mrow' href='/ottelut/{game_slug(d, g)}.html'>{tbadge(g['away'], 'mini')}<span>{esc(tname(g['away']))} – {esc(tname(g['home']))}</span>{tbadge(g['home'], 'mini')}<b>{esc(score_txt(g))}</b>{ic('chev')}</a></li>" for g in gl)
            kprev = f"<a href='/koosteet/{ds[i - 1]}/'>‹ {esc(fi_dshort(ds[i - 1]))}</a>" if i > 0 else "<span></span>"
            knext = f"<a href='/koosteet/{ds[i + 1]}/'>{esc(fi_dshort(ds[i + 1]))} ›</a>" if i + 1 < len(ds) else "<span></span>"
            pubd = (dt.date.fromisoformat(d) + dt.timedelta(days=1)).isoformat()
            ahead, alead, abody = build_article(d, gl, data, d == data["gameDate"])
            htitle = ahead if ahead != "Suomalaiset yön NHL-kierroksella" else f"Suomalaiset yön NHL-kierroksella {nice}"
            kdesc = (alead or desc)[:300]
            kbody = (f"<p class='kdate'>Suomalaiset yön NHL-kierroksella {nice} · Julkaistu {esc(fi_date(pubd))}</p>"
                     f"<h1>{esc(htitle)}</h1>"
                     f"<p class='byline'>Punalamppu · Automaattinen kooste NHL:n tilastoista · tekoälyn avulla tehty, ihmisen tarkastamat tekstipohjat</p>"
                     f"<nav class='daynav'>{kprev}<a href='/koosteet/'>Kaikki koosteet</a>{knext}</nav>"
                     f"<div class='art'>{abody or rec_html}</div>"
                     f"<h2>Yön tulokset</h2><ul class='rows'>{res_list}</ul>"
                     f"<p class='small'><a href='/tulokset/{d}/'>Suomalaisten tehotaulukko ja kaikki yön ottelut {ic('chev')}</a></p>")
            kjl = {"@context": "https://schema.org", "@graph": [
                {"@type": "NewsArticle", "headline": htitle[:110], "datePublished": f"{pubd}T07:00:00+02:00",
                 "dateModified": now_utc().isoformat(timespec="minutes"), "inLanguage": "fi", "description": kdesc,
                 "author": {"@type": "Organization", "name": CFG["siteName"], "url": CFG["baseUrl"]},
                 "publisher": {"@type": "Organization", "name": CFG["siteName"], "logo": {"@type": "ImageObject", "url": CFG["baseUrl"].rstrip("/") + "/icon-512.png"}},
                 "mainEntityOfPage": CFG["baseUrl"].rstrip("/") + f"/koosteet/{d}/", "image": CFG["baseUrl"].rstrip("/") + "/og.png"},
                crumbs([("Punalamppu", "/"), ("Koosteet", "/koosteet/"), (nice, f"/koosteet/{d}/")])]}
            write_page(f"/koosteet/{d}/", f"{htitle} – suomalaiset NHL:ssä {nice} | {CFG['siteName']}" if htitle != f"Suomalaiset yön NHL-kierroksella {nice}" else f"{htitle} | {CFG['siteName']}", kdesc, kbody, kjl, urls=urls)
            KOOSTEET.append((d, nice, htitle, alead))
            FEED[-1]["title"] = htitle
            FEED[-1]["lead"] = alead
        ev = [{"@type": "SportsEvent", "name": f"{tname(g['away'])} – {tname(g['home'])}", "startDate": g.get("start") or d,
               "url": CFG["baseUrl"].rstrip("/") + f"/ottelut/{game_slug(d, g)}.html",
               "awayTeam": {"@type": "SportsTeam", "name": tname(g["away"])}, "homeTeam": {"@type": "SportsTeam", "name": tname(g["home"])},
               "location": {"@type": "Place", "name": g.get("venue") or tname(g["home"])}} for g in gl]
        jl = {"@context": "https://schema.org", "@graph": [crumbs([("Punalamppu", "/"), ("NHL-tulokset", "/tulokset/"), (nice, f"/tulokset/{d}/")])] + ev}
        write_page(f"/tulokset/{d}/", f"NHL-tulokset {nice} – maalit, suomalaiset ja koosteet | {CFG['siteName']}", desc, body, jl, urls=urls)
        links.append((d, len(gl), best))
    klist = "".join(f"<li><a class='krow' href='/koosteet/{d}/'><span class='gt'>Suomalaiset yön NHL-kierroksella {esc(n)}</span><b>{esc(h)}</b>"
                    f"<span class='mute'>{esc(ld)}</span></a></li>" for d, n, h, ld in reversed(KOOSTEET))
    write_page("/koosteet/", f"Suomalaiset NHL:ssä – päivittäiset koosteet | {CFG['siteName']}",
               "Joka aamu uusi kooste: miten suomalaisilla meni yön NHL-otteluissa. Maalit, syötöt, torjunnat ja virstanpylväät suomeksi.",
               "<h1>Koosteet</h1><p class='lead'>Joka aamu uusi kooste siitä, miten suomalaisilla meni yön NHL-otteluissa. Koosteet tuotetaan automaattisesti NHL:n tilastoista tekoälyn avulla. "
               "Koosteet voi tilata myös <a href='/rss.xml'>RSS-syötteenä</a> tai <a href='https://t.me/punalamppu' rel='noopener'>Telegramissa</a>.</p>"
               f"<h2>Uusimmat koosteet</h2><ul class='rows'>{klist or '<li>Ei vielä koosteita.</li>'}</ul>",
               {"@context": "https://schema.org", "@graph": [crumbs([("Punalamppu", "/"), ("Koosteet", "/koosteet/")])]}, urls=urls)
    rows = "".join(f"<li><a class='mrow' href='/tulokset/{d}/'><span>{esc(fi_date(d).capitalize())}</span><span class='mute'>{n} ottelua{(' · ' + esc(b)) if b else ''}</span>{ic('chev')}</a></li>" for d, n, b in reversed(links))
    write_page("/tulokset/", f"NHL-tulokset päivittäin – kaikki pelipäivät | {CFG['siteName']}",
               "NHL-tulokset pelipäivittäin suomeksi: kaikki ottelut, maalintekijät, suomalaisten tehot ja maalikoosteet.",
               "<h1>NHL-tulokset päivittäin</h1><p class='lead'>Jokaisen NHL-yön tulokset omalla sivullaan. Uusin ensin. Tuoreimmat tulokset löytyvät myös <a href='/'>etusivulta</a>.</p>"
               f"<h2>Pelipäivät</h2><ul class='rows'>{rows or '<li>Ei vielä tuloksia.</li>'}</ul>", urls=urls)


def build_team_pages(data, arch_days, urls):
    slugs = data["finnSlugs"]
    tdata = (TEAMDATA.get("teams") or {})
    stand = {}
    for dv in data["standings"]:
        tl = sorted(dv["teams"], key=lambda t: (-t[5], t[1]))
        for i, t in enumerate(tl):
            stand[t[0]] = (dv, i + 1, t)
    free = {(e["date"], frozenset((e["away"], e["home"]))): e["ch"] for e in data.get("freeTv") or []}
    have = set(urls)
    sk_by = {f[0]: f for f in data["finns"]}
    gk_by = {f[0]: f for f in data["finnGoalies"]}
    # arkiston ottelut varalle (jos joukkueen otteluohjelmaa ei saatu)
    arch_by_team = {}
    for d, gl in arch_days.items():
        for g in gl:
            for a in (g["away"], g["home"]):
                arch_by_team.setdefault(a, []).append((d, g))
    grid_divs = []
    for dv in data["standings"]:
        grid_divs.append((dv["name"], dv["conf"], [t[0] for t in sorted(dv["teams"], key=lambda t: (-t[5], t[1]))]))
    if not grid_divs:
        grid_divs = [("NHL", "", sorted(TEAMS, key=lambda a: tname(a)))]

    def tlink(a, on=False):
        return f"<a class='tchip{' on' if on else ''}' href='/joukkueet/{tslug(a)}/'>{tbadge(a, 'mini')}<span>{esc(TEAMS[a][1])}</span></a>"

    sl = season_label(data["gameDate"])
    for a in TEAMS:
        nm = tname(a)
        td = tdata.get(a) or {}
        games = td.get("games") or []
        # menneet ottelut
        past = []
        if games:
            for g in games:
                if g.get("state") in ("OFF", "FINAL") and g.get("as") is not None:
                    past.append(g)
        else:
            for d, g in sorted(arch_by_team.get(a, []), key=lambda x: x[0]):
                past.append({"date": d, "start": g.get("start"), "away": g["away"], "home": g["home"], "as": g.get("awayScore"), "hs": g.get("homeScore"),
                             "last": {"JA": "OT", "VL": "SO"}.get(g.get("final"), g.get("final") or "")})
        past = past[-10:][::-1]
        if games:
            up = [g for g in games if g.get("state") in NOT_STARTED][:8]
        else:
            up = [{"date": u["day"], "start": u.get("start"), "away": u["away"], "home": u["home"]} for u in data["upcoming"] if a in (u["away"], u["home"])][:8]

        def res_row(g):
            home = g["home"] == a
            opp = g["away"] if home else g["home"]
            my, their = (g["hs"], g["as"]) if home else (g["as"], g["hs"])
            win = my > their
            ext = {"OT": " JA", "SO": " VL"}.get(g.get("last") or "", "")
            slug = f"/ottelut/{g['date']}-{g['away'].lower()}-{g['home'].lower()}.html"
            inner = (f"<span class='wl {'w' if win else 'l'}'>{'V' if win else ('JA' if ext else 'H')}</span>"
                     f"<span class='gt'>{esc(fi_dshort(g['date']))}</span>{tbadge(opp, 'mini')}<span>{'vs.' if home else '@'} {esc(tname(opp))}</span>"
                     f"<b>{my}–{their}{ext}</b>")
            return f"<li><a class='mrow' href='{slug}'>{inner}{ic('chev')}</a></li>" if slug in have else f"<li><div class='mrow'>{inner}</div></li>"

        def up_row(g):
            home = g["home"] == a
            opp = g["away"] if home else g["home"]
            when = hel_when(g["start"]) if g.get("start") else fi_dshort(g["date"])
            pair = frozenset((g["away"], g["home"]))
            ch = free.get((g["date"], pair)) or free.get(((dt.date.fromisoformat(g["date"]) + dt.timedelta(days=1)).isoformat(), pair))
            return (f"<li><div class='mrow'><span class='gt wide'>{esc(when)}</span>{tbadge(opp, 'mini')}<span>{'vs.' if home else '@'} {esc(tname(opp))}"
                    + (f"<br><a class='chan' href='/nhl-tv/#ilmaisottelut'>Ilmaiseksi: {esc(ch)}</a>" if ch else "") + "</span></div></li>")

        st = stand.get(a)
        tiles = ""
        sub = "NHL-joukkue"
        if st:
            dv, rank, t = st
            gp, w, l, otl, pts, gf, ga = t[1], t[2], t[3], t[4], t[5], t[6], t[7]
            sub = f"{esc(dv['name'])}-divisioona · {rank}. sija"
            tiles = ("<div class='tiles'>" + "".join(f"<div class='tile'><b>{v}</b><small>{k}</small></div>" for k, v in
                     [("Ottelut", gp), ("Pisteet", pts), ("V–H–JA", f"{w}–{l}–{otl}"),
                      ("Pudotuspelit", pct_txt(ODDS[a]["p"])) if a in ODDS else ("Maalit", f"{gf}–{ga}")]) + "</div>")
        streak = ""
        if past:
            last5 = past[:5]
            streak = "".join(f"<span class='wl {'w' if ((g['hs'] > g['as']) if g['home'] == a else (g['as'] > g['hs'])) else 'l'}'>"
                             f"{'V' if ((g['hs'] > g['as']) if g['home'] == a else (g['as'] > g['hs'])) else ('JA' if g.get('last') in ('OT', 'SO') else 'H')}</span>" for g in last5)
        fins = finn_by_team(data, a)
        finrows = []
        for n in fins:
            link = f"<a href='/suomalaiset/{slugs[n]}.html'>{esc(n)}</a>" if n in slugs else esc(n)
            if n in sk_by:
                f = sk_by[n]
                finrows.append(f"<tr><td>{link}</td><td>{esc({'P': 'puolustaja', 'H': 'hyökkääjä'}.get(f[2], f[2]))}</td><td>{f[3]}</td><td>{f[4]}</td><td>{f[5]}</td><td><b>{f[6]}</b></td></tr>")
            elif n in gk_by:
                f = gk_by[n]
                finrows.append(f"<tr><td>{link}</td><td>maalivahti</td><td>{f[2]}</td><td colspan='3' class='mute'>{f[3]}–{f[4]}–{f[5]}, TO% {esc(f[6])}, PMK {esc(f[7])}</td></tr>")
        sk = sorted(td.get("skaters") or [], key=lambda r: (-r[5], -r[3], r[2]))[:15]
        def nmk(n):
            return (f"<a href='/suomalaiset/{slugs[n]}.html'>{esc(n)}</a> <span class='fi'>FIN</span>" if n in slugs else esc(n))
        skrows = "".join(f"<tr><td>{i + 1}. {nmk(r[0])}</td><td>{esc(r[1])}</td><td>{r[2]}</td><td>{r[3]}</td><td>{r[4]}</td><td><b>{r[5]}</b></td><td>{r[6]:+d}</td></tr>" for i, r in enumerate(sk))
        gkrows = "".join(f"<tr><td>{nmk(r[0])}</td><td>{r[1]}</td><td>{r[2]}–{r[3]}–{r[4]}</td><td>{fmt_sv(r[5]) if r[5] is not None else '–'}</td><td>{fmt_gaa(r[6]) if r[6] is not None else '–'}</td><td>{r[7]}</td></tr>"
                         for r in sorted(td.get("goalies") or [], key=lambda r: -r[1]))
        divtab = ""
        if st:
            dv = st[0]
            tl = sorted(dv["teams"], key=lambda t: (-t[5], t[1]))
            divtab = (f"<h2>{esc(dv['name'])}-divisioona</h2><table class='t'><tr><th>Joukkue</th><th>O</th><th>V</th><th>H</th><th>JA</th><th>P</th></tr>"
                      + "".join(f"<tr{' class=me' if t[0] == a else ''}><td>{i + 1}. <a href='/joukkueet/{tslug(t[0])}/'>{esc(tname(t[0]))}</a></td><td>{t[1]}</td><td>{t[2]}</td><td>{t[3]}</td><td>{t[4]}</td><td><b>{t[5]}</b></td></tr>" for i, t in enumerate(tl))
                      + f"</table><p class='small'><a href='/sarjataulukko/'>Koko NHL:n sarjataulukko {ic('chev')}</a></p>")
        nxt = up[0] if up else None
        nxt_txt = ""
        if nxt:
            opp = nxt["away"] if nxt["home"] == a else nxt["home"]
            nxt_txt = f" Seuraava ottelu: {tname(opp)} {'kotona' if nxt['home'] == a else 'vieraissa'}" + (f" {hel_when(nxt['start'])} Suomen aikaa." if nxt.get("start") else ".")
        fin_txt = (f"Joukkueen suomalaiset: {', '.join(fins)}." if fins else "Joukkueessa ei tällä hetkellä pelaa suomalaisia.")
        rec_txt = ""
        if st:
            t = st[2]
            rec_txt = f"{nm} on {st[0]['name']}-divisioonassa sijalla {st[1]} ({t[5]} pistettä {t[1]} ottelusta, {t[2]}–{t[3]}–{t[4]})."
            if a in ODDS:
                rec_txt += f" Todennäköisyys pudotuspelipaikkaan on Punalampun laskelmassa {pct_txt(ODDS[a]['p'])}."
        hero = (f"<header class='phero' style='--tc:{COLORS.get(a, '#2a3646')}'>{tbadge(a, 'badge lg')}<div><h1>{esc(nm)}</h1>"
                f"<p class='sub'>{sub}</p>" + (f"<p class='streak'>{streak}</p>" if streak else "") + "</div></header>" + tiles)
        faq = [(f"Pelaako {nm} -joukkueessa suomalaisia?", fin_txt + " Kokoonpano päivittyy automaattisesti NHL:n tiedoista."),
               (f"Milloin {nm} pelaa seuraavaksi?", (nxt_txt.strip() or "Seuraavaa ottelua ei ole vielä tiedossa.") + " Kaikki ottelut näet tämän sivun otteluohjelmasta."),
               (f"Missä {nm} -ottelut näkyvät Suomessa?", "Useimmat NHL-ottelut näkyvät Suomessa Viaplayssa. Disney+ näyttää osan otteluista, ja MTV Sub, Star Channel ja Viaplay TV näyttävät valikoituja otteluita ilmaiseksi.")]
        body = (hero
                + f"<p class='lead'>{esc(rec_txt)} {esc(fin_txt)}{esc(nxt_txt)}</p>"
                + (f"<h2>{FLAG}Suomalaiset</h2><table class='t'><tr><th>Pelaaja</th><th>Pelipaikka</th><th>O</th><th>M</th><th>S</th><th>P</th></tr>{''.join(finrows)}</table>" if finrows else "")
                + (f"<h2>Viimeisimmät tulokset</h2><ul class='rows'>{''.join(res_row(g) for g in past)}</ul>" if past else "")
                + (f"<h2>Tulevat ottelut</h2><ul class='rows'>{''.join(up_row(g) for g in up)}</ul><p class='mute small'>Kellonajat Suomen aikaa.</p>" + cal_box(tslug(a) + ".ics", f"{nm}: koko kauden ottelut kalenteriin") if up else "")
                + (f"<h2>Joukkueen pistepörssi {sl}</h2><table class='t'><tr><th>Pelaaja</th><th>Pp</th><th>O</th><th>M</th><th>S</th><th>P</th><th>+/-</th></tr>{skrows}</table>" if skrows else "")
                + (f"<h2>Maalivahdit</h2><table class='t'><tr><th>Maalivahti</th><th>O</th><th>V–H–JA</th><th>TO%</th><th>PMK</th><th>NP</th></tr>{gkrows}</table>" if gkrows else "")
                + divtab
                + "<h2>Usein kysyttyä</h2>" + "".join(f"<h3>{esc(q)}</h3><p>{esc(x)}</p>" for q, x in faq)
                + "<h2>Muut NHL-joukkueet</h2><div class='tgrid'>" + "".join(tlink(x) for x in sorted(TEAMS, key=lambda x: tname(x)) if x != a) + "</div>")
        jl = {"@context": "https://schema.org", "@graph": [
            {"@type": "SportsTeam", "name": nm, "sport": "Jääkiekko", "memberOf": {"@type": "SportsOrganization", "name": "National Hockey League"},
             "athlete": [{"@type": "Person", "name": n} for n in fins]},
            crumbs([("Punalamppu", "/"), ("Joukkueet", "/joukkueet/"), (nm, f"/joukkueet/{tslug(a)}/")]),
            {"@type": "FAQPage", "mainEntity": [{"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": x}} for q, x in faq]}]}
        desc = f"{nm}: tulokset, otteluohjelma Suomen aikaa, sarjatilanne ja pistepörssi {sl}. {fin_txt}"[:300]
        write_page(f"/joukkueet/{tslug(a)}/", f"{nm} – tulokset, otteluohjelma ja suomalaiset | {CFG['siteName']}", desc, body, jl, urls=urls)
    idx = "".join(f"<h2>{esc(n)}{(' · ' + esc(c)) if c else ''}</h2><div class='tgrid'>{''.join(tlink(a) for a in tl)}</div>" for n, c, tl in grid_divs)
    write_page("/joukkueet/", f"NHL-joukkueet – kaikki 32 joukkuetta | {CFG['siteName']}",
               "Kaikki 32 NHL-joukkuetta: tulokset, otteluohjelma Suomen aikaa, suomalaiset pelaajat ja joukkueiden pistepörssit.",
               "<h1>NHL-joukkueet</h1><p class='lead'>Valitse joukkue: tulokset, otteluohjelma Suomen aikaa, suomalaiset ja joukkueen pistepörssi. Joukkueet divisioonittain sarjatilanteen mukaisessa järjestyksessä.</p>" + idx,
               {"@context": "https://schema.org", "@graph": [crumbs([("Punalamppu", "/"), ("Joukkueet", "/joukkueet/")])]}, urls=urls)


# ---------------------------------------------------------------- kaikkien aikojen suomalaiset ja virstanpylväät
def fetch_alltime(now):
    path = os.path.join(DATA, "alltime.json")
    cache = load_json(path, {})
    try:
        age = (now - dt.datetime.fromisoformat(cache.get("_fetched"))).total_seconds() / 3600
    except Exception:
        age = 1e9
    if age < 20 and cache.get("points"):
        return cache
    q = urllib.parse.quote('gameTypeId=2 and nationalityCode="FIN"')
    def rows(kind, prop, limit):
        s = urllib.parse.quote(json.dumps([{"property": prop, "direction": "DESC"}]))
        d = get(f"{STATS}/{kind}/summary?isAggregate=true&isGame=false&sort={s}&start=0&limit={limit}&cayenneExp={q}")
        return (d or {}).get("data") or []
    out = {"_fetched": now.isoformat(timespec="minutes")}
    for key, kind, prop, lim in (("points", "skater", "points", 50), ("goals", "skater", "goals", 25), ("games", "skater", "gamesPlayed", 25), ("wins", "goalie", "wins", 15)):
        r = rows(kind, prop, lim)
        if kind == "skater":
            out[key] = [[fixname(x.get("skaterFullName")), x.get("playerId"), x.get("gamesPlayed", 0), x.get("goals", 0), x.get("assists", 0), x.get("points", 0), x.get("positionCode")] for x in r]
        else:
            out[key] = [[fixname(x.get("goalieFullName")), x.get("playerId"), x.get("gamesPlayed", 0), x.get("wins", 0), x.get("shutouts", 0), x.get("savePct"), x.get("goalsAgainstAverage")] for x in r]
    if not out.get("points"):
        return cache
    save_json(path, out, pretty=False)
    log("kaikkien aikojen suomalaiset haettu")
    return out


ALLTIME = {}
MILES = {"upcoming": [], "reached": [], "ranks": []}
MILE_HTML = {}


def _steps(stat, v):
    if stat == "goals":
        return 50 if v < 300 else 100
    if stat == "shutouts":
        return 10
    if stat == "wins":
        return 50
    return 100


STAT_FI = {"gamesPlayed": ("ottelua", "ottelun", 10), "points": ("pistettä", "pisteen", 6), "goals": ("maalia", "maalin", 4),
           "assists": ("syöttöä", "syötön", 5), "wins": ("voittoa", "voiton", 4), "shutouts": ("nollapeliä", "nollapelin", 1)}


def compute_milestones(data, hel_today):
    path = os.path.join(DATA, "milestones.json")
    st = load_json(path, {"last": {}, "reached": [], "ranks": {}})
    last = st.get("last") or {}
    reached = st.get("reached") or []
    up = []
    off = set(data.get("finnOff") or [])
    people = [(f[0], f[1], False) for f in data["finns"]] + [(f[0], f[1], True) for f in data["finnGoalies"]]
    for name, t, gk in people:
        pr = PROFILES.get(FINN_PID.get(name)) or {}
        ct = ((pr.get("careerTotals") or {}).get("regularSeason")) or {}
        if not ct:
            continue
        stats = ("gamesPlayed", "wins", "shutouts") if gk else ("gamesPlayed", "points", "goals", "assists")
        for s in stats:
            v = ct.get(s) or 0
            step = _steps(s, v)
            key = f"{name}|{s}"
            prev = last.get(key)
            if prev is not None and prev < v <= prev + 8:  # isompi hyppy = tietovirhe tai seurasiirto, ei virstanpylväs
                for m in range(prev // step * step + step, v // step * step + step, step):
                    if prev < m <= v:
                        reached.append({"date": hel_today.isoformat(), "name": name, "team": t, "stat": s, "value": m})
            last[key] = v
            nxt = (v // step + 1) * step
            need = nxt - v
            if need <= STAT_FI[s][2] and t and name not in off and nxt >= 100 or (s == "shutouts" and need <= 1 and t):
                up.append({"name": name, "team": t, "stat": s, "value": nxt, "need": need, "now": v})
    # kaikkien aikojen sijoitukset (pisteet)
    ranks = st.get("ranks") or {}
    rank_moves = []
    for i, r in enumerate(ALLTIME.get("points") or []):
        nm, rk = r[0], i + 1
        if nm in {p[0] for p in people}:
            old = ranks.get(nm)
            if old and rk < old:
                passed = [x[0] for x in (ALLTIME.get("points") or [])[rk:old]]
                rank_moves.append({"date": hel_today.isoformat(), "name": nm, "rank": rk, "from": old, "passed": passed})
            ranks[nm] = rk
    reached = [x for x in reached if x["date"] >= (hel_today - dt.timedelta(days=60)).isoformat()]
    moves = [x for x in (st.get("moves") or []) if x["date"] >= (hel_today - dt.timedelta(days=60)).isoformat()] + rank_moves
    st = {"last": last, "reached": reached, "ranks": ranks, "moves": moves}
    save_json(path, st, pretty=False)
    up.sort(key=lambda x: (x["need"] / STAT_FI[x["stat"]][2], -x["value"]))
    MILES.update({"upcoming": up, "reached": sorted(reached, key=lambda x: x["date"], reverse=True), "moves": sorted(moves, key=lambda x: x["date"], reverse=True)})


DONE_FI = {"gamesPlayed": "pelasi {v}. NHL-runkosarjaottelunsa", "points": "ylsi {v} NHL-runkosarjapisteeseen",
           "goals": "ylsi {v} NHL-runkosarjamaaliin", "assists": "ylsi {v} syöttöpisteeseen NHL:n runkosarjassa",
           "wins": "ylsi {v} NHL-voittoon", "shutouts": "ylsi {v} nollapeliin NHL:ssä"}


NUM_NOM = {1: "yksi", 2: "kaksi", 3: "kolme", 4: "neljä", 5: "viisi", 6: "kuusi", 7: "seitsemän", 8: "kahdeksan", 9: "yhdeksän", 10: "kymmenen"}
NUM_GEN = {1: "yhden", 2: "kahden", 3: "kolmen", 4: "neljän", 5: "viiden", 6: "kuuden", 7: "seitsemän", 8: "kahdeksan", 9: "yhdeksän", 10: "kymmenen"}


NUM_INE = {1: "yhdessä", 2: "kahdessa", 3: "kolmessa", 4: "neljässä", 5: "viidessä", 6: "kuudessa", 7: "seitsemässä", 8: "kahdeksassa", 9: "yhdeksässä", 10: "kymmenessä"}


def nwi(n):
    return NUM_INE.get(n, str(n))


def nw(n):
    return NUM_NOM.get(n, str(n))


def nwg(n):
    return NUM_GEN.get(n, str(n))


def mile_txt(m, done=False):
    w = STAT_FI[m["stat"]]
    if done:
        return f"{m['name']} " + DONE_FI[m["stat"]].format(v=m["value"])
    if m["stat"] == "gamesPlayed":
        return (f"{m['name']} pelaa {m['value']}. NHL-ottelunsa {nwg(m['need'])} ottelun päästä" if m["need"] > 1
                else f"{m['name']} pelaa seuraavaksi {m['value']}. NHL-ottelunsa")
    amount = f"yhden {w[1]}" if m["need"] == 1 else f"{nw(m['need'])} {w[0]}"
    return f"{m['name']} tarvitsee {amount} {m['value']} {w[1]} rajaan"


def mile_short(m):
    w = STAT_FI[m["stat"]]
    if m["stat"] == "gamesPlayed":
        return f"{m['value']}. NHL-ottelu {nwg(m['need'])} ottelun päästä" if m["need"] > 1 else f"{m['value']}. NHL-ottelu seuraavaksi"
    return f"{m['value']} {w[0]}: puuttuu {nw(m['need'])}"


# joukkueen nimi lyhyessä tekstissä (paikkakunta; New Yorkin joukkueet lempinimellä)
PLACE = {"NYR": "Rangers", "NYI": "Islanders", "LAK": "Los Angeles", "TBL": "Tampa Bay", "NJD": "New Jersey", "SJS": "San Jose", "STL": "St. Louis",
         "VGK": "Vegas", "UTA": "Utah", "MTL": "Montreal", "CBJ": "Columbus"}


def place(a):
    if a in PLACE:
        return PLACE[a]
    full, nick = TEAMS.get(a, (a, a))
    return full[: -len(nick)].strip() if full.endswith(nick) and full != nick else full


def team_result(g, t):
    home = g["home"] == t
    my, th = (g["homeScore"], g["awayScore"]) if home else (g["awayScore"], g["homeScore"])
    ext = g.get("final") or ""
    win = my > th
    how = {"JA": " jatkoajalla", "VL": " voittolaukauskilpailussa"}.get(ext, "")
    return win, f"{'voitti' if win else 'hävisi'}{how} {my}–{th}"


def gwg_scorer(g):
    if g.get("final") == "VL":
        return None
    aw = g["awayScore"] > g["homeScore"]
    wt = g["away"] if aw else g["home"]
    lose = min(g["awayScore"], g["homeScore"])
    wg = [x for x in g.get("goals") or [] if x["team"] == wt]
    return wg[lose]["who"] if len(wg) > lose else None


def _act(gg, aa):
    pp = gg + aa
    if gg >= 3:
        s = "teki hattutempun"
    elif gg == 2:
        s = "teki kaksi maalia"
    elif gg == 1:
        s = "teki maalin"
    else:
        return "antoi syötön" if aa == 1 else f"antoi {nw(aa)} syöttöä"
    if pp >= 4 or (pp == 3 and gg < 3):
        return f"keräsi {nw(pp)} pistettä ({gg}+{aa})"
    return s + (" ja syötön" if aa == 1 else f" ja {nw(aa)} syöttöä" if aa > 1 else "")


def build_recap(d, gl, data, latest):
    """Palauttaa (html, lyhyt teksti, rivit) – lyhyin lausein, yksi rivi pelaajaa kohden."""
    slugs = data["finnSlugs"]
    if not gl:
        return "", "", []
    def nm(n):
        return f"<a href='/suomalaiset/{slugs[n]}.html'><b>{esc(n)}</b></a>" if n in slugs else f"<b>{esc(n)}</b>"
    rows = [(g, f) for g in gl for f in g.get("finStats") or []]
    sk = sorted([(g, f) for g, f in rows if f.get("pos") != "MV"], key=lambda x: (-(x[1].get("p") or 0), -(x[1].get("g") or 0), x[1]["name"]))
    gk = [(g, f) for g, f in rows if f.get("pos") == "MV"]
    items, plain, short = [], [], []
    seen = set()
    for g, f in sk:
        gg, aa = f.get("g") or 0, f.get("a") or 0
        if not gg + aa:
            continue
        t = f["team"]
        win, res = team_result(g, t)
        dec = gg and gwg_scorer(g) == f["name"]
        same = (g["id"], t) in seen
        sent = [f"{_act(gg, aa).capitalize()}{' samassa ottelussa' if same and not dec else ''}."]
        if dec:
            sent.append("Maali ratkaisi ottelun jatkoajalla." if g.get("final") == "JA" else "Maali jäi voittomaaliksi.")
        if (g["id"], t) not in seen:
            sent.append(f"{place(t)} {res}.")
        seen.add((g["id"], t))
        txt = " ".join(sent)
        items.append(f"<li>{tbadge(t, 'mini')}<span>{nm(f['name'])} {esc(txt[0].lower() + txt[1:])}</span></li>")
        plain.append(f"{f['name']} {txt[0].lower() + txt[1:]}")
        short.append(f"{short_name(f['name'])} {gg}+{aa}")
    for g, f in gk:
        sv, sa = f.get("saves"), f.get("shots")
        if sv is None or not sa:
            continue
        t = f["team"]
        win, res = team_result(g, t)
        if sa == sv and win:
            txt = f"pelasi nollapelin ({sv} torjuntaa). {place(t)} {res}."
            short.append(f"{short_name(f['name'])} nollapeli")
        else:
            txt = f"torjui {sv}/{sa} ({f'{sv / sa:.3f}'.lstrip('0')}). {place(t)} {res}."
            short.append(f"{short_name(f['name'])} {sv}/{sa}")
        items.append(f"<li>{tbadge(t, 'mini')}<span>{nm(f['name'])} {esc(txt)}</span></li>")
        plain.append(f"{f['name']} {txt}")
    zero = [f["name"] for g, f in sk if not f.get("p")]
    html_ = f"<p class='rintro'>Yöllä pelattiin {esc(nw(len(gl)) if len(gl) <= 10 else len(gl))} ottelua. Suomalaisia pelasi {esc(nw(len(rows)) if len(rows) <= 10 else len(rows))}.</p>"
    if items:
        html_ += f"<ul class='rlist'>{''.join(items)}</ul>"
    if zero:
        html_ += "<p class='rzero'><span>Ilman pisteitä:</span> " + ", ".join(esc(short_name(n)) for n in zero) + ".</p>"
    if latest:
        extra = []
        nxt_d = (dt.date.fromisoformat(d) + dt.timedelta(days=1)).isoformat()
        for m in MILES.get("reached") or []:
            if m["date"] in (d, nxt_d):
                extra.append(("🎉", mile_txt(m, True) + "."))
        for m in MILES.get("moves") or []:
            if m["date"] in (d, nxt_d):
                extra.append(("📈", f"{m['name']} nousi suomalaisten kaikkien aikojen pistepörssissä sijalle {m['rank']}."))
        for m in (MILES.get("upcoming") or [])[:2]:
            extra.append(("⏳", mile_txt(m) + "."))
        top = data["finns"][:3]
        if top:
            extra.append(("🏆", "Suomalaisten pistepörssi: " + ", ".join(f"{short_name(p[0])} {p[6]}" for p in top) + "."))
        if extra:
            html_ += "<ul class='rnotes'>" + "".join(f"<li><span>{e}</span>{esc(t)}</li>" for e, t in extra) + "</ul>"
        for e, t in extra:
            if e == "🎉":
                short.append("🎉 " + t.rstrip("."))
    x = dt.date.fromisoformat(d)
    txt = f"Suomalaiset yön NHL-kierroksella {x.day}.{x.month}. 🇫🇮\n" + (", ".join(short) if short else "Ei suomalaisten tehopisteitä.")
    return html_, txt, plain

# ---------------------------------------------------------------- uutismuotoinen kooste
GEN = {"ANA": "Anaheimin", "BOS": "Bostonin", "BUF": "Buffalon", "CAR": "Carolinan", "CBJ": "Columbuksen", "CGY": "Calgaryn", "CHI": "Chicagon",
       "COL": "Coloradon", "DAL": "Dallasin", "DET": "Detroitin", "EDM": "Edmontonin", "FLA": "Floridan", "LAK": "Los Angelesin", "MIN": "Minnesotan",
       "MTL": "Montrealin", "NJD": "New Jerseyn", "NSH": "Nashvillen", "NYI": "Islandersin", "NYR": "Rangersin", "OTT": "Ottawan", "PHI": "Philadelphian",
       "PIT": "Pittsburghin", "SEA": "Seattlen", "SJS": "San Josen", "STL": "St. Louisin", "TBL": "Tampa Bayn", "TOR": "Toronton", "UTA": "Utahin",
       "VAN": "Vancouverin", "VGK": "Vegasin", "WPG": "Winnipegin", "WSH": "Washingtonin"}
TAG_FI = {"YV": "ylivoimalla", "AV": "alivoimalla", "TM": "tyhjään maaliin"}


def last_name(n):
    return n.split()[-1] if n else n


def per_fi(p):
    return "jatkoajalla" if p == "JA" else f"{p}. erässä"


def toi_fi(t):
    return (t or "").replace(":", ".").lstrip("0") or "–"


def headline_for(gl, data):
    rows = [(g, f) for g in gl for f in g.get("finStats") or []]
    sk = sorted([(g, f) for g, f in rows if f.get("pos") != "MV" and (f.get("p") or 0) > 0],
                key=lambda x: (-(x[1].get("p") or 0), -(x[1].get("g") or 0)))
    gk = [(g, f) for g, f in rows if f.get("pos") == "MV" and f.get("shots")]
    shut = [(g, f) for g, f in gk if f.get("saves") == f.get("shots") and f.get("dec") == "W"]
    if shut:
        g, f = shut[0]
        return f"{f['name']} pelasi nollapelin {GEN.get(f['team'], place(f['team']))} voitossa"
    if sk:
        g, f = sk[0]
        gg, aa, pp = f.get("g") or 0, f.get("a") or 0, f.get("p") or 0
        win, _ = team_result(g, f["team"])
        tgen = GEN.get(f["team"], place(f["team"]))
        if gg and gwg_scorer(g) == f["name"] and g.get("final") == "JA":
            return f"{f['name']} ratkaisi {tgen} voiton jatkoajalla"
        if pp >= 2 or gg >= 1:
            return f"{f['name']} {_act(gg, aa)} {tgen} {'voitossa' if win else 'tappiossa'}"
    big = sorted(gk, key=lambda x: -(x[1].get("saves") or 0))
    if big and (big[0][1].get("saves") or 0) >= 30:
        g, f = big[0]
        win, _ = team_result(g, f["team"])
        return f"{f['name']} torjui {f['saves']} kertaa {GEN.get(f['team'], place(f['team']))} {'voitossa' if win else 'tappiossa'}"
    return ""


def build_article(d, gl, data, latest):
    """Uutismuotoinen kooste: otsikko, ingressi, väliotsikot. Vain tilastoista tarkistettavia tosiasioita."""
    slugs = data["finnSlugs"]
    def nm(n):
        return f"<a href='/suomalaiset/{slugs[n]}.html'>{esc(n)}</a>" if n in slugs else esc(n)
    rows = [(g, f) for g in gl for f in g.get("finStats") or []]
    if not rows:
        return "", "", ""
    sk_all = [(g, f) for g, f in rows if f.get("pos") != "MV"]
    sk = sorted([x for x in sk_all if (x[1].get("p") or 0) > 0], key=lambda x: (-(x[1].get("p") or 0), -(x[1].get("g") or 0), x[1]["name"]))
    gk = [(g, f) for g, f in rows if f.get("pos") == "MV" and f.get("shots")]
    season = {f[0]: f for f in data["finns"]} if latest else {}
    gseason = {f[0]: f for f in data["finnGoalies"]} if latest else {}
    tot_g = sum(f.get("g") or 0 for g, f in sk_all)
    tot_p = sum(f.get("p") or 0 for g, f in sk_all)
    head = headline_for(gl, data) or "Suomalaiset yön NHL-kierroksella"
    # ingressi
    lead = f"Suomalaisia pelasi NHL-yönä {nw(len(rows)) if len(rows) <= 10 else len(rows)} {'ottelussa' if False else ''}".strip()
    lead = (f"NHL-yönä pelattiin {nw(len(gl)) if len(gl) <= 10 else len(gl)} ottelua, ja niissä pelasi {nw(len(rows)) if len(rows) <= 10 else len(rows)} suomalaista. "
            + (f"Suomalaiset tekivät yhteensä {nw(tot_g) if tot_g <= 10 else tot_g} maalia ja {nw(tot_p) if tot_p <= 10 else tot_p} tehopistettä." if tot_p
               else "Suomalaiset jäivät yöllä ilman tehopisteitä."))
    if sk:
        g, f = sk[0]
        win, res = team_result(g, f["team"])
        lead += f" Eniten pisteitä keräsi {f['name']}: {f.get('g') or 0}+{f.get('a') or 0}."
    parts = [f"<p class='ingressi'>{esc(lead)}</p>"]

    def goal_details(g, f):
        mine = [x for x in g.get("goals") or [] if x.get("who") == f["name"]]
        bits = []
        for x in mine:
            b = f"{per_fi(x['p'])} ajassa {toi_fi(x['t'])}"
            if x.get("tag") in TAG_FI:
                b += f" {TAG_FI[x['tag']]}"
            bits.append(b)
        if not bits:
            return ""
        return ("Maali syntyi " + bits[0] + "." if len(bits) == 1 else "Maalit syntyivät " + ", ".join(bits[:-1]) + " ja " + bits[-1] + ".")

    def assist_details(g, f):
        sc = [x["who"] for x in g.get("goals") or [] if f["name"] in (x.get("ast") or [])]
        if not sc:
            return ""
        return (f"Syöttöpiste tuli maaliin, jonka teki {sc[0]}." if len(sc) == 1
                else f"Syöttöpisteet tulivat maaleihin, jotka tekivät {', '.join(sc[:-1])} ja {sc[-1]}.")

    def player_para(g, f):
        gg, aa = f.get("g") or 0, f.get("a") or 0
        t = f["team"]
        win, res = team_result(g, t)
        opp = g["home"] if g["away"] == t else g["away"]
        s = [f"<b>{nm(f['name'])}</b> {esc(_act(gg, aa))}, kun {esc(tname(t))} kohtasi {esc(tname(opp))} -joukkueen."]
        gd_ = goal_details(g, f)
        if gd_:
            s.append(esc(gd_))
        if gg and gwg_scorer(g) == f["name"]:
            s.append("Maali ratkaisi ottelun jatkoajalla." if g.get("final") == "JA" else "Maali jäi ottelun voittomaaliksi.")
        if aa:
            ad = assist_details(g, f)
            if ad:
                s.append(esc(ad))
        s.append(esc(f"{place(t)} {res}."))
        extra = []
        if f.get("toi"):
            extra.append(f"peliaika {toi_fi(f['toi'])}")
        if f.get("sog") is not None:
            extra.append(f"laukaukset {f['sog']}")
        if isinstance(f.get("pm"), int):
            extra.append(f"+/− {f['pm']:+d}")
        if f["name"] in season:
            x = season[f["name"]]
            extra.append(f"kausi {x[4]}+{x[5]}={x[6]} ({x[3]} ott.)")
        return "<div class='pblock'><p>" + " ".join(s) + "</p>" + (f"<p class='pstat'>{esc(' · '.join(extra))}</p>" if extra else "") + "</div>"

    if sk:
        parts.append("<h2>Pistemiehet</h2>")
        parts += [player_para(g, f) for g, f in sk]
    if gk:
        parts.append("<h2>Maalivahdit</h2>")
        for g, f in gk:
            t = f["team"]
            win, res = team_result(g, t)
            opp = g["home"] if g["away"] == t else g["away"]
            sv, sa = f.get("saves") or 0, f.get("shots") or 0
            s = [f"<b>{nm(f['name'])}</b> torjui {sv} laukausta {sa}:stä ({esc(f'{sv / sa:.3f}'.lstrip('0'))}), kun {esc(tname(t))} kohtasi {esc(tname(opp))} -joukkueen."]
            if sa == sv and win:
                s.append("Hän pelasi nollapelin.")
            s.append(esc(f"{place(t)} {res}."))
            st_line = ""
            if f["name"] in gseason:
                x = gseason[f["name"]]
                st_line = f"kausi {x[2]} ott. · {x[3]}–{x[4]}–{x[5]} · TO% {x[6]} · PMK {x[7]}"
            parts.append("<div class='pblock'><p>" + " ".join(s) + "</p>" + (f"<p class='pstat'>{esc(st_line)}</p>" if st_line else "") + "</div>")
    zero = [f for g, f in sk_all if not f.get("p")]
    if zero:
        parts.append("<h2>Ilman pisteitä</h2><p>" + ", ".join(
            f"{nm(f['name'])} ({esc(tname(f['team']))}" + (f", {esc(toi_fi(f.get('toi')))}" if f.get("toi") else "") + ")" for f in zero) + ".</p>"
            "<p class='mute small'>Suluissa joukkue ja peliaika.</p>")
    if latest:
        mil = []
        nxt_d = (dt.date.fromisoformat(d) + dt.timedelta(days=1)).isoformat()
        mil += [esc(mile_txt(m, True)) + "." for m in MILES.get("reached") or [] if m["date"] in (d, nxt_d)]
        mil += [esc(f"{m['name']} nousi suomalaisten kaikkien aikojen NHL-pistepörssissä sijalle {m['rank']}.") for m in MILES.get("moves") or [] if m["date"] in (d, nxt_d)]
        up = [esc(mile_txt(m)) + "." for m in (MILES.get("upcoming") or [])[:4]]
        if mil or up:
            parts.append("<h2>Virstanpylväät</h2>" + "".join(f"<p>{x}</p>" for x in mil)
                         + (("<p><b>Lähellä:</b></p><ul>" + "".join(f"<li>{x}</li>" for x in up) + "</ul>") if up else "")
                         + "<p class='small'><a href='/virstanpylvaat/'>Kaikki virstanpylväät</a></p>")
        top = data["finns"][:5]
        if top:
            parts.append("<h2>Suomalaisten pistepörssi</h2><table class='t'><tr><th>Pelaaja</th><th>O</th><th>M</th><th>S</th><th>P</th></tr>"
                         + "".join(f"<tr><td>{i + 1}. {tbadge(p[1], 'mini')} {nm(p[0])}</td><td>{p[3]}</td><td>{p[4]}</td><td>{p[5]}</td><td><b>{p[6]}</b></td></tr>" for i, p in enumerate(top))
                         + "</table><p class='small'><a href='/suomalaiset/'>Kaikki suomalaiset</a></p>")
        # seuraava kierros
        later = sorted([u for u in data["upcoming"] if u["day"] > d and u.get("start")], key=lambda u: u["start"])
        if later:
            nd = later[0]["day"]
            nxt = [u for u in later if u["day"] == nd and finn_by_team(data, u["away"], u["home"])]
            if nxt:
                parts.append("<h2>Seuraavaksi</h2><p>Suomalaisia nähdään seuraavalla NHL-kierroksella näissä otteluissa (Suomen aikaa):</p><ul>"
                             + "".join(f"<li><b>klo {esc(fi_time(u['start']).lstrip('0'))}</b> {esc(tname(u['away']))} – {esc(tname(u['home']))}: "
                                       f"{esc(', '.join(finn_by_team(data, u['away'], u['home'])))}</li>" for u in nxt)
                             + "</ul><p class='small'><a href='/otteluohjelma/'>Koko otteluohjelma</a> · <a href='/nhl-tv/'>Missä ottelut näkyvät</a></p>")
    parts.append("<h2>Lähteet ja tekotapa</h2><p class='small'>Kooste perustuu NHL:n virallisiin ottelutilastoihin (NHL.com). "
                 "Kooste on tuotettu automaattisesti tekoälyn avulla laaditulla ohjelmalla, joka kirjoittaa tekstin suoraan tilastoista. "
                 "Ylläpitäjä tarkastaa koosteiden tekstipohjat, säännöt ja sanavalinnat aina, kun niitä muutetaan. "
                 "Yksittäiset aamun koosteet julkaistaan automaattisesti ilman erillistä tarkastusta. Tekstissä ei ole arvioita eikä lainauksia. "
                 "<a href='/tietoa.html#tekoaly'>Näin Punalamppu käyttää tekoälyä</a>. "
                 "Tiedot päivittyvät, jos NHL korjaa tilastojaan. Huomasitko virheen? <a href='/yhteys.html'>Ilmoita siitä meille</a>, niin korjaamme sen.</p>")
    return head, lead, "".join(parts)


# ---------------------------------------------------------------- kalenterit (.ics)
def ics_escape(s):
    return str(s).replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def ics_write(path, name, events):
    now = now_utc().strftime("%Y%m%dT%H%M%SZ")
    base = CFG["baseUrl"].rstrip("/")
    out = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Punalamppu//NHL//FI", "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
           f"X-WR-CALNAME:{ics_escape(name)}", "X-WR-TIMEZONE:Europe/Helsinki", "REFRESH-INTERVAL;VALUE=DURATION:PT12H", "X-PUBLISHED-TTL:PT12H"]
    for e in events:
        st = dt.datetime.fromisoformat(e["start"].replace("Z", "+00:00")).astimezone(dt.timezone.utc)
        out += ["BEGIN:VEVENT", f"UID:{e['uid']}@punalamppu.com", f"DTSTAMP:{now}", f"DTSTART:{st:%Y%m%dT%H%M%SZ}", "DURATION:PT2H45M",
                f"SUMMARY:{ics_escape(e['title'])}", f"DESCRIPTION:{ics_escape(e.get('desc', ''))}", f"URL:{base}{e.get('url', '/')}", "END:VEVENT"]
    out.append("END:VCALENDAR")
    lines = []
    for ln in out:  # rivitys 75 tavuun
        b = ln.encode("utf-8")
        while len(b) > 74:
            cut = 74
            while (b[cut] & 0xC0) == 0x80:
                cut -= 1
            lines.append(b[:cut].decode("utf-8"))
            b = b" " + b[cut:]
        lines.append(b.decode("utf-8"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "w", encoding="utf-8", newline="").write("\r\n".join(lines) + "\r\n")


def build_calendars(data, urls):
    tdata = TEAMDATA.get("teams") or {}
    free = {(e["date"], frozenset((e["away"], e["home"]))): e["ch"] for e in data.get("freeTv") or []}
    allg = {}
    for a in TEAMS:
        games = [g for g in (tdata.get(a) or {}).get("games") or [] if g.get("start")]
        if not games:
            games = [{"id": f"{u['day']}-{u['away']}-{u['home']}", "date": u["day"], "start": u["start"], "away": u["away"], "home": u["home"], "state": "FUT"}
                     for u in data["upcoming"] if a in (u["away"], u["home"]) and u.get("start")]
        evs = []
        for g in games:
            allg[g["id"]] = g
            fins = finn_by_team(data, g["away"], g["home"])
            pair = frozenset((g["away"], g["home"]))
            ch = free.get((g["date"], pair)) or free.get(((dt.date.fromisoformat(g["date"]) + dt.timedelta(days=1)).isoformat(), pair))
            title = f"🏒 {g['away']} – {g['home']}"
            if g.get("as") is not None and g.get("state") in ("OFF", "FINAL"):
                title += f" {g['as']}–{g['hs']}"
            evs.append({"uid": f"{g['id']}-{a}", "start": g["start"], "title": title + (f" (ilmaiseksi: {ch})" if ch else ""),
                        "desc": f"{tname(g['away'])} – {tname(g['home'])}" + (f"\nSuomalaiset: {', '.join(fins)}" if fins else "") + "\nTulokset ja maalikoosteet: punalamppu.com",
                        "url": f"/joukkueet/{tslug(a)}/"})
        ics_write(os.path.join(OUT, "kalenteri", f"{tslug(a)}.ics"), f"{tname(a)} (Punalamppu)", evs)
    # suomalaisten ottelut: kaikki tulevat ottelut, joissa pelaa suomalainen
    today = now_utc() - dt.timedelta(days=2)
    evs = []
    for g in sorted(allg.values(), key=lambda g: g["start"]):
        if dt.datetime.fromisoformat(g["start"].replace("Z", "+00:00")) < today:
            continue
        fins = finn_by_team(data, g["away"], g["home"])
        if not fins:
            continue
        pair = frozenset((g["away"], g["home"]))
        ch = free.get((g["date"], pair)) or free.get(((dt.date.fromisoformat(g["date"]) + dt.timedelta(days=1)).isoformat(), pair))
        evs.append({"uid": f"{g['id']}-fin", "start": g["start"], "title": f"🇫🇮 {g['away']} – {g['home']}: " + ", ".join(short_name(n) for n in fins) + (f" (ilmaiseksi: {ch})" if ch else ""),
                    "desc": f"{tname(g['away'])} – {tname(g['home'])}\nSuomalaiset: {', '.join(fins)}\nTulokset ja maalikoosteet: punalamppu.com", "url": "/suomalaiset/"})
    ics_write(os.path.join(OUT, "kalenteri", "suomalaiset.ics"), "Suomalaisten NHL-ottelut (Punalamppu)", evs[:400])


def cal_box(file, label):
    base = re.sub(r"^https?://", "", CFG["baseUrl"].rstrip("/"))
    return (f"<div class='calbox'>{ic('cal')}<div><b>{esc(label)}</b><span>Ottelut päivittyvät puhelimen kalenteriin automaattisesti Suomen ajassa.</span></div>"
            f"<a class='btn' href='webcal://{base}/kalenteri/{file}'>Lisää kalenteriin</a>"
            f"<a class='small' href='/kalenteri/{file}' download>.ics</a></div>")


# ---------------------------------------------------------------- pudotuspelitodennäköisyydet (oma simulaatio)
ODDS = {}


def playoff_odds(data, sims=2000):
    import random
    tdata = TEAMDATA.get("teams") or {}
    if not data["standings"] or len(tdata) < 30:
        return {}
    info = {}
    for dv in data["standings"]:
        for t in dv["teams"]:
            info[t[0]] = {"div": dv["name"], "conf": dv["conf"], "gp": t[1], "w": t[2], "pts": t[5]}
    if len(info) < 32:
        return {}
    rem = {}
    for a, td in tdata.items():
        for g in td.get("games") or []:
            if g.get("state") in NOT_STARTED and g["away"] in info and g["home"] in info:
                rem[g["id"]] = (g["away"], g["home"])
    rem = list(rem.values())
    def strength(a):
        i = info[a]
        return (i["pts"] + 28) / (2 * (i["gp"] + 28))  # tasoitus: 28 "keskiverto-ottelua" (pistetahti vaihtelee paljon)
    pr = []
    for aw, hm in rem:
        pa, ph = strength(aw), strength(hm)
        p = 0.5 + 0.75 * (ph * (1 - pa) / (ph * (1 - pa) + pa * (1 - ph)) - 0.5) + 0.035
        pr.append((aw, hm, min(0.8, max(0.2, p))))
    rnd = random.Random(data["gameDate"] + str(sum(i["pts"] for i in info.values())))
    made = {a: 0 for a in info}
    pts_sum = {a: 0 for a in info}
    teams = list(info)
    for _ in range(sims):
        pts = {a: info[a]["pts"] for a in teams}
        wins = {a: info[a]["w"] for a in teams}
        for aw, hm, p in pr:
            ot = rnd.random() < 0.23
            if rnd.random() < p:
                pts[hm] += 2; wins[hm] += 1
                if ot: pts[aw] += 1
            else:
                pts[aw] += 2; wins[aw] += 1
                if ot: pts[hm] += 1
        for c in ("Itä", "Länsi"):
            ct = [a for a in teams if info[a]["conf"] == c]
            key = lambda a: (pts[a], wins[a], rnd.random())
            qual = set()
            for dvn in {info[a]["div"] for a in ct}:
                qual |= set(sorted([a for a in ct if info[a]["div"] == dvn], key=key, reverse=True)[:3])
            rest = sorted([a for a in ct if a not in qual], key=key, reverse=True)[:2]
            for a in qual | set(rest):
                made[a] += 1
        for a in teams:
            pts_sum[a] += pts[a]
    return {a: {"p": made[a] / sims, "xp": pts_sum[a] / sims, "conf": info[a]["conf"], "div": info[a]["div"], "pts": info[a]["pts"], "gp": info[a]["gp"]} for a in teams}


def pct_txt(p):
    if p >= 0.995:
        return "yli 99 %"
    if p <= 0.005:
        return "alle 1 %"
    return f"{round(p * 100)} %"


def mile_html_for(name):
    up = [m for m in MILES.get("upcoming") or [] if m["name"] == name]
    done = [m for m in MILES.get("reached") or [] if m["name"] == name][:3]
    rank = next((i + 1 for i, r in enumerate(ALLTIME.get("points") or []) if r[0] == name), None)
    items = [f"<li>{esc(mile_short(m))}</li>" for m in up] + [f"<li>Saavutettu {esc(fi_dshort(m['date']))}: {esc(DONE_FI[m['stat']].format(v=m['value']))}</li>" for m in done]
    if rank:
        items.append(f"<li>Suomalaisten kaikkien aikojen NHL-pistepörssissä sijalla <b>{rank}</b> (<a href='/kaikkien-aikojen-suomalaiset/'>katso lista</a>)</li>")
    return ("<h3>Virstanpylväät</h3><ul>" + "".join(items) + "</ul>") if items else ""


def build_alltime_pages(data, urls):
    slugs = data["finnSlugs"]
    active = {f[0] for f in data["finns"] + data["finnGoalies"]}
    def nm(n):
        x = f"<a href='/suomalaiset/{slugs[n]}.html'>{esc(n)}</a>" if n in slugs else esc(n)
        return x + (" <span class='fi'>NYT</span>" if n in active else "")
    at = ALLTIME
    body = ""
    if not at.get("points"):
        log("kaikkien aikojen tilastoja ei saatu")
    if at.get("points"):
        body += ("<h2>Pistepörssi – top 50</h2><table class='t'><tr><th>Pelaaja</th><th>O</th><th>M</th><th>S</th><th>P</th></tr>"
                 + "".join(f"<tr{' class=me' if r[0] in active else ''}><td>{i + 1}. {nm(r[0])}</td><td>{r[2]}</td><td>{r[3]}</td><td>{r[4]}</td><td><b>{r[5]}</b></td></tr>" for i, r in enumerate(at["points"])) + "</table>")
    if at.get("goals"):
        body += ("<h2>Maalipörssi – top 25</h2><table class='t'><tr><th>Pelaaja</th><th>O</th><th>M</th></tr>"
                 + "".join(f"<tr{' class=me' if r[0] in active else ''}><td>{i + 1}. {nm(r[0])}</td><td>{r[2]}</td><td><b>{r[3]}</b></td></tr>" for i, r in enumerate(at["goals"])) + "</table>")
    if at.get("games"):
        body += ("<h2>Eniten otteluita – top 25</h2><table class='t'><tr><th>Pelaaja</th><th>O</th><th>P</th></tr>"
                 + "".join(f"<tr{' class=me' if r[0] in active else ''}><td>{i + 1}. {nm(r[0])}</td><td><b>{r[2]}</b></td><td>{r[5]}</td></tr>" for i, r in enumerate(at["games"])) + "</table>")
    if at.get("wins"):
        body += ("<h2>Maalivahdit: eniten voittoja</h2><table class='t'><tr><th>Maalivahti</th><th>O</th><th>V</th><th>NP</th><th>TO%</th></tr>"
                 + "".join(f"<tr{' class=me' if r[0] in active else ''}><td>{i + 1}. {nm(r[0])}</td><td>{r[2]}</td><td><b>{r[3]}</b></td><td>{r[4]}</td><td>{fmt_sv(r[5])}</td></tr>" for i, r in enumerate(at["wins"])) + "</table>")
    top = (at.get("points") or [])
    lead = (f"Suomalaisten kaikkien aikojen NHL-pistepörssiä johtaa {top[0][0]} {top[0][5]} pisteellä ennen pelaajaa {top[1][0]} ({top[1][5]} p). "
            if len(top) > 1 else "")
    best_act = next(((i + 1, r) for i, r in enumerate(top) if r[0] in active), None)
    if best_act:
        lead += f"Nykypelaajista korkeimmalla on {best_act[1][0]}, sijalla {best_act[0]} ({best_act[1][5]} p). "
    faq = []
    if len(top) > 1:
        faq.append(("Kuka on kaikkien aikojen paras suomalainen NHL-pistemies?", f"{top[0][0]} on tehnyt NHL:n runkosarjassa eniten pisteitä suomalaisista: {top[0][5]} pistettä {top[0][2]} ottelussa. Toisena on {top[1][0]} {top[1][5]} pisteellä."))
    if at.get("goals"):
        g0 = at["goals"][0]
        faq.append(("Kuka suomalainen on tehnyt eniten maaleja NHL:ssä?", f"{g0[0]} on tehnyt suomalaisista eniten NHL-runkosarjamaaleja: {g0[3]} maalia."))
    if at.get("wins"):
        w0 = at["wins"][0]
        faq.append(("Kuka suomalainen maalivahti on voittanut eniten NHL:ssä?", f"{w0[0]} on suomalaismaalivahdeista voittanut eniten NHL-runkosarjaotteluita: {w0[3]} voittoa."))
    body_full = (f"<h1>Kaikkien aikojen suomalaiset NHL:ssä</h1><p class='lead'>{esc(lead)}Tilastot ovat NHL:n runkosarjasta ja päivittyvät automaattisesti. "
                 "Nykyiset pelaajat on korostettu.</p>" + body
                 + ("<h2>Usein kysyttyä</h2>" + "".join(f"<h3>{esc(q)}</h3><p>{esc(a)}</p>" for q, a in faq) if faq else "")
                 + "<p class='small mute'>Lähde: NHL.com (runkosarjatilastot, kansalaisuus Suomi). <a href='/virstanpylvaat/'>Lähestyvät virstanpylväät</a></p>")
    jl = {"@context": "https://schema.org", "@graph": [crumbs([("Punalamppu", "/"), ("Kaikkien aikojen suomalaiset", "/kaikkien-aikojen-suomalaiset/")])]
          + ([{"@type": "FAQPage", "mainEntity": [{"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faq]}] if faq else [])}
    if at.get("points"):
      write_page("/kaikkien-aikojen-suomalaiset/", f"Kaikkien aikojen suomalaiset NHL:ssä – pistepörssi ja ennätykset | {CFG['siteName']}",
               (lead or "Suomalaisten kaikkien aikojen NHL-pistepörssi, maalipörssi, ottelumäärät ja maalivahtien voitot.")[:300], body_full, jl, urls=urls)
    # virstanpylväät
    up = MILES.get("upcoming") or []
    done = MILES.get("reached") or []
    moves = MILES.get("moves") or []
    def mrow(m, txt):
        return f"<li><div class='mrow'>{tbadge(m['team'], 'mini') if m.get('team') else ''}<span>{txt}</span></div></li>"
    b = ("<h1>Suomalaisten NHL-virstanpylväät</h1><p class='lead'>Ketkä suomalaiset ovat lähellä uransa merkkipaaluja? Lista päivittyy joka yö pelaajien NHL-runkosarjauran tilastoista.</p>"
         "<h2>Lähestyvät virstanpylväät</h2>" + (f"<ul class='rows'>{''.join(mrow(m, esc(mile_txt(m)) + '.') for m in up)}</ul>" if up else "<p>Kukaan ei ole juuri nyt aivan virstanpylvään tuntumassa.</p>")
         + ("<h2>Hiljattain saavutetut</h2><ul class='rows'>" + "".join(mrow(m, f"<span class='gt'>{esc(fi_dshort(m['date']))}</span> " + esc(mile_txt(m, True)) + ".") for m in done[:20]) + "</ul>" if done else "")
         + ("<h2>Nousut kaikkien aikojen pistepörssissä</h2><ul class='rows'>" + "".join(mrow(m, f"<span class='gt'>{esc(fi_dshort(m['date']))}</span> " + esc(f"{m['name']} nousi sijalle {m['rank']}" + (f" ohi pelaajan {m['passed'][-1]}" if m.get('passed') else "")) + ".") for m in moves[:20]) + "</ul>" if moves else "")
         + "<p class='small'><a href='/kaikkien-aikojen-suomalaiset/'>Kaikkien aikojen suomalaiset NHL:ssä " + ic('chev') + "</a></p>")
    write_page("/virstanpylvaat/", f"Suomalaisten NHL-virstanpylväät – lähestyvät merkkipaalut | {CFG['siteName']}",
               "Lähestyvät ja hiljattain saavutetut suomalaisten NHL-virstanpylväät: 100 ottelun, pisteen ja maalin rajat. Päivittyy automaattisesti.", b,
               {"@context": "https://schema.org", "@graph": [crumbs([("Punalamppu", "/"), ("Virstanpylväät", "/virstanpylvaat/")])]}, urls=urls)


def build_odds_page(data, urls):
    if not ODDS:
        return
    sl = season_label(data["gameDate"])
    body = (f"<h1>Kuka pääsee NHL:n pudotuspeleihin? Todennäköisyydet {sl}</h1><p class='lead'>Mikä on kunkin joukkueen todennäköisyys päästä pudotuspeleihin? "
            "Punalampun oma laskelma simuloi kauden jäljellä olevat ottelut 2 000 kertaa joukkueiden tähänastisen pistetahdin perusteella. Päivittyy joka päivä.</p>")
    for c in ("Itä", "Länsi"):
        ts = sorted([a for a in ODDS if ODDS[a]["conf"] == c], key=lambda a: (-ODDS[a]["p"], -ODDS[a]["pts"]))
        body += (f"<h2>{'Itäinen' if c == 'Itä' else 'Läntinen'} konferenssi</h2><table class='t odds'><tr><th>Joukkue</th><th>P</th><th>Ennuste</th><th>Pudotuspelit</th></tr>"
                 + "".join(f"<tr><td><a href='/joukkueet/{tslug(a)}/'>{esc(tname(a))}</a> <span class='mute small'>{esc(ODDS[a]['div'])}</span></td><td>{ODDS[a]['pts']}</td><td>{round(ODDS[a]['xp'])}</td>"
                           f"<td><div class='bar'><i style='width:{max(1, round(ODDS[a]['p'] * 100))}%'></i><b>{pct_txt(ODDS[a]['p'])}</b></div></td></tr>" for a in ts)
                 + "</table>")
    body += ("<h2>Miten laskelma tehdään?</h2><p>Jokaiselle jäljellä olevalle runkosarjaottelulle lasketaan voittotodennäköisyys joukkueiden pisteprosentista (alkukauden tulokset tasoitettuna) "
             "ja kotietu huomioiden. Noin 23 % otteluista ratkeaa jatkoajalla, jolloin häviäjä saa pisteen. Pudotuspeleihin pääsee kunkin divisioonan kolme parasta ja konferenssin kaksi parasta muuta (villit kortit). "
             "Ennuste-sarake on joukkueen keskimääräinen loppupistemäärä simulaatioissa. Kyse on tilastollisesta arviosta, ei vedonlyöntikertoimista.</p>"
             "<p class='small'><a href='/sarjataulukko/'>NHL-sarjataulukko " + ic('chev') + "</a></p>")
    write_page("/pudotuspelit/", f"NHL-pudotuspelitodennäköisyydet {sl} – kuka pääsee playoffeihin? | {CFG['siteName']}",
               f"NHL-joukkueiden todennäköisyys päästä pudotuspeleihin kaudella {sl}: oma simulaatio jäljellä olevista otteluista, päivittyy päivittäin.", body,
               {"@context": "https://schema.org", "@graph": [crumbs([("Punalamppu", "/"), ("Pudotuspelit", "/pudotuspelit/")])]}, urls=urls)


# ---------------------------------------------------------------- automaattiset uutiset
NEWS = {"articles": []}


def _art_slug(a):
    return f"/uutiset/{a['slug']}/"


def news_upsert(st, art):
    arts = st.setdefault("articles", [])
    for i, a in enumerate(arts):
        if a["id"] == art["id"]:
            if a.get("frozen"):
                return False
            arts[i] = art
            return True
    arts.append(art)
    return True


def preview_article(data, D, now, arch_days=None):
    """Päivän ennakko: illan/yön ottelut Suomen aikaa, suomalaiset, ilmaiset lähetykset."""
    start = dt.datetime(D.year, D.month, D.day, 15, 0, tzinfo=HEL)
    end = start + dt.timedelta(hours=18)
    games = []
    for u in data["upcoming"]:
        if not u.get("start"):
            continue
        t = dt.datetime.fromisoformat(u["start"].replace("Z", "+00:00")).astimezone(HEL)
        if start <= t < end:
            games.append((t, u))
    games.sort(key=lambda x: x[0])
    if not games:
        return None
    slugs = data["finnSlugs"]
    sk = {f[0]: f for f in data["finns"]}
    gkd = {f[0]: f for f in data["finnGoalies"]}
    free = {(e["date"], frozenset((e["away"], e["home"]))): e["ch"] for e in data.get("freeTv") or []}
    def nm(n):
        return f"<a href='/suomalaiset/{slugs[n]}.html'>{esc(n)}</a>" if n in slugs else esc(n)
    def stat(n):
        if n in sk:
            f = sk[n]
            return f"{f[4]}+{f[5]}={f[6]} ({f[3]} ott.)"
        if n in gkd:
            f = gkd[n]
            return f"MV, TO% {f[6]}"
        return ""
    # kuka pelasi joukkueensa edellisessä ottelussa (arkistosta)
    last_game = {}
    for d in sorted(arch_days or {}):
        for g in arch_days[d]:
            if g.get("state") not in (None, "OFF", "FINAL") and not g.get("finStats"):
                continue
            for t in (g["away"], g["home"]):
                last_game[t] = {f["name"] for f in g.get("finStats") or [] if f.get("team") == t}
    def split(team):
        names = finn_by_team(data, team)
        if team not in last_game:
            return names, []
        return [n for n in names if n in last_game[team]], [n for n in names if n not in last_game[team]]
    fin_games, others, n_fin, faceoffs, frees = [], [], 0, [], []
    for t, u in games:
        fa, fa_x = split(u["away"])
        fh, fh_x = split(u["home"])
        ch = free.get((t.date().isoformat(), frozenset((u["away"], u["home"])))) or free.get(((t.date() - dt.timedelta(days=1)).isoformat(), frozenset((u["away"], u["home"]))))
        if ch:
            frees.append((t, u, ch))
        if fa or fh or fa_x or fh_x:
            n_fin += len(fa) + len(fh)
            if fa and fh:
                faceoffs.append(u)
            fin_games.append((t, u, fa, fh, ch, fa_x + fh_x))
        else:
            others.append((t, u, ch))
    when = lambda t: f"klo {t:%H.%M}".replace("klo 0", "klo ")
    dd = f"{D.day}.{D.month}."
    def best(names):
        return sorted(names, key=lambda n: -(sk[n][6] if n in sk else 0))[0]
    fo = []
    for t, u, fa, fh, ch, extra in fin_games:
        if fa and fh:
            fo.append((100 if ch else 0) + len(fa) + len(fh), u, fa, fh, ch)
    if fo:
        fo.sort(key=lambda x: -x[0])
        _, u, fa, fh, ch = fo[0]
        title = f"NHL tänä yönä {dd}: {best(fa)} ja {best(fh)} vastakkain" + (f" – ilmaiseksi {ch}" if ch else "")
    elif frees:
        t, u, ch = frees[0]
        title = f"NHL tänä yönä {dd}: {tname(u['away'])} – {tname(u['home'])} ilmaiseksi ({ch})"
    else:
        title = f"NHL tänä yönä {dd}: suomalaiset ja ottelut" if not fin_games else f"NHL tänä yönä {dd}: suomalaisia {nwi(len(fin_games))} ottelussa"
    lead = (f"NHL:ssä pelataan tänä yönä {nw(len(games)) if len(games) <= 10 else len(games)} ottelua. "
            + (f"Suomalaisia on joukkueiden kokoonpanoissa {nwi(len(fin_games))} ottelussa. " if fin_games else "Yhdessäkään illan ottelussa ei ole suomalaisia kokoonpanoissa. ")
            + ("Ilmaiseksi näkyy yksi ottelu." if len(frees) == 1 else f"Ilmaiseksi näkyy {nw(len(frees))} ottelua." if frees else ""))
    body = [f"<p class='ingressi'>{esc(lead.strip())}</p>"]
    if fin_games:
        body.append("<h2>Suomalaisten ottelut</h2>")
        for t, u, fa, fh, ch, extra in fin_games:
            ppl = [(n, u["away"]) for n in fa] + [(n, u["home"]) for n in fh]
            body.append(f"<div class='pblock'><p><b>{esc(when(t))}</b> {esc(tname(u['away']))} – {esc(tname(u['home']))}"
                        + (f" · <a href='/nhl-tv/#ilmaisottelut'>ilmaiseksi: {esc(ch)}</a>" if ch else "") + "</p>"
                        + ("<p class='pstat'>" + " · ".join(f"{nm(n)} {esc(stat(n))}" for n, _ in ppl) + "</p>" if ppl else "")
                        + (f"<p class='pstat'>Kokoonpanossa, mutta ei pelannut joukkueen edellistä ottelua: {', '.join(nm(n) for n in extra)}</p>" if extra else "")
                        + "</div>")
        body.append("<p class='small mute'>Pelaajat ovat joukkueidensa NHL-kokoonpanoissa ja pelasivat joukkueensa edellisessä ottelussa, ellei toisin mainita. "
                    "Lopulliset kokoonpanot varmistuvat vasta juuri ennen ottelua, joten muutokset ovat mahdollisia.</p>")
    likely = {n for _, _, fa, fh, _, _ in fin_games for n in fa + fh}
    ups = [m for m in (MILES.get("upcoming") or []) if m["name"] in likely]
    if ups:
        body.append("<h2>Virstanpylväät lähellä</h2><ul>" + "".join(f"<li>{esc(mile_txt(m))}.</li>" for m in ups[:5]) + "</ul>")
    if others:
        body.append("<h2>Muut ottelut</h2><ul>" + "".join(f"<li><b>{esc(when(t))}</b> {esc(tname(u['away']))} – {esc(tname(u['home']))}"
                                                      + (f" (ilmaiseksi: {esc(ch)})" if ch else "") + "</li>" for t, u, ch in others) + "</ul>")
    body.append("<p class='small'>Kellonajat Suomen aikaa. <a href='/otteluohjelma/'>Koko otteluohjelma</a> · <a href='/nhl-tv/'>Missä NHL näkyy</a> · "
                "<a href='/kalenteri/suomalaiset.ics'>Suomalaisten ottelut kalenteriin</a></p>")
    first = games[0][0]
    return {"id": f"p-{D.isoformat()}", "type": "ennakko", "slug": f"{D.isoformat()}-nhl-tana-yona", "date": D.isoformat(),
            "published": min(now, first - dt.timedelta(minutes=1)).isoformat(timespec="minutes") if now < first else first.isoformat(timespec="minutes"),
            "title": title, "lead": lead.strip(), "html": "".join(body), "frozen": now >= first}


def milestone_article(m, data):
    slugs = data["finnSlugs"]
    w = STAT_FI[m["stat"]]
    title = mile_txt(m, True)
    pr = PROFILES.get(FINN_PID.get(m["name"])) or {}
    ct = ((pr.get("careerTotals") or {}).get("regularSeason")) or {}
    parts = []
    if ct:
        if m["stat"] in ("wins", "shutouts") or "wins" in ct and m["stat"] == "gamesPlayed" and ct.get("wins") is not None and ct.get("points") is None:
            parts.append(f"Uralla hänellä on nyt {ct.get('gamesPlayed', 0)} NHL-runkosarjaottelua, {ct.get('wins', 0)} voittoa ja {ct.get('shutouts', 0)} nollapeliä.")
        else:
            parts.append(f"Uralla hänellä on nyt {ct.get('gamesPlayed', 0)} NHL-runkosarjaottelussa {ct.get('goals', 0)} maalia ja {ct.get('assists', 0)} syöttöä, yhteensä {ct.get('points', 0)} pistettä.")
    rank = next((i + 1 for i, r in enumerate(ALLTIME.get("points") or []) if r[0] == m["name"]), None)
    if rank:
        parts.append(f"Suomalaisten kaikkien aikojen NHL-pistepörssissä hän on sijalla {rank}.")
    team = tname(m["team"]) if m.get("team") else ""
    lead = f"{title}." + (f" Hän edustaa {team} -joukkuetta." if team else "")
    link = f"<a href='/suomalaiset/{slugs[m['name']]}.html'>{esc(m['name'])}</a>" if m["name"] in slugs else esc(m["name"])
    body = (f"<p class='ingressi'>{esc(lead)}</p><p>{link} saavutti merkkipaalun {esc(fi_date(m['date']))} päivitetyissä tilastoissa. {esc(' '.join(parts))}</p>"
            "<p class='small'><a href='/virstanpylvaat/'>Lähestyvät virstanpylväät</a> · <a href='/kaikkien-aikojen-suomalaiset/'>Kaikkien aikojen suomalaiset</a></p>")
    slug = f"{m['date']}-{slugify(m['name'])}-{m['value']}-{slugify(w[0])}"
    return {"id": f"m-{m['name']}-{m['stat']}-{m['value']}", "type": "virstanpylväs", "slug": slug, "date": m["date"],
            "published": dt.datetime.fromisoformat(m["date"]).replace(hour=9, tzinfo=HEL).isoformat(timespec="minutes"),
            "title": title, "lead": lead, "html": body, "frozen": True}


def roster_articles(st, data, D):
    """Kokoonpanomuutokset: vertaa suomalaisten NHL-kokoonpanoja edelliseen päivään."""
    cur = load_json(os.path.join(DATA, "rosters.json"), {})
    if cur.get("date") != D.isoformat() or not cur.get("players"):
        return []
    now_map = {str(p["id"]): {"team": p["team"], "name": p["name"]} for p in cur["players"]}
    prev = st.get("roster_prev")
    out = []
    if prev and st.get("roster_date") != D.isoformat():
        slugs = data["finnSlugs"]
        def link(n):
            return f"<a href='/suomalaiset/{slugs[n]}.html'>{esc(n)}</a>" if n in slugs else esc(n)
        for pid, p in now_map.items():
            o = prev.get(pid)
            if not o:
                title = f"{p['name']} mukana {tname(p['team'])} -joukkueen NHL-kokoonpanossa"
                lead = f"{p['name']} on lisätty {tname(p['team'])} -joukkueen NHL-kokoonpanoon."
                kind = "nousu"
            elif o["team"] != p["team"]:
                title = f"{p['name']} siirtyi {tname(o['team'])} -joukkueesta {tname(p['team'])} -joukkueeseen"
                lead = f"{p['name']} kuuluu nyt {tname(p['team'])} -joukkueen NHL-kokoonpanoon. Aiemmin hän oli {tname(o['team'])} -joukkueen kokoonpanossa."
                kind = "siirto"
            else:
                continue
            body = (f"<p class='ingressi'>{esc(lead)}</p><p>Tieto perustuu NHL:n julkaisemiin joukkueiden kokoonpanoihin ({esc(fi_date(D.isoformat()))}). "
                    f"Muutoksen syy, esimerkiksi nosto farmista, kauppa tai siirtolista, ei käy ilmi kokoonpanotiedoista.</p>"
                    f"<p class='small'>{link(p['name'])} · <a href='/joukkueet/{tslug(p['team'])}/'>{esc(tname(p['team']))}</a></p>")
            out.append({"id": f"r-{D.isoformat()}-{pid}", "type": "kokoonpano", "slug": f"{D.isoformat()}-{slugify(p['name'])}-{kind}",
                        "date": D.isoformat(), "published": dt.datetime(D.year, D.month, D.day, 12, 0, tzinfo=HEL).isoformat(timespec="minutes"),
                        "title": title, "lead": lead, "html": body, "frozen": True})
        for pid, o in prev.items():
            if pid not in now_map:
                title = f"{o['name']} ei ole enää {tname(o['team'])} -joukkueen NHL-kokoonpanossa"
                lead = f"{o['name']} on poistunut {tname(o['team'])} -joukkueen NHL-kokoonpanosta."
                body = (f"<p class='ingressi'>{esc(lead)}</p><p>Tieto perustuu NHL:n julkaisemiin joukkueiden kokoonpanoihin ({esc(fi_date(D.isoformat()))}). "
                        "Muutoksen syy, esimerkiksi siirto farmiin, kauppa tai loukkaantuminen, ei käy ilmi kokoonpanotiedoista.</p>")
                out.append({"id": f"r-{D.isoformat()}-{pid}-out", "type": "kokoonpano", "slug": f"{D.isoformat()}-{slugify(o['name'])}-pois-kokoonpanosta",
                            "date": D.isoformat(), "published": dt.datetime(D.year, D.month, D.day, 12, 0, tzinfo=HEL).isoformat(timespec="minutes"),
                            "title": title, "lead": lead, "html": body, "frozen": True})
    if st.get("roster_date") != D.isoformat():
        st["roster_prev"] = now_map
        st["roster_date"] = D.isoformat()
    return out


def weekly_article(data, arch_days, D):
    """Maanantain viikkokatsaus: edellisen seitsemän pelipäivän suomalaistehot."""
    days = sorted(d for d in arch_days if d <= (D - dt.timedelta(days=1)).isoformat())[-7:]
    if len(days) < 3:
        return None
    pts, gks, games = {}, {}, 0
    for d in days:
        for g in arch_days[d]:
            games += 1
            for f in g.get("finStats") or []:
                if f.get("pos") == "MV":
                    x = gks.setdefault(f["name"], [f["team"], 0, 0, 0, 0])
                    x[1] += 1; x[2] += f.get("saves") or 0; x[3] += f.get("shots") or 0; x[4] += 1 if f.get("dec") == "W" else 0
                else:
                    x = pts.setdefault(f["name"], [f["team"], 0, 0, 0, 0])
                    x[1] += 1; x[2] += f.get("g") or 0; x[3] += f.get("a") or 0; x[4] += f.get("p") or 0
    top = sorted(pts.items(), key=lambda kv: (-kv[1][4], -kv[1][2], kv[0]))
    if not top:
        return None
    wk = D.isocalendar()[1]
    a, b = dt.date.fromisoformat(days[0]), dt.date.fromisoformat(days[-1])
    rng = f"{a.day}.{a.month}.–{b.day}.{b.month}."
    best = top[0]
    title = f"Suomalaisten NHL-viikko {wk}: {best[0]} keräsi {best[1][4]} pistettä"
    lead = f"Viikolla {rng} pelattiin {games} NHL-ottelua. Suomalaisista eniten pisteitä keräsi {best[0]}: {best[1][2]}+{best[1][3]}={best[1][4]} {best[1][1]} ottelussa."
    slugs = data["finnSlugs"]
    def nm(n):
        return f"<a href='/suomalaiset/{slugs[n]}.html'>{esc(n)}</a>" if n in slugs else esc(n)
    body = [f"<p class='ingressi'>{esc(lead)}</p><h2>Viikon pistemiehet</h2><table class='t'><tr><th>Pelaaja</th><th>O</th><th>M</th><th>S</th><th>P</th></tr>"
            + "".join(f"<tr><td>{i + 1}. {tbadge(v[0], 'mini')} {nm(n)}</td><td>{v[1]}</td><td>{v[2]}</td><td>{v[3]}</td><td><b>{v[4]}</b></td></tr>" for i, (n, v) in enumerate(top[:10]) if v[4]) + "</table>"]
    if gks:
        body.append("<h2>Viikon maalivahdit</h2><table class='t'><tr><th>Maalivahti</th><th>O</th><th>V</th><th>TO%</th></tr>"
                    + "".join(f"<tr><td>{tbadge(v[0], 'mini')} {nm(n)}</td><td>{v[1]}</td><td>{v[4]}</td><td>{(f'{v[2] / v[3]:.3f}'.lstrip('0')) if v[3] else '–'}</td></tr>"
                              for n, v in sorted(gks.items(), key=lambda kv: -kv[1][1])) + "</table>")
    wm = [m for m in MILES.get("reached") or [] if days[0] <= m["date"] <= D.isoformat()]
    if wm:
        body.append("<h2>Viikon virstanpylväät</h2><ul>" + "".join(f"<li>{esc(mile_txt(m, True))}.</li>" for m in wm) + "</ul>")
    body.append("<p class='small'><a href='/koosteet/'>Päivittäiset koosteet</a> · <a href='/suomalaiset/'>Kauden tilastot</a></p>")
    return {"id": f"w-{D.isocalendar()[0]}-{wk}", "type": "viikkokatsaus", "slug": f"{D.isoformat()}-suomalaisten-nhl-viikko-{wk}", "date": D.isoformat(),
            "published": dt.datetime(D.year, D.month, D.day, 10, 0, tzinfo=HEL).isoformat(timespec="minutes"),
            "title": title, "lead": lead, "html": "".join(body), "frozen": True}


TYPE_FI = {"ennakko": "Ennakko", "virstanpylväs": "Virstanpylväs", "kokoonpano": "Kokoonpano", "viikkokatsaus": "Viikkokatsaus", "kooste": "Kooste"}


def build_news(data, arch_days, urls):
    path = os.path.join(DATA, "news.json")
    st = load_json(path, {"articles": []})
    now = now_utc().astimezone(HEL)
    D = now.date()
    try:
        if now.hour >= 10:
            p = preview_article(data, D, now, arch_days)
            if p:
                news_upsert(st, p)
    except Exception as e:
        log("ennakko epäonnistui", e)
    try:
        for m in MILES.get("reached") or []:
            news_upsert(st, milestone_article(m, data))
    except Exception as e:
        log("virstanpylväsuutinen epäonnistui", e)
    try:
        for a in roster_articles(st, data, D):
            news_upsert(st, a)
    except Exception as e:
        log("kokoonpanouutiset epäonnistuivat", e)
    try:
        if D.weekday() == 0 and now.hour >= 9 and not data["pending"]:
            w = weekly_article(data, arch_days, D)
            if w:
                news_upsert(st, w)
    except Exception as e:
        log("viikkokatsaus epäonnistui", e)
    # vain viimeiset 120 päivää
    cut = (D - dt.timedelta(days=120)).isoformat()
    st["articles"] = [a for a in st["articles"] if a["date"] >= cut]
    save_json(path, st, pretty=False)
    arts = sorted(st["articles"], key=lambda a: a["published"], reverse=True)
    base = CFG["baseUrl"].rstrip("/")
    for a in arts:
        url = _art_slug(a)
        pub = dt.datetime.fromisoformat(a["published"])
        body = (f"<p class='kdate'>{esc(TYPE_FI.get(a['type'], 'Uutinen'))} · Julkaistu {esc(fi_date(pub.date().isoformat()))} klo {pub:%H.%M}</p>"
                f"<h1>{esc(a['title'])}</h1><p class='byline'>Punalamppu · Automaattinen uutinen NHL:n tilastoista · tekoälyn avulla tehty, ihmisen tarkastamat tekstipohjat</p>"
                f"<div class='art'>{a['html']}</div>"
                "<h2>Lähteet ja tekotapa</h2><p class='small'>Uutinen perustuu NHL:n virallisiin tilastoihin ja kokoonpanotietoihin (NHL.com). "
                "Se on tuotettu automaattisesti tekoälyn avulla laaditulla ohjelmalla, joka kirjoittaa tekstin suoraan tilastoista. "
                "Ylläpitäjä tarkastaa tekstipohjat ja säännöt aina, kun niitä muutetaan. Yksittäisiä uutisia ei tarkasteta ennen julkaisua. "
                "Tekstissä ei ole arvioita eikä lainauksia. Huomasitko virheen? <a href='/yhteys.html'>Ilmoita siitä meille</a>, niin korjaamme sen. "
                "<a href='/tietoa.html#tekoaly'>Näin Punalamppu käyttää tekoälyä</a>.</p>"
                "<p class='small'><a href='/uutiset/'>Kaikki uutiset</a></p>")
        jl = {"@context": "https://schema.org", "@graph": [
            {"@type": "NewsArticle", "headline": a["title"][:110], "datePublished": a["published"], "dateModified": a["published"] if a.get("frozen") else now.isoformat(timespec="minutes"),
             "inLanguage": "fi", "description": a["lead"][:300], "author": {"@type": "Organization", "name": CFG["siteName"], "url": CFG["baseUrl"]},
             "publisher": {"@type": "Organization", "name": CFG["siteName"], "logo": {"@type": "ImageObject", "url": base + "/icon-512.png"}},
             "mainEntityOfPage": base + url, "image": base + "/og.png"},
            crumbs([("Punalamppu", "/"), ("Uutiset", "/uutiset/"), (a["title"][:60], url)])]}
        write_page(url, f"{a['title']} | {CFG['siteName']}", a["lead"][:300], body, jl, urls=urls)
    # hakemisto: uutiset ja koosteet yhdessä
    items = [(a["published"], a["title"], _art_slug(a), TYPE_FI.get(a["type"], "Uutinen"), a["lead"]) for a in arts]
    for d, nice, h, ld in KOOSTEET:
        pubd = (dt.date.fromisoformat(d) + dt.timedelta(days=1)).isoformat()
        items.append((f"{pubd}T07:00+02:00", h, f"/koosteet/{d}/", "Kooste", ld))
    items.sort(key=lambda x: x[0], reverse=True)
    lis = "".join(f"<li><a class='krow' href='{u}'><span class='gt'>{esc(k)} · {esc(fi_dshort(p[:10]))}</span><b>{esc(t)}</b><span class='mute'>{esc(ld[:160])}</span></a></li>"
                  for p, t, u, k, ld in items[:80])
    write_page("/uutiset/", f"NHL-uutiset suomeksi – suomalaiset, ennakot ja koosteet | {CFG['siteName']}",
               "Automaattiset NHL-uutiset suomeksi: päivän ennakot, yön suomalaiskoosteet, virstanpylväät, kokoonpanomuutokset ja viikkokatsaukset.",
               "<h1>Uutiset</h1><p class='lead'>Päivän ennakot, yön suomalaiskoosteet, virstanpylväät, kokoonpanomuutokset ja viikkokatsaukset. "
               "Uutiset tuotetaan automaattisesti NHL:n tilastoista tekoälyn avulla. Tilaa ne <a href='/rss.xml'>RSS-syötteenä</a> tai "
               "<a href='https://t.me/punalamppu' rel='noopener'>Telegramissa</a>.</p>"
               f"<h2>Tuoreimmat</h2><ul class='rows'>{lis or '<li>Ei vielä uutisia.</li>'}</ul>",
               {"@context": "https://schema.org", "@graph": [crumbs([("Punalamppu", "/"), ("Uutiset", "/uutiset/")])]}, urls=urls)
    NEWS["items"] = items
    return items


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
        career += MILE_HTML.get(name, "")
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
