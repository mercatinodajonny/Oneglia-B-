-- FOOTCORE · fasi 2 e 3 insieme: incolla TUTTO in Supabase → SQL Editor → New query → Run
-- =====================================================================
--  FOOTCORE · FASE 2 — Accessi senza conferma email + pagina pubblica
--  Incolla tutto in: Supabase → SQL Editor → New query → Run
--  Richiede di aver già eseguito fcore_fase1.sql. È sicuro rieseguirlo.
-- =====================================================================

-- ---------- 1. Niente più "Email not confirmed" per chi è stato invitato dallo staff ----------
-- Se l'email è già registrata dallo staff (memberships o members), l'account
-- creato con "Primo accesso" viene confermato subito. Le email sconosciute no.
create or replace function public.auto_confirm_invited() returns trigger
language plpgsql security definer set search_path = public, auth as $$
begin
  if new.email_confirmed_at is null and (
       exists (select 1 from public.memberships m where lower(m.email) = lower(new.email) and not m.revocato)
    or exists (select 1 from public.members mb where lower(mb.email) = lower(new.email))
  ) then
    new.email_confirmed_at := now();
  end if;
  return new;
end $$;

drop trigger if exists footcore_auto_confirm on auth.users;
create trigger footcore_auto_confirm before insert on auth.users
  for each row execute function public.auto_confirm_invited();

-- Sblocca chi si è già registrato ma è rimasto bloccato
update auth.users u set email_confirmed_at = now()
where u.email_confirmed_at is null and (
     exists (select 1 from public.memberships m where lower(m.email) = lower(u.email) and not m.revocato)
  or exists (select 1 from public.members mb where lower(mb.email) = lower(u.email)));

-- ---------- 2. Pagina pubblica ----------
-- La società decide se la sua squadra è visibile al pubblico (di default sì).
alter table public.teams add column if not exists pubblica boolean not null default true;

-- Restituisce SOLO i dati pubblici di una squadra: classifica, partite e,
-- per i giocatori, nome, ruolo, numero, età, presenze, gol e assist.
-- Mai telefono, email, data di nascita, certificati, cassa, note o infortuni.
-- Un giocatore con "pubblico" = false nella sua scheda non compare.
create or replace function public.footcore_pubblico(t text default 'oneglia-b') returns jsonb
language sql stable security definer set search_path = public as $$
  with tm as (
    select t2.*, c.nome as club_nome from teams t2 join clubs c on c.id = t2.club_id
    where t2.id = t and t2.pubblica and not t2.archiviata
  ),
  ms as (
    select d.data from docs d, tm where d.club_id = tm.club_id and d.col = 'matches'
      and (d.team_id = tm.id or d.team_id is null)
  ),
  ps as (
    select d.id, d.data from docs d, tm where d.club_id = tm.club_id and d.col = 'players'
      and (d.team_id = tm.id or d.team_id is null)
      and coalesce(d.data->>'pubblico','true') <> 'false'
      and coalesce(d.data->>'stato','') not in ('ex','svincolato','ceduto')
  )
  select case when not exists (select 1 from tm) then null else jsonb_build_object(
    'squadra', (select jsonb_build_object('id', id, 'nome', nome, 'club', club_nome, 'categoria', categoria, 'girone', girone) from tm),
    'classifica', (select d.data from docs d, tm where d.club_id = tm.club_id and d.col = 'info' and d.id = 'classifica' and (d.team_id = tm.id or d.team_id is null) limit 1),
    'partite', coalesce((select jsonb_agg(jsonb_build_object(
        'data', m.data->>'data', 'ora', m.data->>'ora', 'avversario', m.data->>'avversario',
        'casa', m.data->'casa', 'golFatti', m.data->'golFatti', 'golSubiti', m.data->'golSubiti',
        'giornata', m.data->'giornata', 'competizione', m.data->>'competizione', 'luogo', m.data->>'luogo',
        'live', m.data->'live')
      order by m.data->>'data') from ms m), '[]'::jsonb),
    'giocatori', coalesce((select jsonb_agg(jsonb_build_object(
        'nome', p.data->>'nome', 'cognome', p.data->>'cognome', 'ruolo', p.data->>'ruolo', 'numero', p.data->'numero',
        'eta', case when coalesce(p.data->>'nascita','') ~ '^\d{4}-\d{2}-\d{2}'
                    then date_part('year', age(current_date, (p.data->>'nascita')::date))::int end,
        'gol', (select coalesce(sum(nullif(m.data->'marcatori'->>p.id,'')::numeric),0) from ms m),
        'assist', (select coalesce(sum(nullif(m.data->'assist'->>p.id,'')::numeric),0) from ms m),
        'presenze', (select count(*) from ms m where coalesce(nullif(m.data->'minuti'->>p.id,'')::numeric,0) > 0
                       or (m.data->'golFatti' is not null and m.data->>'golFatti' <> '' and coalesce(m.data->'convocati','[]'::jsonb) ? p.id))
      )) from ps p), '[]'::jsonb)
  ) end $$;

grant execute on function public.footcore_pubblico(text) to anon, authenticated;

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
