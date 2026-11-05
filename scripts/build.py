#!/usr/bin/env python3
"""Punalamppu – hakee NHL:n julkiset tulos- ja tilastotiedot ja rakentaa staattisen sivuston kansioon _site/.

Ajetaan GitHub Actionsissa (.github/workflows/update.yml). Käyttää vain Pythonin vakiokirjastoa.

Ympäristömuuttujat testaukseen:
  KA_FIXTURES=<kansio>  lukee rajapintavastaukset tiedostoista verkon sijaan
  KA_NOW=<ISO-aika>     korvaa nykyhetken (esim. 2026-11-05T04:00:00Z)
"""
import datetime as dt
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


def get_text(url):
    if FIXTURES:
        p = fixture_path(url)[:-5] + ".xml"
        return open(p, encoding="utf-8").read() if os.path.exists(p) else None
    req = urllib.request.Request(url, headers={"User-Agent": CFG["userAgent"]})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
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
    if cache.get("date") != today.isoformat() or not cache.get("players"):
        players = []
        for abbr in TEAMS:
            d = get(f"{API}/roster/{abbr}/current") or {}
            for grp, pos in (("forwards", "H"), ("defensemen", "P"), ("goalies", "MV")):
                for p in d.get(grp) or []:
                    if (p.get("birthCountry") or "").upper() != "FIN":
                        continue
                    players.append({"id": p.get("id"), "name": fixname(full_name(p)), "team": abbr, "pos": pos})
        if players:
            cache = {"date": today.isoformat(), "players": players}
            save_json(path, cache)
    return cache.get("players") or []


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
        "history": hist[-120:],
        "sources": [{"name": "NHL.com (julkiset tulos- ja tilastotiedot)", "url": "https://www.nhl.com/"}],
    }


# ---------------------------------------------------------------- sivut
def page(title, desc, path, body, jsonld=None):
    base = CFG["baseUrl"].rstrip("/")
    ld = f'<script type="application/ld+json">{json.dumps(jsonld, ensure_ascii=False)}</script>' if jsonld else ""
    return f"""<!DOCTYPE html>
<html lang="fi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title><meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{base}{path}"><meta property="og:title" content="{esc(title)}"><meta property="og:description" content="{esc(desc)}">
<meta property="og:type" content="website"><meta property="og:url" content="{base}{path}"><meta property="og:locale" content="fi_FI">
<meta property="og:image" content="{base}/og.png"><meta name="twitter:card" content="summary_large_image">
<link rel="icon" href="/favicon.svg" type="image/svg+xml"><link rel="apple-touch-icon" href="/apple-touch-icon.png"><meta name="theme-color" content="#0B1118"><link rel="stylesheet" href="/static.css">{ld}</head>
<body><div class="wrap"><header><a class="brand" href="/" aria-label="Punalamppu – etusivu"><img src="/logo-mark.svg" alt="" width="34" height="34"><span>PUNA<b>LAMPPU</b></span></a></header>
<nav class="crumbs"><a href="/">Tulokset</a> · <a href="/otteluohjelma/">Otteluohjelma</a> · <a href="/suomalaiset/">Suomalaiset</a> · <a href="/pisteporssi/">Pistepörssi</a> · <a href="/sarjataulukko/">Sarjataulukko</a> · <a href="/ottelut/">Arkisto</a></nav>
<main>{body}</main>{footer()}</div></body></html>"""


def footer():
    return (f'<footer class="foot"><p>{esc(CFG["siteName"])} on itsenäinen harrastussivusto, jolla ei ole yhteyttä National Hockey Leagueen (NHL) '
            'tai sen joukkueisiin. NHL ja joukkueiden nimet ovat omistajiensa tavaramerkkejä. Tulos- ja tilastotiedot: NHL.com.</p>'
            '<p><a href="/tietoa.html">Tietoa sivustosta</a> · <a href="/tietosuoja.html">Tietosuoja</a></p></footer>')


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
        return ""
    return (f'<div class="yt" data-id="{vid}"><button type="button" onclick="kaYT(this.parentNode)">▶ Katso maalikooste</button>'
            f'<p class="mute">Video: NHL / YouTube. Video ladataan YouTubesta vasta painettaessa (YouTube voi tällöin asettaa evästeitä).</p></div>'
            '<script>function kaYT(d){d.innerHTML=\'<iframe src="https://www.youtube-nocookie.com/embed/\'+d.dataset.id+\'?autoplay=1&rel=0" title="Maalikooste – NHL / YouTube" allow="autoplay; encrypted-media; picture-in-picture; fullscreen" allowfullscreen loading="lazy"></iframe><p class="mute">Video: NHL / YouTube</p>\'}</script>')


def fi_date(gd):
    y, m, d = gd.split("-")
    wd = ["maanantai", "tiistai", "keskiviikko", "torstai", "perjantai", "lauantai", "sunnuntai"][dt.date(int(y), int(m), int(d)).weekday()]
    return f"{wd} {int(d)}.{int(m)}.{y}"


def score_txt(g):
    s = f"{g['awayScore']}–{g['homeScore']}"
    return s + (f" {g['final']}" if g.get("final") else "")


def render_game_page(gd, g, slugs):
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
        rows.append(f"<li><span class='mute'>{per} {esc(x['t'])}</span> <b>{esc(x['team'])}</b> {who}{tag}{ast}</li>")
    stars = "".join(f"<li>{'★' * (s.get('star') or 1)} {esc(s['name'])} ({esc(s['team'])}) – {esc(star_line(s))}</li>" for s in g.get("threeStars", []))
    body = f"""<article><h1>{esc(a)} – {esc(h)} <span class="sc">{esc(score_txt(g))}</span></h1>
<p class="mute">{esc(fi_date(gd).capitalize())}{(' · ' + esc(g['venue'])) if g.get('venue') else ''}</p>
{f'<p>{esc(g["note"])}</p>' if g.get('note') else ''}
{video_block(g, gd)}
<p class="btns"><a class="btn" href="{yt_url(gd, g)}" rel="noopener">▶ Maalikooste YouTubessa</a>{f' <a class="btn alt" href="{esc(g["recapUrl"])}" rel="noopener">Kooste NHL.comissa</a>' if g.get('recapUrl') else ''}</p>
<h2>Maalit</h2><ol class="goals">{''.join(rows) or '<li class="mute">Ei maalitietoja.</li>'}</ol>
{f'<h2>Maalivahdit</h2><p>{esc(g["goalies"])}</p>' if g.get('goalies') else ''}
{f'<h2>Ottelun tähdet</h2><ul>{stars}</ul>' if stars else ''}
<p><a href="/ottelut/">← Kaikki ottelut</a></p></article>"""
    jsonld = {"@context": "https://schema.org", "@type": "SportsEvent", "name": f"{a} – {h}", "sport": "Jääkiekko",
              "startDate": g.get("start") or gd, "eventStatus": "https://schema.org/EventScheduled",
              "awayTeam": {"@type": "SportsTeam", "name": a}, "homeTeam": {"@type": "SportsTeam", "name": h},
              "location": {"@type": "Place", "name": g.get("venue") or h},
              "description": desc}
    return title, desc, body, jsonld


def build_site(data):
    if os.path.exists(OUT):
        shutil.rmtree(OUT)
    shutil.copytree(WEB, OUT)
    base = CFG["baseUrl"].rstrip("/")
    slugs = data["finnSlugs"]
    urls = ["/", "/ottelut/", "/suomalaiset/", "/tietoa.html", "/tietosuoja.html"]
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
              .replace("{{FOOTER}}", footer()))
    idx = idx.replace("{{JSONLD}}", json.dumps({"@context": "https://schema.org", "@type": "WebSite", "name": CFG["siteName"],
                                                 "url": base + "/", "inLanguage": "fi"}, ensure_ascii=False))
    open(os.path.join(OUT, "index.html"), "w", encoding="utf-8").write(idx)
    save_json(os.path.join(OUT, "data.json"), data, pretty=False)

    # --- tieto- ja tietosuojasivut
    for fn in ("tietoa.html", "tietosuoja.html", "404.html"):
        p = os.path.join(OUT, fn)
        if os.path.exists(p):
            s = open(p, encoding="utf-8").read()
            s = (s.replace("{{SITE}}", esc(CFG["siteName"])).replace("{{BASE}}", base)
                  .replace("{{EMAIL}}", esc(CFG.get("contactEmail") or "(lisää yhteystieto config.json-tiedostoon)"))
                  .replace("{{OWNER}}", esc(CFG.get("ownerName") or "(lisää ylläpitäjän nimi config.json-tiedostoon)"))
                  .replace("{{FOOTER}}", footer()))
            open(p, "w", encoding="utf-8").write(s)

    # --- ottelusivut arkistosta
    os.makedirs(os.path.join(OUT, "ottelut"), exist_ok=True)
    days = []
    for fn in sorted(os.listdir(os.path.join(DATA, "archive")), reverse=True):
        if not fn.endswith(".json"):
            continue
        a = load_json(os.path.join(DATA, "archive", fn), {})
        d = a.get("gameDate") or fn[:-5]
        glist = list((a.get("games") or {}).values())
        lis = []
        for g in glist:
            title, desc_g, body, jl = render_game_page(d, g, slugs)
            path = f"/ottelut/{game_slug(d, g)}.html"
            open(os.path.join(OUT, path.lstrip("/")), "w", encoding="utf-8").write(page(title, desc_g, path, body, jl))
            urls.append(path)
            lis.append(f"<li><a href='{path}'>{esc(tname(g['away']))} – {esc(tname(g['home']))} {esc(score_txt(g))}</a></li>")
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
        open(os.path.join(OUT, path.lstrip("/")), "w", encoding="utf-8").write(page(title, desc_p, path, body, jl))
        urls.append(path)
        rows.append(f"<tr><td><a href='{path}'>{esc(name)}</a></td><td>{esc(t)}</td><td>{gp}</td><td>{g_}</td><td>{a_}</td><td><b>{p_}</b></td></tr>")
    for f in data["finnGoalies"]:
        name, t = f[0], f[1]
        path = f"/suomalaiset/{slugs[name]}.html"
        title, desc_p, body, jl = render_player(name, t, "MV", f, True, data, gd, slugs)
        open(os.path.join(OUT, path.lstrip("/")), "w", encoding="utf-8").write(page(title, desc_p, path, body, jl))
        urls.append(path)
    open(os.path.join(OUT, "suomalaiset", "index.html"), "w", encoding="utf-8").write(page(
        f"Suomalaiset NHL:ssä {season_label(gd)} – pisteet ja tilastot | {CFG['siteName']}",
        f"Kaikki suomalaiset NHL-pelaajat kaudella {season_label(gd)}: pisteet, maalit ja maalivahtitilastot päivittäin.",
        "/suomalaiset/",
        f"<h1>Suomalaiset NHL:ssä {season_label(gd)}</h1><table class='t'><tr><th>Pelaaja</th><th>Joukkue</th><th>O</th><th>M</th><th>S</th><th>P</th></tr>{''.join(rows)}</table>"
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
        return f"<tr><td>{i}. {nm}</td><td>{esc(p[1])}</td><td>{p[2]}</td><td>{p[3]}</td><td>{p[4]}</td><td><b>{p[5]}</b></td></tr>"
    head = "<tr><th>Pelaaja</th><th>Joukkue</th><th>O</th><th>M</th><th>S</th><th>P</th></tr>"
    sk = data["skaters"]
    by_g = sorted(sk, key=lambda x: (-x[3], -x[5]))[:20]
    top3 = ", ".join(f"{p[0]} {p[5]} p" for p in sk[:3])
    write("/pisteporssi/", f"NHL-pistepörssi {sl} – pisteet, maalit ja syötöt | {CFG['siteName']}",
          f"NHL:n pistepörssi kaudella {sl} päivittäin päivitettynä. Kärjessä: {top3}. Myös maalipörssi, syöttöpörssi ja suomalaiset.",
          f"<h1>NHL-pistepörssi {sl}</h1><p class='mute'>Päivitetty {esc(data['updated'][:10])}. Suomalaisten oma pörssi: <a href='/suomalaiset/'>suomalaiset NHL:ssä</a>.</p>"
          f"<table class='t'>{head}{''.join(plrow(i + 1, p) for i, p in enumerate(sk[:50]))}</table>"
          f"<h2>Maalipörssi</h2><table class='t'>{head}{''.join(plrow(i + 1, p) for i, p in enumerate(by_g))}</table>")
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
            + (f" <span class='mute'>(🇫🇮 {esc(', '.join(n.split(' ')[-1] for n in finn_by_team(data, u['away'], u['home'])))})</span>" if finn_by_team(data, u['away'], u['home']) else "")
            + "</li>" for u in sorted(lst, key=lambda x: x["start"] or "")) + "</ul>"
    write("/otteluohjelma/", f"NHL-otteluohjelma – tulevat ottelut Suomen aikaa | {CFG['siteName']}",
          "NHL:n otteluohjelma seuraavalle viikolle Suomen ajassa. Näet myös, missä otteluissa suomalaiset pelaavat.",
          f"<h1>NHL-otteluohjelma Suomen aikaa</h1><p class='mute'>Kellonajat Suomen aikaa. Otsikon päivä on NHL:n pelipäivä Pohjois-Amerikassa; ottelut pelataan Suomessa seuraavana yönä.</p>{orows or '<p>Ei tulevia otteluita tiedossa.</p>'}")

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
            out.append(f"<li>{esc(fi_date(d))}: vs {esc(tname(opp))} – <a href='/ottelut/{game_slug(d, g)}.html'>ottelu</a></li>")
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
    lead = f"{esc(name)} on {str(age) + '-vuotias ' if age else ''}suomalainen {posn}"
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
    mates_html = ("<p>Muut suomalaiset joukkueessa: " + ", ".join(f"<a href='/suomalaiset/{slugs[n]}.html'>{esc(n)}</a>" for n in mates if n in slugs) + ".</p>") if mates else ""
    recent = recent_goals(name)
    # usein kysytyt
    faq = [(f"Missä joukkueessa {name} pelaa?", f"{name} pelaa NHL:ssä {team_full} -joukkueessa." if team_full else f"{name} ei ole tällä hetkellä NHL-kokoonpanossa.")]
    faq.append((f"Paljonko {name} on tehnyt pisteitä kaudella {sl}?" if not is_goalie else f"Millaiset tilastot {name} on tehnyt kaudella {sl}?", season_line))
    faq_html = "<h2>Usein kysyttyä</h2>" + "".join(f"<h3>{esc(q)}</h3><p>{esc(a)}</p>" for q, a in faq)
    body = (f"<article><h1>{esc(name)}</h1><p class='mute'>{esc(team_full or 'NHL')} · {posn}</p>"
            f"<p>{lead} {esc(born)} {esc(season_line)}</p>"
            + (f"<p class='mute'>{esc(', '.join(phys).capitalize())}. {draft}</p>" if phys or draft else "")
            + f"<h2>Kausi {sl}</h2><div class='tw'>{stat_tbl}</div>{l5html}"
            + (f"<h2>Viimeisimmät maalit</h2><ul>{recent}</ul>" if recent else "")
            + nxt_html + career + mates_html + faq_html
            + "<p><a href='/suomalaiset/'>← Kaikki suomalaiset NHL:ssä</a></p></article>")
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


def finn_by_team(data, *teams):
    return [f[0] for f in data["finns"] if f[1] in teams] + [f[0] for f in data["finnGoalies"] if f[1] in teams]


def season_label(gd):
    y, m = int(gd[:4]), int(gd[5:7])
    s = y if m >= 7 else y - 1
    return f"{s}–{str(s + 1)[2:]}"


if __name__ == "__main__":
    data = collect()
    build_site(data)
