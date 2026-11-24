# FootCore · Oneglia Sq. B

App web per gestire rosa, allenamenti, partite, formazioni, cassa e comunicazioni dell'Oneglia Calcio Sq. B.

- **Sito**: pubblicato da GitHub Pages (https://mercatinodajonny.github.io/Oneglia-B-/) a ogni push su `main` (nessuna build: `index.html` statico).
- **Risultati, calendario e classifica**: `scripts/lnd_sync.py` legge i Comunicati Ufficiali LND Liguria (Delegazione di Imperia) e aggiorna il database. Gira da solo con GitHub Actions (`.github/workflows/lnd-sync.yml`, due volte al giorno) e serve il segreto `SUPABASE_SERVICE_KEY`.
- **Database e accessi**: Supabase (tabelle `docs` e `members`, regole in `supabase/schema.sql`).
- La chiave nel codice è la chiave pubblica *anon* di Supabase: i dati sono protetti dalle regole del database e dagli account.

## Nota per chi modifica
A ogni modifica di index.html aggiorna la costante `BUILD` (es. "2026-11-24-1"): così le app già aperte sui telefoni si ricaricano da sole con la versione nuova.

## FootCore
- `supabase/fcore_fase1.sql`: società, stagioni, squadre, ruoli e permessi.
- `supabase/footcore_fase2.sql`: conferma automatica degli account invitati dallo staff e pagina pubblica (`#pubblico`, funzione `footcore_pubblico`).
- Logo e icone in `assets/` (footcore-logo.svg, footcore-mark.svg, footcore-icon.svg).
- `supabase/footcore_fase3.sql` + `scripts/lnd_campionati.py`: campionati pubblici di tutte le categorie della Delegazione di Imperia (tabella `campionati`, leggibile senza account), aggiornati dalla stessa GitHub Action.
