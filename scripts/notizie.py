#!/usr/bin/env python3
"""Raccoglie le ultime notizie di calcio dai feed RSS pubblici delle testate.

Per ogni notizia salva titolo, fonte, data, link all'articolo originale e
l'indirizzo dell'immagine di anteprima che la testata stessa pubblica per la
condivisione (og:image / immagine del feed). L'immagine non viene copiata:
l'app la mostra dal sito della testata, con la fonte e il link all'articolo.
Riconosce le squadre citate nel titolo, così l'app mostra prima le notizie
delle squadre preferite e usa lo stemma della squadra come immagine.

Uscita: data/notizie.json
"""
import json, re, sys, concurrent.futures as cf, unicodedata, urllib.request, email.utils, datetime as dt
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent.parent
UA = {"User-Agent": "Mozilla/5.0 (GolazoApp; +https://mercatinodajonny.github.io/Oneglia-B-/)"}

# fonte: (nome mostrato, url feed, zona, filtro: True = tieni solo se parla di calcio)
FONTI = [
    ("IVG", "https://www.ivg.it/feed/", "Savona", True),
    ("SvSport", "https://www.svsport.it/rss.xml", "Savona", True),
    ("Riviera24", "https://www.riviera24.it/sport/feed/", "Imperia", True),
    ("Genova24", "https://www.genova24.it/feed/", "Genova", True),
    ("Città della Spezia", "https://www.cittadellaspezia.com/feed/", "La Spezia", True),
    ("Levante News", "https://www.levantenews.it/feed/", "Genova", True),
    ("Calcio Flash Ponente", "https://www.calcioflashponente.it/feed/", "Imperia", False),
    ("Sanremonews", "https://www.sanremonews.it/rss.xml", "Imperia", True),
    ("ImperiaPost", "https://www.imperiapost.it/feed/", "Imperia", True),
    ("ANSA", "https://www.ansa.it/sito/notizie/sport/calcio/calcio_rss.xml", "Italia", False),
]

CALCIO = re.compile(r"\b(calcio|serie [abcd]|eccellenza|promozione|prima categoria|seconda categoria|terza categoria|"
                    r"juniores|allievi|giovanissimi|under ?1\d|mister|allenatore|gol|rigore|classifica|campionato|"
                    r"panchina|attaccante|centrocampista|difensore|portiere|derby|girone|coppa italia|squadra|partita|vittoria|sconfitta|"
                    r"pareggio|tre punti|ds|direttore sportivo|calciomercato|doppietta|tripletta|capolista|salvezza|playoff|playout|stadio)\b", re.I)
ESCLUDI = re.compile(r"\b(calcio a 5|futsal|pallavolo|volley|basket|rugby|pallanuoto|tennis|ciclismo|atletica|nuoto|hockey|"
                     r"padel|baseball|softball|bocce|scacchi)\b", re.I)


def norm(s):
    s = unicodedata.normalize("NFD", s.lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def squadre_note():
    """Nomi brevi delle squadre presenti nell'app (dilettanti + professionisti)."""
    nomi = set()
    for f in ("campionati.json", "nazionali.json"):
        p = ROOT / "data" / f
        if not p.exists():
            continue
        d = json.loads(p.read_text())
        for c in d.get("campionati", d if isinstance(d, list) else []):
            for r in ((c.get("dati") or {}).get("classifica") or {}).get("righe", []):
                nomi.add(r["squadra"])
    brevi = {}
    for n in nomi:
        b = re.sub(r"\b(a\.?s\.?d\.?|s\.?s\.?d\.?|u\.?s\.?d?\.?|f\.?c\.?|f\.?b\.?c\.?|calcio|ssdarl|srl|s\.r\.l\.?|sq\.? ?[a-d])\b", " ", n, flags=re.I)
        b = re.sub(r"\b(18|19|20)\d\d\b", " ", b)
        b = re.sub(r"[^\w' &]", " ", b)
        b = re.sub(r"\s+", " ", b).strip()
        if len(b) >= 4:
            brevi.setdefault(norm(b), n)
    # nomi comuni ma ambigui da non usare da soli
    for x in ("inter", "genova", "san", "don bosco", "royal", "ponente", "finale", "colli", "mele", "sori", "panchina"):
        brevi.pop(x, None)
    return brevi


def trova_squadre(titolo, brevi):
    t = norm(titolo)
    trovate = []
    for b, n in sorted(brevi.items(), key=lambda x: -len(x[0])):
        if re.search(r"(?<![\w])" + re.escape(b) + r"(?![\w])", t) and not any(b in norm(x) for x in trovate):
            trovate.append(n)
    return trovate[:3]


def img_feed(it):
    for tag in ("{http://search.yahoo.com/mrss/}content", "{http://search.yahoo.com/mrss/}thumbnail", "enclosure"):
        for e in it.findall(tag):
            u = e.get("url") or ""
            if u.startswith("http") and (e.get("type", "image").startswith("image") or re.search(r"\.(jpe?g|png|webp)", u, re.I)):
                return u
    return ""


def og_image(url):
    try:
        req = urllib.request.Request(url, headers=UA)
        html = urllib.request.urlopen(req, timeout=10).read(250000).decode("utf-8", "ignore")
        m = re.search(r'<meta[^>]+property=["\']og:image(?::secure_url)?["\'][^>]+content=["\']([^"\']+)', html) or \
            re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image', html)
        u = (m.group(1) if m else "").replace("&amp;", "&").strip()
        if u.startswith("//"):
            u = "https:" + u
        return u if u.startswith("https://") else ""
    except Exception:
        return ""


def data_iso(s):
    try:
        return email.utils.parsedate_to_datetime(s).astimezone(dt.timezone.utc).isoformat()
    except Exception:
        return ""


def main():
    brevi = squadre_note()
    out, visti = [], set()
    for nome, url, zona, filtro in FONTI:
        try:
            req = urllib.request.Request(url, headers=UA)
            xml = urllib.request.urlopen(req, timeout=20).read()
            items = ET.fromstring(xml).findall(".//item")
        except Exception as e:
            print(f"{nome}: non raggiungibile ({e})", file=sys.stderr)
            continue
        for it in items:
            titolo = re.sub(r"\s+", " ", (it.findtext("title") or "")).strip()
            link = (it.findtext("link") or "").strip()
            if not titolo or not link.startswith("http") or link in visti:
                continue
            cat = " ".join(c.text or "" for c in it.findall("category"))
            sq = trova_squadre(titolo, brevi)
            if ESCLUDI.search(titolo) and not sq:
                continue
            if filtro and not CALCIO.search(titolo):
                continue
            # titoli svsport tipo "Calcio | Andora. ..."
            if re.match(r"^\s*(calcio)\s*\|\s*", titolo, re.I):
                titolo = re.sub(r"^\s*calcio\s*\|\s*", "", titolo, flags=re.I)
            elif "|" in titolo[:25]:
                continue  # altri sport su svsport ("Savona Rugby | ...")
            visti.add(link)
            out.append({"t": titolo[:160], "f": nome, "z": zona, "u": link,
                        "d": data_iso(it.findtext("pubDate") or ""), "sq": sq, "img": img_feed(it)})
    out.sort(key=lambda x: x["d"], reverse=True)
    out = out[:60]
    senza = [x for x in out if not x["img"]]
    with cf.ThreadPoolExecutor(8) as ex:
        for x, u in zip(senza, ex.map(lambda x: og_image(x["u"]), senza)):
            x["img"] = u
    # immagini generiche del sito (logo della testata) non servono
    for x in out:
        if re.search(r"(logo|default|placeholder|share-?image|og-?default)", x["img"], re.I):
            x["img"] = ""
    res = {"aggiornato": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes"),
           "nota": "Titoli, link e immagini di anteprima pubblicati dalle testate per la condivisione. Gli articoli e le foto restano sui loro siti.",
           "notizie": out[:60]}
    (ROOT / "data" / "notizie.json").write_text(json.dumps(res, ensure_ascii=False, indent=0))
    print(len(out), "notizie;", sum(1 for x in out if x["img"]), "con foto;", sum(1 for x in out if x["sq"]), "con squadre riconosciute")


if __name__ == "__main__":
    main()
