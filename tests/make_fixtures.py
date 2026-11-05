#!/usr/bin/env python3
"""Luo testiaineiston (tests/fixtures/) NHL-rajapinnan muotoisista vastauksista.
Aineisto perustuu 4.11.2026 otteluihin. Se testaa sivuston koodin – ei rajapinnan todellista muotoa."""
import json, os, re, sys, urllib.parse
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "fixtures")
os.makedirs(OUT, exist_ok=True)
API = "https://api-web.nhle.com/v1"; STATS = "https://api.nhle.com/stats/rest/en"; SID = "20262027"


def save(url, obj):
    name = re.sub(r"[^A-Za-z0-9]+", "_", url.split("://", 1)[-1]).strip("_")
    json.dump(obj, open(os.path.join(OUT, name[:180] + ".json"), "w"), ensure_ascii=False)


def D(s): return {"default": s}


def goal(per, t, team, fn, ln, pid, strength="ev", mod="", ast=()):
    return {"period": per, "periodDescriptor": {"number": per, "periodType": "OT" if per == 4 else "REG"}, "timeInPeriod": t,
            "teamAbbrev": D(team), "firstName": D(fn), "lastName": D(ln), "name": D(fn[0] + ". " + ln), "playerId": pid,
            "strength": strength, "goalModifier": mod, "assists": [{"name": D(a), "firstName": D(a.split()[0]), "lastName": D(a.split()[-1])} for a in ast]}


games = [
    (2026020201, "SJS", 2, "LAK", 7, "REG", [
        goal(1, "01:23", "LAK", "Adrian", "Kempe", 1), goal(1, "16:09", "LAK", "Adrian", "Kempe", 1, ast=["Artemi Panarin"]),
        goal(1, "18:38", "LAK", "Quinton", "Byfield", 2, "pp", ast=["Artemi Panarin", "Adrian Kempe"]),
        goal(2, "05:07", "SJS", "Macklin", "Celebrini", 3, "pp"), goal(2, "11:10", "LAK", "Erik", "Haula", 100, ast=["Joel Armia"]),
        goal(2, "15:51", "LAK", "Adrian", "Kempe", 1, "pp", ast=["Artemi Panarin"]), goal(3, "02:12", "LAK", "Joel", "Armia", 101),
        goal(3, "13:02", "SJS", "Will", "Smith", 4, "pp"), goal(3, "14:28", "LAK", "Quinton", "Byfield", 2, ast=["Artemi Panarin"])],
     [("Adrian Kempe", "LAK", "C", 3, 1, 4), ("Artemi Panarin", "LAK", "L", 0, 4, 4), ("Darcy Kuemper", "LAK", "G", None, None, None)]),
    (2026020202, "CHI", 3, "FLA", 5, "REG", [
        goal(1, "04:43", "FLA", "Sandis", "Vilmanis", 5), goal(1, "12:29", "FLA", "Carter", "Verhaeghe", 6, "pp", ast=["Anton Lundell"]),
        goal(2, "13:20", "FLA", "Seth", "Jones", 7), goal(2, "16:48", "CHI", "Roman", "Kantserov", 8, ast=["Teuvo Teräväinen"]),
        goal(3, "09:31", "CHI", "Frank", "Nazar", 9, "sh"), goal(3, "11:01", "FLA", "Sandis", "Vilmanis", 5),
        goal(3, "16:09", "CHI", "Frank", "Nazar", 9), goal(3, "18:33", "FLA", "Sam", "Reinhart", 10, mod="empty-net")],
     [("Sandis Vilmanis", "FLA", "R", 2, 2, 4), ("Sam Reinhart", "FLA", "C", 1, 2, 3), ("Frank Nazar", "CHI", "C", 2, 0, 2)]),
    (2026020203, "OTT", 2, "BUF", 1, "REG", [
        goal(2, "14:00", "BUF", "Peyton", "Krebs", 11, ast=["Konsta Helenius"]), goal(3, "11:33", "OTT", "Shane", "Pinto", 12),
        goal(3, "16:51", "OTT", "Michael", "Amadio", 13, ast=["Nikolas Matinpalo"])],
     [("Michael Amadio", "OTT", "R", 1, 0, 1), ("Samuel Ersson", "OTT", "G", None, None, None), ("Shane Pinto", "OTT", "C", 1, 0, 1)]),
    (2026020204, "CGY", 1, "SEA", 2, "OT", [
        goal(1, "12:15", "CGY", "Yegor", "Sharangovich", 14), goal(2, "13:09", "SEA", "Berkly", "Catton", 15, ast=["Kaapo Kakko"]),
        goal(4, "00:55", "SEA", "Matty", "Beniers", 16)],
     [("Matty Beniers", "SEA", "C", 1, 0, 1), ("Joey Daccord", "SEA", "G", None, None, None), ("Dustin Wolf", "CGY", "G", None, None, None)]),
]
save(f"{API}/score/2026-11-04", {"games": [
    {"id": gid, "gameState": "OFF", "startTimeUTC": "2026-11-05T00:30:00Z", "awayTeam": {"abbrev": a, "score": as_}, "homeTeam": {"abbrev": h, "score": hs},
     "periodDescriptor": {"number": 4 if lpt == "OT" else 3, "periodType": lpt}, "gameOutcome": {"lastPeriodType": lpt}, "goals": gl,
     "threeMinRecap": f"/video/{a.lower()}-at-{h.lower()}-recap"} for gid, a, as_, h, hs, lpt, gl, _ in games]})
save(f"{API}/score/2026-11-05", {"games": [{"id": 2026020210, "gameState": "FUT", "startTimeUTC": "2026-11-06T00:00:00Z",
                                            "awayTeam": {"abbrev": "PHI"}, "homeTeam": {"abbrev": "NYR"}}]})
gk_saves = {2026020201: [("Yaroslav Askarov", "L", 24, "SJS"), ("Darcy Kuemper", "W", 30, "LAK")], 2026020202: [("Spencer Knight", "L", 20, "CHI"), ("Jacob Markstrom", "W", 17, "FLA")],
            2026020203: [("Samuel Ersson", "W", 24, "OTT"), ("Colten Ellis", "L", 28, "BUF")], 2026020204: [("Dustin Wolf", "O", 27, "CGY"), ("Joey Daccord", "W", 25, "SEA")]}
for gid, a, _, h, _, _, _, stars in games:
    gs = gk_saves[gid]
    save(f"{API}/gamecenter/{gid}/boxscore", {"venue": D("Arena"), "awayTeam": {"abbrev": a}, "homeTeam": {"abbrev": h}, "playerByGameStats": {
        "awayTeam": {"goalies": [{"name": D(gs[0][0]), "decision": gs[0][1], "saves": gs[0][2]}]},
        "homeTeam": {"goalies": [{"name": D(gs[1][0]), "decision": gs[1][1], "saves": gs[1][2]}]}}})
    save(f"{API}/gamecenter/{gid}/landing", {"summary": {"threeStars": [
        {"star": i + 1, "name": D(n), "teamAbbrev": t, "position": p, "goals": g_, "assists": a_, "points": p_, "savePctg": .937 if p == "G" else None}
        for i, (n, t, p, g_, a_, p_) in enumerate(stars)]}})

save(f"{API}/standings/now", {"standings": [
    {"teamAbbrev": D(t), "divisionName": dv, "conferenceName": cf, "gamesPlayed": r[0], "wins": r[1], "losses": r[2], "otLosses": r[3], "points": r[4], "goalFor": r[5], "goalAgainst": r[6]}
    for dv, cf, rows in [
        ("Atlantic", "Eastern", [("BOS", (16, 11, 4, 1, 23, 58, 38)), ("MTL", (15, 9, 3, 3, 21, 52, 47)), ("OTT", (17, 10, 6, 1, 21, 54, 52)), ("TBL", (14, 9, 3, 2, 20, 52, 45)), ("FLA", (16, 9, 5, 2, 20, 52, 47)), ("TOR", (17, 8, 7, 2, 18, 62, 56)), ("BUF", (15, 7, 5, 3, 17, 44, 51)), ("DET", (16, 7, 6, 3, 17, 48, 50))]),
        ("Metropolitan", "Eastern", [("CAR", (17, 12, 3, 2, 26, 64, 40)), ("NJD", (15, 10, 5, 0, 20, 52, 43)), ("NYR", (16, 8, 7, 1, 17, 48, 47)), ("WSH", (14, 8, 6, 0, 16, 49, 48)), ("NYI", (14, 7, 5, 2, 16, 40, 39)), ("CBJ", (13, 6, 7, 0, 12, 36, 41)), ("PIT", (15, 5, 8, 2, 12, 49, 52)), ("PHI", (17, 4, 9, 4, 12, 37, 58))]),
        ("Central", "Western", [("MIN", (17, 11, 3, 3, 25, 56, 38)), ("UTA", (16, 10, 6, 0, 20, 57, 54)), ("DAL", (15, 9, 5, 1, 19, 44, 36)), ("COL", (16, 9, 6, 1, 19, 66, 53)), ("NSH", (15, 6, 4, 5, 17, 46, 48)), ("STL", (15, 7, 7, 1, 15, 45, 45)), ("WPG", (16, 5, 8, 3, 13, 39, 58)), ("CHI", (16, 4, 11, 1, 9, 36, 63))]),
        ("Pacific", "Western", [("EDM", (16, 11, 2, 3, 25, 67, 48)), ("VGK", (17, 10, 5, 2, 22, 58, 49)), ("SEA", (15, 9, 5, 1, 19, 54, 53)), ("ANA", (15, 7, 7, 1, 15, 54, 57)), ("CGY", (16, 7, 8, 1, 15, 39, 55)), ("SJS", (17, 7, 9, 1, 15, 44, 61)), ("LAK", (14, 5, 7, 2, 12, 43, 47)), ("VAN", (17, 3, 13, 1, 7, 51, 77))])]
    for t, r in rows]})

save(f"{API}/schedule/2026-11-05", {"gameWeek": [
    {"date": "2026-11-05", "games": [{"gameState": "FUT", "startTimeUTC": "2026-11-06T00:00:00Z", "awayTeam": {"abbrev": a}, "homeTeam": {"abbrev": h}} for a, h in
                                      [("PHI", "NYR"), ("CAR", "NYI"), ("DAL", "CBJ"), ("VAN", "WPG")]] + [{"gameState": "FUT", "startTimeUTC": "2026-11-06T02:30:00Z", "awayTeam": {"abbrev": "NSH"}, "homeTeam": {"abbrev": "COL"}}]},
    {"date": "2026-11-12", "games": [{"gameState": "FUT", "startTimeUTC": "2026-11-12T17:00:00Z", "awayTeam": {"abbrev": "CAR"}, "homeTeam": {"abbrev": "SEA"}, "neutralSite": True, "venue": D("Veikkaus Arena")}]}]})

sk = [  # pid, nimi, joukkue, pos, gp, g, a, fin
    (1, "Adrian Kempe", "LAK", "C", 13, 6, 6, 0), (20, "Connor McDavid", "EDM", "C", 16, 9, 31, 0), (21, "Leon Draisaitl", "EDM", "C", 16, 13, 16, 0),
    (22, "Kirill Kaprizov", "MIN", "L", 17, 15, 11, 0), (102, "Sebastian Aho", "CAR", "C", 17, 9, 12, 1), (103, "Mikko Rantanen", "DAL", "R", 15, 8, 10, 1),
    (104, "Artturi Lehkonen", "COL", "L", 16, 12, 5, 1), (105, "Miro Heiskanen", "DAL", "D", 15, 3, 8, 1), (100, "Erik Haula", "LAK", "C", 14, 3, 3, 1),
    (101, "Joel Armia", "LAK", "R", 14, 3, 2, 1), (106, "Kaapo Kakko", "SEA", "R", 15, 2, 10, 1), (107, "Teuvo Teräväinen", "CHI", "C", 12, 2, 4, 1),
    (5, "Sandis Vilmanis", "FLA", "R", 16, 4, 3, 0)]
save(f"{STATS}/skater/summary?isAggregate=true&isGame=false&limit=-1&cayenneExp=" + urllib.parse.quote(f"gameTypeId=2 and seasonId={SID}"),
     {"data": [{"playerId": p, "skaterFullName": n, "teamAbbrevs": t, "positionCode": pos, "gamesPlayed": gp, "goals": g, "assists": a, "points": g + a} for p, n, t, pos, gp, g, a, _ in sk]})
save(f"{STATS}/skater/bios?isAggregate=true&isGame=false&limit=-1&cayenneExp=" + urllib.parse.quote(f"gameTypeId=2 and seasonId={SID}"),
     {"data": [{"playerId": p, "skaterFullName": n, "nationalityCode": "FIN" if f else "CAN", "birthCountryCode": "FIN" if f else "CAN", "positionCode": pos} for p, n, t, pos, gp, g, a, f in sk]})
gks = [(200, "Juuse Saros", "NSH", 11, 4, 3, 4, .908, 2.81, 0, 1), (201, "Ukko-Pekka Luukkonen", "BUF", 10, 4, 3, 3, .874, 3.42, 0, 1), (202, "Darcy Kuemper", "LAK", 9, 5, 3, 1, .883, 3.4, 0, 0)]
save(f"{STATS}/goalie/summary?isAggregate=true&isGame=false&limit=-1&cayenneExp=" + urllib.parse.quote(f"gameTypeId=2 and seasonId={SID}"),
     {"data": [{"playerId": p, "goalieFullName": n, "teamAbbrevs": t, "gamesPlayed": gp, "wins": w, "losses": l, "otLosses": o, "savePct": sv, "goalsAgainstAverage": ga, "shutouts": so} for p, n, t, gp, w, l, o, sv, ga, so, _ in gks]})
save(f"{STATS}/goalie/bios?isAggregate=true&isGame=false&limit=-1&cayenneExp=" + urllib.parse.quote(f"gameTypeId=2 and seasonId={SID}"),
     {"data": [{"playerId": p, "goalieFullName": n, "nationalityCode": "FIN" if f else "CAN"} for p, n, *_, f in gks]})
print("fixtures:", len(os.listdir(OUT)))

# YouTube-syöte (NHL:n kanava)
feed = '''<?xml version="1.0" encoding="UTF-8"?><feed xmlns:yt="http://www.youtube.com/xml/schemas/2015" xmlns="http://www.w3.org/2005/Atom">
<entry><yt:videoId>AbCdEfGh123</yt:videoId><title>NHL Highlights | Sharks vs. Kings | November 04, 2026</title></entry>
<entry><yt:videoId>ZyXwVuT9876</yt:videoId><title>NHL Highlights | Flames vs. Kraken | November 04, 2026</title></entry>
<entry><yt:videoId>Other000001</yt:videoId><title>Top Saves from Week 5</title></entry></feed>'''
fname = re.sub(r"[^A-Za-z0-9]+", "_", "www.youtube.com/feeds/videos.xml?channel_id=UCqFMzb-4AUf6WAIbl132QKA").strip("_")[:180] + ".xml"
open(os.path.join(OUT, fname), "w").write(feed)
