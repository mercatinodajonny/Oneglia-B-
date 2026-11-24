#!/usr/bin/env python3
"""FootCore · campionati pubblici.
Legge i Comunicati Ufficiali della LND Liguria (Delegazione di Imperia) e salva, per OGNI
categoria e girone trovati, risultati, programma gare e classifica nella tabella pubblica
`campionati` (visibile a tutti, anche senza account).
Uso: SUPABASE_URL=... SUPABASE_SERVICE_KEY=... python3 scripts/lnd_campionati.py [--dry] [--n 15]"""
import os, re, sys, json, datetime, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lnd_sync import get, pdf_text, comunicati, norm, simile

DRY = "--dry" in sys.argv
QUANTI = int(sys.argv[sys.argv.index("--n") + 1]) if "--n" in sys.argv else 15
DELEGAZIONE = "Imperia"
NON_CATEGORIE = ("RISULTATI", "PROGRAMMA GARE", "CLASSIFICHE", "GIUSTIZIA", "VARIAZIONE", "LOCALIT", "IMPIANTO",
                 "SQUADRA", "SOCIET", "ERRATA", "SETTORE GIOVANILE", "ALLEGATI", "COMUNICAZIONI", "D.P. IMPERIA",
                 "PROVVEDIMENTI", "GARE DEL", "SEGRETERIA", "SOMMARIO", "STAGIONE SPORTIVA")
STOP = re.compile(r"^\s*(GIUSTIZIA SPORTIVA|Si invitano|Allegati|PUBBLICATO ED AFFISSO|CLASSIFICHE|PROGRAMMA GARE|RISULTATI GARE)\s*$")

def bel_nome(s):
    s = re.sub(r"\s+", " ", s.replace("PROVINICIALI", "PROVINCIALI").replace(" - ", " ")).strip()
    return s

def cat_key(s):
    return re.sub(r"[^a-z0-9]+", "-", norm(bel_nome(s)).lower()).strip("-")

def titolo(line):
    """Una riga centrata tutta maiuscola = nome di una categoria."""
    if len(line) - len(line.lstrip()) < 12: return None
    t = line.strip()
    if len(t) < 6 or len(t) > 60 or t != t.upper() or not re.match(r"^[A-Z][A-Z0-9 °’'\-.&/]+$", t): return None
    if any(t.startswith(x) or x in t for x in NON_CATEGORIE): return None
    if re.search(r"\s-\s.+\d", t): return None
    return bel_nome(t)

def blocchi(txt, intestazione):
    """Le parti del comunicato che iniziano con una intestazione centrata (non l'indice)."""
    righe = txt.splitlines(); out = []; dentro = False; cur = []
    for l in righe:
        if re.match(r"^\s{10,}" + intestazione + r"\s*$", l):
            if cur: out.append(cur)
            dentro = True; cur = []; continue
        if dentro and STOP.match(l) and not re.match(r"^\s{10,}" + intestazione + r"\s*$", l):
            out.append(cur); cur = []; dentro = False; continue
        if dentro: cur.append(l)
    if cur: out.append(cur)
    return out

def leggi_risultati(txt):
    out = []
    for righe in blocchi(txt, "RISULTATI GARE"):
        cat = gir = None; giornata = None; data = None
        for l in righe:
            t = titolo(l)
            if t: cat = t; continue
            d = re.search(r"GARE DEL (\d\d)/(\d\d)/(\d{4})", l)
            if d: data = f"{d.group(3)}-{d.group(2)}-{d.group(1)}"; continue
            g = re.search(r"GIRONE\s+[“\"]?([A-Z])[”\"]?\s*-\s*(\d+)\^?\s*GIORNATA", l)
            if g: gir, giornata = g.group(1), int(g.group(2)); continue
            r = re.match(r"^\s*(\*)?\s*(.+?)\s+-\s+(.+?)\s{2,}(\d+)\s*-\s*(\d+)\s*$", l)
            if r and cat and gir and "C.U." not in l:
                out.append({"cat": cat, "girone": gir, "giornata": giornata, "data": data,
                            "casa": r.group(2).strip(), "ospite": r.group(3).strip(), "gc": int(r.group(4)), "go": int(r.group(5))})
    return out

def leggi_programma(txt):
    out = []
    for righe in blocchi(txt, "PROGRAMMA GARE"):
        cat = gir = None; giornata = None
        for i, l in enumerate(righe):
            t = titolo(l)
            if t: cat = t; continue
            g = re.match(r"^\s*GIRONE\s+([A-Z])\s*-\s*(\d+)\s*Giornata", l, re.I)
            if g: gir, giornata = g.group(1).upper(), int(g.group(2)); continue
            m = re.match(r"^\s*(.+?)\s{2,}(.+?)\s{2,}([AR])(\s|$)", l)
            if not m or not cat or not gir or "SQUADRA" in l: continue
            data = ora = None
            for j in (i - 1, i - 2):
                if 0 <= j < len(righe):
                    d = re.search(r"(\d\d)/(\d\d)/(\d{4})", righe[j])
                    if d: data = f"{d.group(3)}-{d.group(2)}-{d.group(1)}"; break
            for j in (i + 1, i + 2):
                if 0 <= j < len(righe):
                    o = re.search(r"\b(\d{1,2}:\d\d)\b", righe[j])
                    if o: ora = o.group(1); break
            out.append({"cat": cat, "girone": gir, "giornata": giornata, "casa": m.group(1).strip(), "ospite": m.group(2).strip(), "data": data, "ora": ora})
    return out

def leggi_classifiche(txt):
    out = {}
    for righe in blocchi(txt, "CLASSIFICHE"):
        cat = None; gir = "A"
        for l in righe:
            t = titolo(l)
            if t: cat = t; gir = "A"; continue
            g = re.match(r"^\s*GIRONE\s+[“\"]?([A-Z])[”\"]?\s*$", l)
            if g: gir = g.group(1); continue
            r = re.match(r"^\s*(\d+)\s+(.+?)\s{2,}(-?\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(-?\d+)\s+(-?\d+)\s*$", l)
            if r and cat:
                pos, sq, pt, g_, v, n, p, gf, gs, dr, pen = r.groups()
                out.setdefault((cat, gir), []).append({"pos": int(pos), "squadra": sq.strip(), "pt": int(pt), "g": int(g_), "v": int(v), "n": int(n),
                                                       "p": int(p), "gf": int(gf), "gs": int(gs), "dr": int(dr), "pen": int(pen)})
    return out

def titolo_squadra(s):
    s = " ".join(w[:1].upper() + w[1:].lower() for w in s.replace("’", "'").split())
    s = re.sub(r"\bA\.s\.d\.?", "A.S.D.", s)
    return re.sub(r"\b(Asd|A\.S\.D\.|Ssd|Sq\.B|Sq\. B)\b", lambda m: {"Asd": "ASD", "A.S.D.": "A.S.D.", "Ssd": "SSD"}.get(m.group(1), "Sq. B"), s)

def main():
    lista = comunicati()[:QUANTI]
    letti = []
    for n, page in lista:
        html = get(page)
        pdfs = [u for u in re.findall(r'href="([^"]+\.pdf)"', html) if "C.U." in u or "cu-" in u.lower()]
        if not pdfs: continue
        txt = pdf_text(get(pdfs[0], True))
        dm = re.search(r"C\.U\. ?\d+ - (\d\d)/(\d\d)/(\d\d)", txt)
        letti.append({"n": n, "pdf": pdfs[0], "data": f"20{dm.group(3)}-{dm.group(2)}-{dm.group(1)}" if dm else None,
                      "ris": leggi_risultati(txt), "prog": leggi_programma(txt), "cl": leggi_classifiche(txt)})
    print("Comunicati letti:", [c["n"] for c in letti])
    camp = {}
    def C(cat, gir):
        k = f"{cat_key(cat)}-{gir.lower()}"
        return camp.setdefault(k, {"id": k, "categoria": cat.title().replace("U1", "U1").replace("Fase Provinciale", "fase provinciale"),
                                   "girone": gir, "risultati": {}, "programma": {}, "classifica": None, "cu": None, "aggiornato": None})
    for c in reversed(letti):  # dal più vecchio al più nuovo: i più recenti vincono
        for r in c["ris"]:
            x = C(r["cat"], r["girone"]); x["risultati"][(norm(r["casa"]), norm(r["ospite"]))] = r
            x["cu"], x["aggiornato"] = c["n"], c["data"]
        for p in c["prog"]:
            x = C(p["cat"], p["girone"]); x["programma"][(norm(p["casa"]), norm(p["ospite"]))] = p
            x["cu"], x["aggiornato"] = c["n"], c["data"]
        for (cat, gir), righe in c["cl"].items():
            x = C(cat, gir); x["classifica"] = {"righe": [{**r, "squadra": titolo_squadra(r["squadra"])} for r in righe], "cu": c["n"], "aggiornata": c["data"]}
    righe_db = []
    stagione = None
    for x in camp.values():
        ris = sorted(x["risultati"].values(), key=lambda r: (r["giornata"] or 0, r["casa"]))
        giocate = list(x["risultati"].keys())
        oggi = datetime.date.today().isoformat()
        limite = (datetime.date.today() - datetime.timedelta(days=7)).isoformat()
        def gia_giocata(k, p):
            if k in x["risultati"]: return True
            if any(simile(c, k[0]) and simile(o, k[1]) for c, o in giocate): return True
            return bool(p.get("data")) and p["data"] < limite
        prog = sorted([p for k, p in x["programma"].items() if not gia_giocata(k, p)], key=lambda p: (p["giornata"] or 0, p["data"] or "", p["casa"]))
        dati = {"classifica": x["classifica"],
                "risultati": [{k: v for k, v in r.items() if k not in ("cat",)} | {"casa": titolo_squadra(r["casa"]), "ospite": titolo_squadra(r["ospite"])} for r in ris],
                "programma": [{k: v for k, v in p.items() if k not in ("cat",)} | {"casa": titolo_squadra(p["casa"]), "ospite": titolo_squadra(p["ospite"])} for p in prog],
                "fonte": "Comunicati Ufficiali LND Liguria – Delegazione di Imperia", "cu": x["cu"]}
        if not (dati["risultati"] or dati["programma"] or dati["classifica"]): continue
        righe_db.append({"id": x["id"], "delegazione": DELEGAZIONE, "categoria": x["categoria"], "girone": x["girone"],
                         "dati": dati, "aggiornato": x["aggiornato"], "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat()})
        print(f"  {x['id']}: {len(dati['risultati'])} risultati, {len(dati['programma'])} in programma, classifica {'sì' if x['classifica'] else 'no'}")
    if DRY:
        json.dump(righe_db, open("/tmp/campionati.json", "w"), ensure_ascii=False, indent=1); print("[dry] salvato /tmp/campionati.json"); return
    key = os.environ.get("SUPABASE_SERVICE_KEY", "")
    if not key: print("Manca SUPABASE_SERVICE_KEY"); sys.exit(1)
    url = os.environ.get("SUPABASE_URL", "https://xgsmvirezubvgpqcfxjp.supabase.co").rstrip("/") + "/rest/v1/campionati?on_conflict=id"
    h = {"apikey": key, "Authorization": "Bearer " + key, "Content-Type": "application/json", "Prefer": "resolution=merge-duplicates"}
    urllib.request.urlopen(urllib.request.Request(url, data=json.dumps(righe_db).encode(), headers=h, method="POST"), timeout=60)
    print(f"Campionati salvati: {len(righe_db)}")

if __name__ == "__main__":
    main()
