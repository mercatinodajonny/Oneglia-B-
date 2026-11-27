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
QUANTI = int(sys.argv[sys.argv.index("--n") + 1]) if "--n" in sys.argv else 60
DELEGAZIONE = "Imperia"
# Tutti gli enti della LND Liguria che pubblicano comunicati: (slug pagina, nome, prefisso id)
AREE = [("dp-imperia", "Imperia", ""), ("cr-liguria", "Liguria (regionale)", "reg-"), ("dp-savona", "Savona", "sv-"),
        ("dp-genova", "Genova", "ge-"), ("dp-chiavari", "Chiavari", "chi-"), ("dp-la-spezia", "La Spezia", "sp-"),
        ("seried", "Serie D (Dipartimento Interregionale)", "sd-")]
SOLO = [a for a in AREE if ("--area" not in sys.argv or a[0] == sys.argv[sys.argv.index("--area") + 1])]
NON_CATEGORIE = ("RISULTATI", "PROGRAMMA GARE", "CLASSIFICHE", "GIUSTIZIA", "VARIAZIONE", "LOCALIT", "IMPIANTO",
                 "SQUADRA", "SOCIET", "ERRATA", "SETTORE GIOVANILE", "ALLEGATI", "COMUNICAZIONI", "D.P. IMPERIA",
                 "PROVVEDIMENTI", "GARE DEL", "SEGRETERIA", "SOMMARIO", "STAGIONE SPORTIVA")
STOP = re.compile(r"^\s*(GIUSTIZIA SPORTIVA|Si invitano|Allegati|PUBBLICATO ED AFFISSO|CLASSIFICHE|PROGRAMMA GARE|ORARIO GARE|RISULTATI GARE)\s*$")

def bel_nome(s):
    s = re.sub(r"\s+", " ", s.replace("PROVINICIALI", "PROVINCIALI").replace(" - ", " ")).strip()
    return s

def cat_key(s):
    return re.sub(r"[^a-z0-9]+", "-", norm(bel_nome(s)).lower()).strip("-")

def titolo(line):
    """Una riga centrata tutta maiuscola = nome di una categoria."""
    if len(line) - len(line.lstrip()) < 6: return None
    t = re.sub(r"^\([A-Z0-9]{1,3}\)\s*[–-]\s*", "", line.strip()).replace("‘", "'").replace("’", "'")
    if len(t) < 6 or len(t) > 60 or t != t.upper() or not re.match(r"^[A-Z][A-Z0-9 °’'\-.&/]+$", t): return None
    if any(t.startswith(x) or x in t for x in NON_CATEGORIE): return None
    if re.search(r"\s-\s.+\d", t): return None
    if not re.search(r"CATEGORIA|ECCELLENZA|PROMOZIONE|JUNIORES|ALLIEVI|GIOVANISSIMI|ESORDIENTI|PULCINI|UNDER|U1\d|SERIE [A-D]|FEMMINIL|CALCIO A 5|COPPA|TORNEO|AMATORI", t): return None
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
    for righe in [txt.splitlines()]:  # tutto il comunicato: i risultati stanno dopo "RISULTATI UFFICIALI GARE DEL"
        cat = gir = None; giornata = None; data = None; colonne = None; ok = False
        for l in righe:
            t = titolo(l)
            if t: cat = t; colonne = None; ok = False; gir = None; continue
            d = re.search(r"GARE DEL (\d\d)/\s?(\d{1,2})/(\d{4})", l)
            if d: data = f"{d.group(3)}-{int(d.group(2)):02d}-{d.group(1)}"; ok = "RISULTATI" in l.upper(); continue
            if not ok: continue
            # comunicati regionali: due gironi affiancati in colonne ("GIRONE A - 9 Giornata - A    GIRONE B - 9 Giornata - A")
            cols = [(m.start(), m.group(1), int(m.group(2)), m.group(3).upper()) for m in
                    re.finditer(r"GIRONE\s+([A-Z]{1,2})\s*-\s*(\d+)\s*Giornata\s*-\s*([AR])", l, re.I)]
            if cols: colonne = cols; gir = cols[0][1]; giornata = cols[0][2]; continue
            if colonne and cat:
                trovate = list(re.finditer(r"(?:\(\d+\)\s+)?(?P<c>[^\s(][^ ]*(?: [^ ]+)*?)\s+-\s+(?P<o>\S+(?: \S+)*?)\s+(?P<a>\d+)\s?-\s?(?P<b>\d+)(?=\s{2,}|\s*$)", l))
                for m in trovate:
                    col = min(colonne, key=lambda c: abs(c[0] - m.start()))
                    out.append({"cat": cat, "girone": col[1], "giornata": col[2] + (0 if col[3] == "A" else 100), "data": data,
                                "casa": m.group("c").strip(), "ospite": m.group("o").strip(), "gc": int(m.group("a")), "go": int(m.group("b"))})
                if trovate: continue
            g = re.search(r"GIRONE\s+[“\"]?([A-Z])[”\"]?\s*-\s*(\d+)\^?\s*GIORNATA", l)
            if g: gir, giornata = g.group(1), int(g.group(2)); colonne = None; continue
            r = re.match(r"^\s*(\*)?\s*(.+?)\s+-\s+(.+?)\s{2,}(\d+)\s*-\s*(\d+)\s*$", l)
            if r and cat and gir and "C.U." not in l:
                out.append({"cat": cat, "girone": gir, "giornata": giornata, "data": data,
                            "casa": r.group(2).strip(), "ospite": r.group(3).strip(), "gc": int(r.group(4)), "go": int(r.group(5))})
    return out

def leggi_programma(txt):
    out = []
    for righe in blocchi(txt, "PROGRAMMA GARE") + blocchi(txt, "ORARIO GARE"):
        cat = gir = None; giornata = None
        for i, l in enumerate(righe):
            t = titolo(l)
            if t: cat = t; continue
            g = re.match(r"^\s*GIRONE\s+([A-Z]{1,2})\s*-\s*(\d+)\s*Giornata", l, re.I)
            if g: gir, giornata = g.group(1).upper(), int(g.group(2)); continue
            m = re.match(r"^\s*(\S+(?: \S+)*)\s{2,}(\S+(?: \S+)*)\s{2,}([AR])(?:\s|$)", l)
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

STAGIONE_INIZIO = "2026-07-01"

def tutti_i_comunicati(area="dp-imperia"):
    """Comunicati della stagione, anche dalle pagine precedenti dell'elenco."""
    LIST = f"https://www.lndliguria.it/area-comunicati/{area}/"
    visti, out = set(), []
    for pag in range(1, 6):
        url = LIST if pag == 1 else LIST + f"page/{pag}/"
        try: html = get(url)
        except Exception: break
        nuovi = [(u, n) for u, n in re.findall(r'href="(https://www\.lndliguria\.it/comunicati-ufficiali/c-?u-(\d+)[-/][^"]*)"', html)]
        if not nuovi: break
        for u, n in nuovi:
            if u in visti: continue
            visti.add(u); out.append((int(n), u))
    return out  # nell'ordine dell'elenco: dal più recente

def main():
    tutte = []
    for area, nome, pref in SOLO:
        global DELEGAZIONE
        DELEGAZIONE = nome
        print(f"== {nome}")
        try: tutte += leggi_area(area, nome, pref)
        except Exception as e: print("  errore:", e)
    salva(tutte)

def leggi_classifiche_seried(txt):
    """Serie D: righe 'SQUADRA  PT G V N P GF GS DR PE' senza posizione, sotto 'CLASSIFICA' / 'GIRONE X'."""
    out = {}; dentro = False; gir = None
    for l in txt.splitlines():
        if re.match(r"^\s*CLASSIFICA\s*$", l): dentro = True; continue
        if not dentro: continue
        g = re.match(r"^\s*GIRONE\s+([A-Z])\s*$", l)
        if g: gir = g.group(1); continue
        r = re.match(r"^\s*(\S+(?: \S+)*)\s{2,}(-?\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(-?\d+)\s+(-?\d+)\s*$", l)
        if r and gir:
            sq, pt, g_, v, n, p, gf, gs, dr, pen = r.groups()
            rows = out.setdefault(("SERIE D", gir), [])
            rows.append({"pos": len(rows) + 1, "squadra": re.sub(r"^(A\.?S\.?D\.?C?|S\.?S\.?D\.?|U\.?S\.?D?\.?|S\.?C\.?D\.?|ACS\.?D\.?|ASDC|SSDARL|ASD|U\.S\.D\.)\s+", "", sq.strip()),
                         "pt": int(pt), "g": int(g_), "v": int(v), "n": int(n), "p": int(p), "gf": int(gf), "gs": int(gs), "dr": int(dr), "pen": int(pen)})
        elif re.match(r"^\s*(Pag\.|PROGRAMMA|Variazioni)", l) and out: dentro = False
    return out

def leggi_seried(nome_area, pref, gironi=("A",)):
    """Serie D: comunicati del Dipartimento Interregionale (risultati dal Giudice Sportivo, classifica dalle Comunicazioni)."""
    # tutte le pagine dei comunicati della stagione in corso: servono tutti i Giudice Sportivo (risultati dalla 1ª giornata)
    stag = f"{STAGIONE_INIZIO[:4]}/{int(STAGIONE_INIZIO[:4]) + 1}" if "STAGIONE_INIZIO" in globals() else None
    pdfs = []
    for pag in range(1, 16):
        try: html = get("https://lnd.it/seried/comunicati/" + (f"page/{pag}/" if pag > 1 else ""))
        except Exception: break
        trov = list(dict.fromkeys(re.findall(r'href="(https://comunicati\.lnd\.it/storage/comunicati/[^"]+?\.pdf)"', html)))
        if not trov: break
        if stag and not any(f"/{stag}/" in u for u in trov): break
        pdfs += [u for u in trov if u not in pdfs and (not stag or f"/{stag}/" in u)]
    gs = [u for u in pdfs if re.search(r"Giudice_Sportivo_Serie_D", u, re.I)]
    cl = [u for u in pdfs if re.search(r"classifica", u, re.I)][:2]
    pdfs = gs + cl
    camp = {}
    for u in reversed(pdfs):
        try: txt = pdf_text(get(u, True))
        except Exception: continue
        dm = re.search(r"(\d\d)/(\d\d)/(20\d\d)", txt); data = f"{dm.group(3)}-{dm.group(2)}-{dm.group(1)}" if dm else None
        for r in leggi_risultati(txt):
            if r["cat"] != "SERIE D" or r["girone"] not in gironi: continue
            x = camp.setdefault(r["girone"], {"ris": {}, "cl": None, "agg": None})
            x["ris"][(norm(r["casa"]), norm(r["ospite"]))] = r; x["agg"] = data
        for (cat, gir), righe in leggi_classifiche_seried(txt).items():
            if gir in gironi:
                camp.setdefault(gir, {"ris": {}, "cl": None, "agg": None})["cl"] = {"righe": [{**r, "squadra": titolo_squadra(r["squadra"])} for r in righe], "aggiornata": data}
    out = []
    for gir, x in camp.items():
        ris = sorted(x["ris"].values(), key=lambda r: (r["giornata"] or 0, r["casa"]))
        dati = {"classifica": x["cl"], "programma": [], "cu": None,
                "risultati": [{k: v for k, v in r.items() if k != "cat"} | {"casa": titolo_squadra(r["casa"]), "ospite": titolo_squadra(r["ospite"])} for r in ris],
                "fonte": "Comunicati Ufficiali LND – Dipartimento Interregionale"}
        out.append({"id": f"{pref}serie-d-{gir.lower()}", "delegazione": nome_area, "categoria": "Serie D", "girone": gir,
                    "dati": dati, "aggiornato": x["agg"], "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat()})
        print(f"  {pref}serie-d-{gir.lower()}: {len(ris)} risultati, classifica {'sì' if x['cl'] else 'no'}")
    return out

def leggi_area(area, nome_area, pref):
    if area == "seried": return leggi_seried(nome_area, pref)
    lista = tutti_i_comunicati(area)[:QUANTI]
    letti = []
    prec = None
    for n, page in lista:
        if prec is not None and n > prec: break  # numerazione ricominciata: stagione precedente
        prec = n
        html = get(page)
        pdfs = [u for u in re.findall(r'href="([^"]+\.pdf)"', html) if re.search(r"c\.?\s?-?u\.?|comunicato", u, re.I)]
        if not pdfs: continue
        txt = pdf_text(get(pdfs[0], True))
        dm = re.search(r"C\.U\. ?(?:N\.?\s*)?\d+\s*[-–]\s*(\d\d)/(\d\d)/(\d\d)", txt)
        if dm and f"20{dm.group(3)}-{dm.group(2)}-{dm.group(1)}" < STAGIONE_INIZIO: break  # stagione precedente: fine
        dm = dm or re.search(r"(\d\d)/(\d\d)/20(\d\d)", txt)
        letti.append({"n": n, "pdf": pdfs[0], "data": f"20{dm.group(3)}-{dm.group(2)}-{dm.group(1)}" if dm else None,
                      "ris": leggi_risultati(txt), "prog": leggi_programma(txt), "cl": leggi_classifiche(txt)})
    print("Comunicati letti:", [c["n"] for c in letti])
    camp = {}
    def C(cat, gir):
        k = f"{pref}{cat_key(cat)}-{gir.lower()}"
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
        tutto_prog = list(x["programma"].items())
        for k, r in x["risultati"].items():
            p = x["programma"].get(k) or next((v for (c, o), v in tutto_prog if simile(c, k[0]) and simile(o, k[1])), None)
            if p and p.get("giornata"): r["giornata"] = p["giornata"]
        ris = sorted(x["risultati"].values(), key=lambda r: (r["giornata"] or 0, r["casa"]))
        giocate = list(x["risultati"].keys())
        oggi = datetime.date.today().isoformat()
        limite = (datetime.date.today() - datetime.timedelta(days=7)).isoformat()
        def gia_giocata(k, p):
            if k in x["risultati"]: return True
            if any(simile(c, k[0]) and simile(o, k[1]) for c, o in giocate): return True
            return bool(p.get("data")) and p["data"] < limite
        prog = sorted([p for k, p in x["programma"].items() if not gia_giocata(k, p)], key=lambda p: (p["giornata"] or 0, p["data"] or "", p["casa"]))
        if not x["classifica"] and len(ris) >= 4 and not re.search(r"coppa|torneo|fase finale|play", x["categoria"], re.I):
            tab = {}
            for r in ris:
                for sq, f, s_ in ((r["casa"], r["gc"], r["go"]), (r["ospite"], r["go"], r["gc"])):
                    t = tab.setdefault(norm(sq), {"squadra": titolo_squadra(sq), "pt": 0, "g": 0, "v": 0, "n": 0, "p": 0, "gf": 0, "gs": 0})
                    t["g"] += 1; t["gf"] += f; t["gs"] += s_
                    if f > s_: t["v"] += 1; t["pt"] += 3
                    elif f == s_: t["n"] += 1; t["pt"] += 1
                    else: t["p"] += 1
            righe_cl = sorted(tab.values(), key=lambda t: (-t["pt"], -(t["gf"] - t["gs"]), -t["gf"], t["squadra"]))
            for i, t in enumerate(righe_cl, 1): t.update(pos=i, dr=t["gf"] - t["gs"], pen=0)
            x["classifica"] = {"righe": righe_cl, "cu": x["cu"], "aggiornata": x["aggiornato"], "calcolata": True}
        dati = {"classifica": x["classifica"],
                "risultati": [{k: v for k, v in r.items() if k not in ("cat",)} | {"casa": titolo_squadra(r["casa"]), "ospite": titolo_squadra(r["ospite"])} for r in ris],
                "programma": [{k: v for k, v in p.items() if k not in ("cat",)} | {"casa": titolo_squadra(p["casa"]), "ospite": titolo_squadra(p["ospite"])} for p in prog],
                "fonte": "Comunicati Ufficiali LND Liguria – " + (nome_area if "regionale" in nome_area else "Delegazione di " + nome_area), "cu": x["cu"]}
        if not dati["classifica"] and len(dati["risultati"]) < 2: continue
        if pref and pref != "reg-" and re.search(r"eccellenza|promozione|prima categoria|regional|femminil|coppa italia", x["categoria"], re.I): continue
        righe_db.append({"id": x["id"], "delegazione": nome_area, "categoria": x["categoria"], "girone": x["girone"],
                         "dati": dati, "aggiornato": x["aggiornato"], "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat()})
        print(f"  {x['id']}: {len(dati['risultati'])} risultati, {len(dati['programma'])} in programma, classifica {'sì' if x['classifica'] else 'no'}")
    return righe_db

def salva(righe_db):
    if "--out" in sys.argv:
        dest = sys.argv[sys.argv.index("--out") + 1]
        os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
        json.dump({"aggiornato": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%MZ"), "campionati": righe_db},
                  open(dest, "w"), ensure_ascii=False, separators=(",", ":"))
        print("Salvato", dest); return
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
