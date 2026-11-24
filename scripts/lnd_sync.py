#!/usr/bin/env python3
"""Sincronizza risultati, classifica e calendario della Seconda Categoria (girone A, Imperia)
dai Comunicati Ufficiali pubblici della LND Liguria verso il database dell'app.
Uso: SUPABASE_URL=... SUPABASE_SERVICE_KEY=... python3 scripts/lnd_sync.py [--dry]"""
import os, re, sys, json, subprocess, tempfile, unicodedata, urllib.request, datetime

BASE = "https://www.lndliguria.it"
LIST = BASE + "/area-comunicati/dp-imperia/"
CATEGORIA = "SECONDA CATEGORIA"
NOI = "ONEGLIA CALCIO"
UA = {"User-Agent": "OnegliaSqB-app/1.0 (+https://mercatinodajonny.github.io/Oneglia-B-/)"}
DRY = "--dry" in sys.argv

def get(url, binary=False):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read()
    return data if binary else data.decode("utf-8", "replace")

def norm(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().upper()
    s = re.sub(r"[’'`.,]", "", s)
    s = re.sub(r"\b(ASD|A S D|SSD|SRL|SQ B|CALCIO|SPORT|1\d{3}|20\d\d)\b", " ", s)
    return re.sub(r"\s+", " ", s).strip()

def simile(a, b):
    """True se due nomi di squadra (già normalizzati) indicano la stessa società."""
    if not a or not b: return False
    if a == b or a in b or b in a: return True
    ta, tb = a.split(), b.split()
    if len(ta) > len(tb): ta, tb = tb, ta
    ok = sum(1 for t in ta if any(u.startswith(t) or t.startswith(u) for u in tb))
    return ok == len(ta) and ok >= 2

def pdf_text(data):
    with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
        f.write(data); f.flush()
        return subprocess.run(["pdftotext", "-layout", f.name, "-"], capture_output=True, text=True).stdout

def comunicati():
    """Elenco (numero, url pagina) dei comunicati della delegazione, dal più recente."""
    html = get(LIST)
    pages = sorted(set(re.findall(r'href="(https://www\.lndliguria\.it/comunicati-ufficiali/cu-(\d+)-[^"]*?im[^"]*)"', html)), key=lambda x: -int(x[1]))
    return [(int(n), u) for u, n in pages]

def section(txt, start_pat, stop_pats):
    m = re.search(start_pat, txt)
    if not m: return ""
    rest = txt[m.end():]
    end = len(rest)
    for p in stop_pats:
        k = re.search(p, rest)
        if k: end = min(end, k.start())
    return rest[:end]

SECT_HEAD = r"\n\s{10,}[A-Z][A-Z0-9 °’'\-]{6,}\n"  # titolo centrato di una nuova categoria

def parse_risultati(txt):
    out = []
    for blk in re.finditer(r"RISULTATI GARE\s*\n\s*" + CATEGORIA, txt):
        part = txt[blk.end():]
        stop = re.search(r"\n\s{20,}(ALLIEVI|GIOVANISSIMI|ESORDIENTI|PULCINI|JUNIORES|PRIMA CATEGORIA|TERZA CATEGORIA|CALCIO A 5|GIUDICE|PROVVEDIMENTI)", part)
        part = part[:stop.start()] if stop else part[:6000]
        giornata, data_def = None, None
        for line in part.splitlines():
            d = re.search(r"GARE DEL (\d\d)/(\d\d)/(\d{4})", line)
            if d: data_def = f"{d.group(3)}-{d.group(2)}-{d.group(1)}"
            g = re.search(r"GIRONE\s+“?\"?A”?\"?\s*-\s*(\d+)\^?\s*GIORNATA\s*-\s*(ANDATA|RITORNO)", line)
            if g: giornata = int(g.group(1)); fase = g.group(2); continue
            r = re.match(r"^\s*(\*)?\s*(.+?)\s+-\s+(.+?)\s{2,}(\d+)\s*-\s*(\d+)\s*$", line)
            if r and giornata:
                out.append({"giornata": giornata, "casa": r.group(2).strip(), "ospite": r.group(3).strip(),
                            "gc": int(r.group(4)), "go": int(r.group(5)), "data": data_def, "anticipo": bool(r.group(1))})
    return out

def parse_classifica(txt):
    sec = section(txt, r"CLASSIFICHE\s*\n\s*" + CATEGORIA, [r"\n\s{20,}[A-Z]{4,}[A-Z0-9 ]*\n\s*\n\s*N°"])
    righe = []
    for line in sec.splitlines():
        r = re.match(r"^\s*(\d+)\s+(.+?)\s{2,}(-?\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(-?\d+)\s+(-?\d+)\s*$", line)
        if r:
            pos, sq, pt, g, v, n, p, gf, gs, dr, pen = r.groups()
            righe.append({"pos": int(pos), "squadra": sq.strip(), "pt": int(pt), "g": int(g), "v": int(v), "n": int(n),
                          "p": int(p), "gf": int(gf), "gs": int(gs), "dr": int(dr), "pen": int(pen)})
        elif righe and re.match(r"^\s*$", line) is None and not re.match(r"^\s*\d", line) and "SOCIET" not in line:
            if len(righe) > 3: break
    return righe

def parse_programma(txt):
    out = []
    for blk in re.finditer(r"PROGRAMMA GARE\s*\n\s*" + CATEGORIA + r"\s*\n\s*GIRONE A - (\d+) Giornata", txt):
        giornata = int(blk.group(1))
        part = txt[blk.end():]
        stop = re.search(r"\n\s*GIRONE [A-Z] - \d+ Giornata|\n\s{20,}(ALLIEVI|GIOVANISSIMI|ESORDIENTI|PULCINI|JUNIORES|PRIMA CATEGORIA|TERZA CATEGORIA|CALCIO A 5|CLASSIFICHE)", part)
        part = part[:stop.start()] if stop else part[:5000]
        lines = part.splitlines()
        for i, line in enumerate(lines):
            m = re.match(r"^\s*(.+?)\s{2,}(.+?)\s{2,}([AR])\s{2,}(.*)$", line)
            if not m or "SQUADRA" in line: continue
            data = ora = None
            for j in (i - 1, i - 2):
                if 0 <= j < len(lines):
                    d = re.search(r"(\d\d)/(\d\d)/(\d{4})", lines[j])
                    if d: data = f"{d.group(3)}-{d.group(2)}-{d.group(1)}"; break
            for j in (i + 1, i + 2):
                if 0 <= j < len(lines):
                    o = re.search(r"\b(\d{1,2}:\d\d)\b", lines[j])
                    if o: ora = o.group(1); break
            out.append({"giornata": giornata, "casa": m.group(1).strip(), "ospite": m.group(2).strip(), "ar": m.group(3), "data": data, "ora": ora})
    return out

def leggi_comunicato(n, page):
    html = get(page)
    pdfs = [u for u in re.findall(r'href="([^"]+\.pdf)"', html) if "C.U." in u or "cu-" in u.lower()]
    if not pdfs: return None
    txt = pdf_text(get(pdfs[0], True))
    dm = re.search(r"C\.U\. ?\d+ - (\d\d)/(\d\d)/(\d\d)", txt)
    return {"n": n, "pdf": pdfs[0], "data": f"20{dm.group(3)}-{dm.group(2)}-{dm.group(1)}" if dm else None,
            "risultati": parse_risultati(txt), "classifica": parse_classifica(txt), "programma": parse_programma(txt)}

# ---------------- database ----------------
URL = os.environ.get("SUPABASE_URL", "https://xgsmvirezubvgpqcfxjp.supabase.co").rstrip("/") + "/rest/v1/docs"
KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
H = {"apikey": KEY, "Authorization": "Bearer " + KEY, "Content-Type": "application/json"}

def db_get(col, id=None):
    q = f"?col=eq.{col}" + (f"&id=eq.{id}" if id else "") + "&select=id,data"
    return json.loads(get_db(URL + q))

def get_db(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=H), timeout=60) as r:
        return r.read().decode()

def db_put(col, id, data):
    if DRY:
        print("  [dry] salverei", col, id); return
    body = json.dumps({"col": col, "id": id, "data": data}).encode()
    h = dict(H, Prefer="resolution=merge-duplicates,return=minimal")
    urllib.request.urlopen(urllib.request.Request(URL + "?on_conflict=col,id", data=body, headers=h, method="POST"), timeout=60)

def main():
    lista = comunicati()[:12]
    letti = [c for c in (leggi_comunicato(n, u) for n, u in lista) if c]
    if not letti: print("Nessun comunicato letto"); return
    ultimo = letti[0]
    print(f"Comunicati letti: {[c['n'] for c in letti]}")
    info = {r["id"]: r["data"] for r in db_get("info")} if KEY else {}
    # risultati: quelli già salvati + quelli nuovi (i più recenti vincono)
    ris = {}
    for r in ((info.get("girone") or {}).get("risultati") or []):
        if r.get("casaUff"): ris[(norm(r["casaUff"]), norm(r["ospiteUff"]))] = {**r, "casa": r["casaUff"], "ospite": r["ospiteUff"]}
    for c in reversed(letti):
        for r in c["risultati"]:
            ris[(norm(r["casa"]), norm(r["ospite"]))] = r
    prog = {}
    for c in reversed(letti):
        for p in c["programma"]:
            prog[(norm(p["casa"]), norm(p["ospite"]))] = p
    # il numero di giornata nei risultati dei comunicati non è affidabile: lo prendiamo dal programma gare
    for k, r in ris.items():
        p = prog.get(k) or next((v for (c, o), v in prog.items() if simile(c, k[0]) and simile(o, k[1])), None)
        if not p and r.get("data"):
            dd = datetime.date.fromisoformat(r["data"])
            p = next((v for v in prog.values() if v.get("data") and abs((datetime.date.fromisoformat(v["data"]) - dd).days) <= 2), None)
        if p: r["giornata"] = p["giornata"]
    cl = next((c["classifica"] for c in letti if c["classifica"]), [])
    cl_cu = next((c for c in letti if c["classifica"]), ultimo)
    print(f"Risultati: {len(ris)} · Partite in programma: {len(prog)} · Righe classifica: {len(cl)}")
    if KEY == "" and not DRY:
        print("Manca SUPABASE_SERVICE_KEY"); sys.exit(1)

    old_cl = (info.get("classifica") or {}).get("righe") or []
    # nomi come li usa l'app (per stemmi): se la squadra esiste già teniamo il suo nome
    nomi_app = {norm(r.get("squadra", "")): r.get("squadra") for r in old_cl}
    matches = db_get("matches") if KEY else []
    for m in matches:
        a = m["data"].get("avversario")
        if a: nomi_app.setdefault(norm(a), a)
    def bello(nome):
        k = norm(nome)
        if k == norm(NOI): return "Oneglia Sq. B"
        if k in nomi_app: return nomi_app[k]
        for kk, v in nomi_app.items():
            if simile(kk, k): return v
        return nome.title().replace("’", "'")

    # non tornare indietro: se in app c'è una classifica con più partite giocate, la teniamo
    vecchia_g = sum(int(r.get("g") or 0) for r in old_cl); nuova_g = sum(r["g"] for r in cl)
    if cl and vecchia_g > nuova_g and (info.get("classifica") or {}).get("fonte") != "LND Liguria":
        print(f"Classifica in app più recente ({vecchia_g} > {nuova_g} partite): la tengo"); cl = []
    if cl:
        zone = {norm(r.get("squadra", "")): r.get("zona") for r in old_cl}
        righe = []
        for r in cl:
            nome = bello(r["squadra"]); me = norm(r["squadra"]) == norm(NOI)
            righe.append({**r, "squadra": nome, "me": me, "zona": zone.get(norm(nome)) or ""})
        nuova = {**(info.get("classifica") or {}), "righe": righe, "fonte": "LND Liguria", "cu": cl_cu["n"], "aggiornata": cl_cu["data"]}
        if nuova != info.get("classifica"):
            db_put("info", "classifica", nuova); print("Classifica aggiornata (C.U.", cl_cu["n"], ")")

    girone = {"fonte": "Comunicati Ufficiali LND Liguria – Delegazione di Imperia", "cu": ultimo["n"], "pdf": ultimo["pdf"], "aggiornato": ultimo["data"],
              "controllato": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%MZ"),
              "risultati": sorted([{**r, "casaUff": r["casa"], "ospiteUff": r["ospite"], "casa": bello(r["casa"]), "ospite": bello(r["ospite"])} for r in ris.values()], key=lambda r: (r["giornata"], r["casa"])),
              "programma": sorted([{**p, "casa": bello(p["casa"]), "ospite": bello(p["ospite"])} for p in prog.values()], key=lambda p: (p["giornata"], p["data"] or "", p["casa"]))}
    old_g = dict(info.get("girone") or {}); old_g.pop("controllato", None)
    cmp_g = dict(girone); cmp_g.pop("controllato", None)
    if cmp_g != old_g:
        db_put("info", "girone", girone); print("Risultati e programma del girone aggiornati")

    # le nostre partite: risultato (solo se mancante), data/ora e giornata ufficiali
    for m in matches:
        d = dict(m["data"]); avv = norm(d.get("avversario", "")); cambi = {}
        if not avv: continue
        casa = d.get("casa")
        key = (norm(NOI), avv) if casa else (avv, norm(NOI))
        def trova(tab):
            if key in tab: return tab[key]
            for (c, o), v in tab.items():
                if simile(c, key[0]) and simile(o, key[1]): return v
        r = trova(ris)
        if r and abs((datetime.date.fromisoformat(r["data"] or d["data"]) - datetime.date.fromisoformat(d["data"])).days) <= 10:
            gf, gs = (r["gc"], r["go"]) if casa else (r["go"], r["gc"])
            if d.get("golFatti") in (None, ""):
                cambi.update(golFatti=gf, golSubiti=gs)
            elif (d.get("golFatti"), d.get("golSubiti")) != (gf, gs):
                cambi["risultatoUfficiale"] = f"{gf}-{gs}"
        p = trova(prog)
        giocata = d.get("golFatti") not in (None, "") or "golFatti" in cambi
        if p and not giocata and p.get("data") and abs((datetime.date.fromisoformat(p["data"]) - datetime.date.fromisoformat(d["data"])).days) <= 21:
            if p["data"] != d.get("data"): cambi["data"] = p["data"]
            if p.get("ora") and p["ora"] != d.get("ora"): cambi["ora"] = p["ora"]
        if cambi:
            print("  partita", m["id"], d.get("avversario"), cambi)
            db_put("matches", m["id"], {**d, **cambi})
    print("Fatto.")

if __name__ == "__main__":
    if "--test" in sys.argv:
        txt = open(sys.argv[sys.argv.index("--test") + 1]).read()
        print(json.dumps({"risultati": parse_risultati(txt), "classifica": parse_classifica(txt), "programma": parse_programma(txt)}, ensure_ascii=False, indent=1)[:4000])
    else:
        main()
