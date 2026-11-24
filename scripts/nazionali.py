#!/usr/bin/env python3
"""Serie A, Serie B (ESPN, dati pubblici) e Serie C (Wikipedia) -> data/nazionali.json.

Stesso formato di data/campionati.json, così l'app li mostra come gli altri campionati.
Uso: python3 scripts/nazionali.py --out data/nazionali.json
"""
import argparse, datetime as dt, gzip, json, re, sys, time, urllib.request
from zoneinfo import ZoneInfo

UA = "GolazoApp/0.1 (https://mercatinodajonny.github.io/Oneglia-B-/; officialmercatinodajonny@gmail.com)"
ROMA = ZoneInfo("Europe/Rome")


def get(url, tries=4):
    for i in range(tries):
        try:
            r = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "gzip"}), timeout=40)
            b = r.read()
            if r.headers.get("Content-Encoding") == "gzip" or b[:2] == b"\x1f\x8b":
                b = gzip.decompress(b)
            return b.decode("utf-8")
        except Exception as e:  # rete instabile o limite di richieste
            print("  riprovo", url[:80], e, file=sys.stderr)
            time.sleep(6 * (i + 1))
    raise RuntimeError("impossibile scaricare " + url)


def stagione_oggi():
    o = dt.date.today()
    a = o.year if o.month >= 7 else o.year - 1
    return a


# ---------------------------------------------------------------- ESPN (A e B)
def espn(lega, categoria, sid):
    a = stagione_oggi()
    st = json.loads(get(f"https://site.api.espn.com/apis/v2/sports/soccer/{lega}/standings"))
    ent = st["children"][0]["standings"]["entries"]
    loghi, colori, righe = {}, {}, []
    for e in ent:
        t = e["team"]; n = t["displayName"]
        s = {x["name"]: x.get("value") for x in e["stats"]}
        if t.get("logos"): loghi[n] = t["logos"][0]["href"]
        righe.append({"squadra": n, "pt": int(s.get("points") or 0), "g": int(s.get("gamesPlayed") or 0),
                      "v": int(s.get("wins") or 0), "n": int(s.get("ties") or 0), "p": int(s.get("losses") or 0),
                      "gf": int(s.get("pointsFor") or 0), "gs": int(s.get("pointsAgainst") or 0),
                      "dr": int(s.get("pointDifferential") or 0), "rank": int(s.get("rank") or 0)})
    righe.sort(key=lambda r: (r["rank"] or 99, -r["pt"]))
    for i, r in enumerate(righe, 1):
        r["pos"] = i; r.pop("rank", None)
    ev = []
    for anno in (a, a + 1):
        d = json.loads(get(f"https://site.api.espn.com/apis/site/v2/sports/soccer/{lega}/scoreboard?dates={anno}&limit=1000"))
        ev += d.get("events", [])
        time.sleep(1)
    partite, visti = [], set()
    for e in ev:
        if e["id"] in visti: continue
        visti.add(e["id"])
        se = e.get("season") or {}; slug = str(se.get("slug", ""))
        if not (slug.startswith(f"{a}-{str(a + 1)[2:]}") or (slug == "regular-season" and e["date"][:10] >= f"{a}-07-01" and e["date"][:10] < f"{a + 1}-07-01")): continue
        c = e["competitions"][0]
        h = next(x for x in c["competitors"] if x["homeAway"] == "home")
        o = next(x for x in c["competitors"] if x["homeAway"] == "away")
        for x in (h, o):
            tm = x["team"]
            if tm.get("logo"): loghi.setdefault(tm["displayName"], tm["logo"])
            if tm.get("color"): colori[tm["displayName"]] = "#" + tm["color"]
        t = dt.datetime.fromisoformat(e["date"].replace("Z", "+00:00")).astimezone(ROMA)
        m = {"data": t.strftime("%Y-%m-%d"), "ora": t.strftime("%H:%M"), "casa": h["team"]["displayName"], "ospite": o["team"]["displayName"]}
        stt = c["status"]["type"]
        if stt.get("completed"):
            m["gc"], m["go"] = int(h.get("score") or 0), int(o.get("score") or 0)
        elif stt.get("name") in ("STATUS_POSTPONED", "STATUS_CANCELED"):
            m["rinviata"] = True
        partite.append(m)
    partite.sort(key=lambda m: (m["data"], m["ora"]))
    # giornata: la n-esima partita della squadra di casa (la Lega non la espone qui)
    cnt = {}
    for m in partite:
        k = max(cnt.get(m["casa"], 0), cnt.get(m["ospite"], 0)) + 1
        cnt[m["casa"]] = cnt[m["ospite"]] = k
        m["giornata"] = k
    ris = [m for m in partite if "gc" in m]
    prog = [m for m in partite if "gc" not in m]
    return {"id": sid, "categoria": categoria, "girone": "Unico", "delegazione": "Nazionale",
            "stagione": f"{a}/{a + 1}", "aggiornato": dt.date.today().isoformat(),
            "dati": {"classifica": {"righe": righe}, "risultati": ris, "programma": prog,
                     "loghi": loghi, "colori": colori, "fonte": "ESPN (dati pubblici)"}}


# ------------------------------------------------------- Wikipedia (Serie C)
def pulisci(s):
    s = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]*)\]\]", r"\1", s)
    s = re.sub(r"\{\{[^{}]*\}\}", "", s)
    s = re.sub(r"<[^>]+>", "", s)
    s = re.sub(r"'{2,}", "", s)
    return s.strip()


def serie_c():
    a = stagione_oggi()
    txt = get(f"https://it.wikipedia.org/w/index.php?title=Serie_C_{a}-{a + 1}&action=raw")
    out = []
    gir = re.split(r"\n== *Girone ([ABC]) *==", txt)
    for i in range(1, len(gir), 2):
        g, corpo = gir[i], gir[i + 1]
        righe = []
        cl = re.search(r"=== *Classifica *===(.*?)\n\|\}", corpo, re.S)
        if cl:
            for row in cl.group(1).split("\n|-")[1:]:
                mn = re.search(r'text-align: *left;?" *\|([^\n]*)', row)
                if not mn: continue
                raw = mn.group(1).strip()
                t = re.search(r"\{\{Calcio ([^}|]+)", raw)
                nome = (t.group(1) if t else pulisci(raw)).strip()
                mp = re.search(r"\|\|\s*(\d+)\.?\s*\|\|", row)
                resto = row[mn.end():]
                n = [int(x.replace("−", "-").replace("+", "")) for x in re.findall(r"[+\-−]?\d+", re.sub(r"\{\{[^}]*\}\}", "", resto))]
                if nome and len(n) >= 8:
                    pt, gg, v, nn, p_, gf, gs = n[:7]
                    righe.append({"pos": int(mp.group(1)) if mp else len(righe) + 1, "squadra": nome, "pt": pt, "g": gg, "v": v, "n": nn, "p": p_, "gf": gf, "gs": gs, "dr": gf - gs})
        ris = []
        tb = re.search(r"==== *Tabellone *====(.*?)\n\|\}", corpo, re.S)
        if tb:
            righe_t = tb.group(1).split("\n|-")
            for row in righe_t[1:]:
                m = re.search(r'text-align: *left;?" *\|([^\n|]+)', row)
                if not m: continue
                casa = pulisci(m.group(1))
                vals = re.split(r"\|\|", row[m.end():])
                vals = [pulisci(v.split("|")[-1]) for v in vals]
                vals = [v for v in vals if v != ""]
                # le colonne seguono l'ordine alfabetico delle squadre nelle righe
                ris.append((casa, vals))
            nomi = [r[0] for r in ris]
            partite = []
            for casa, vals in ris:
                vals = [v for v in vals if v not in ("––––", "–––", "—")] if len(vals) > len(nomi) - 1 else vals
                altri = [x for x in nomi if x != casa]
                for osp, v in zip(altri, vals):
                    mm = re.fullmatch(r"(\d+)-(\d+)", v)
                    if mm:
                        partite.append({"casa": casa, "ospite": osp, "gc": int(mm.group(1)), "go": int(mm.group(2)), "data": ""})
            ris = partite
        if righe:
            cl = [r["squadra"] for r in righe]
            k = lambda x: re.sub(r"[^a-z0-9]", "", x.lower())
            def allinea(n):
                if n in cl: return n
                for c in cl:
                    if k(c) == k(n) or k(c) in k(n) or k(n) in k(c): return c
                tok = {w for w in re.findall(r"[a-z]{4,}", n.lower())}
                for c in cl:
                    if tok & set(re.findall(r"[a-z]{4,}", c.lower())): return c
                return n
            for m in ris:
                m["casa"], m["ospite"] = allinea(m["casa"]), allinea(m["ospite"])
            # allinea i nomi del tabellone a quelli della classifica (es. "Alcione " con spazio)
            out.append({"id": f"serie-c-{g.lower()}", "categoria": "Serie C", "girone": g, "delegazione": "Nazionale",
                        "stagione": f"{a}/{a + 1}", "aggiornato": dt.date.today().isoformat(),
                        "dati": {"classifica": {"righe": righe}, "risultati": ris, "programma": [],
                                 "fonte": "Wikipedia (Serie C " + f"{a}-{a + 1})"}})
    return out


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--out", default="data/nazionali.json"); a = ap.parse_args()
    camp = []
    for lega, cat, sid in (("ita.1", "Serie A", "serie-a"), ("ita.2", "Serie B", "serie-b")):
        try:
            camp.append(espn(lega, cat, sid)); print(cat, "ok")
        except Exception as e:
            print(cat, "ERRORE", e, file=sys.stderr)
    try:
        c = serie_c(); camp += c; print("Serie C gironi", len(c))
    except Exception as e:
        print("Serie C ERRORE", e, file=sys.stderr)
    if not camp:
        sys.exit("nessun dato")
    # non perdere un campionato se oggi la fonte non risponde
    try:
        vecchio = {c["id"]: c for c in json.load(open(a.out))["campionati"]}
        nuovi = {c["id"] for c in camp}
        camp += [c for k, c in vecchio.items() if k not in nuovi]
    except Exception:
        pass
    json.dump({"aggiornato": dt.datetime.now(ROMA).isoformat(timespec="minutes"), "campionati": camp},
              open(a.out, "w"), ensure_ascii=False, separators=(",", ":"))
    print("scritto", a.out, len(camp))


if __name__ == "__main__":
    main()
