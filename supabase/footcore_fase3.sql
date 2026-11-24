-- =====================================================================
--  FOOTCORE · FASE 3 — Campionati pubblici (come Tuttocampo, senza account)
--  Incolla tutto in: Supabase → SQL Editor → New query → Run
--  È sicuro rieseguirlo.
-- =====================================================================

-- Un campionato = una categoria + un girone (es. Seconda Categoria girone A).
-- Lo riempie in automatico scripts/lnd_campionati.py dai Comunicati Ufficiali LND.
create table if not exists public.campionati (
  id          text primary key,            -- es. 'seconda-categoria-a'
  delegazione text not null default 'Imperia',
  categoria   text not null,               -- 'Seconda Categoria', 'Allievi U17 Provinciali'…
  girone      text not null default 'A',
  stagione    text not null default '2026/2027',
  dati        jsonb not null default '{}'::jsonb,  -- classifica, risultati, programma
  aggiornato  date,
  updated_at  timestamptz not null default now()
);

alter table public.campionati enable row level security;
drop policy if exists campionati_read on public.campionati;
-- Tutti possono leggere, anche senza account. Scrive solo l'aggiornamento automatico (chiave di servizio).
create policy campionati_read on public.campionati for select to anon, authenticated using (true);
grant select on public.campionati to anon, authenticated;

-- Abbonamento della società: per ora la gestione è gratuita per tutti (fase di prova).
alter table public.clubs add column if not exists abbonamento text not null default 'prova gratuita';
