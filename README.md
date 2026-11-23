# Oneglia Sq. B · App della squadra

App web per gestire rosa, allenamenti, partite, formazioni, cassa e comunicazioni dell'Oneglia Calcio Sq. B.

- **Sito**: pubblicato da Netlify a ogni push su `main` (nessuna build: `index.html` statico).
- **Database e accessi**: Supabase (tabelle `docs` e `members`, regole in `supabase/schema.sql`).
- La chiave nel codice è la chiave pubblica *anon* di Supabase: i dati sono protetti dalle regole del database e dagli account.
