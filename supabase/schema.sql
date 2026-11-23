-- =========================================================
--  ONEGLIA SQ. B · Database (Supabase, piano gratuito)
--  Incolla tutto in: Supabase → SQL Editor → New query → Run
-- =========================================================

-- Tabella unica con tutti i dati dell'app
create table if not exists public.docs (
  col  text not null,
  id   text not null,
  data jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now(),
  primary key (col, id)
);

-- Account: li crea lo staff dall'app (email + ruolo + giocatore collegato)
create table if not exists public.members (
  email text primary key,
  ruolo text not null default 'giocatore'
        check (ruolo in ('giocatore','staff','dirigente','mister','admin')),
  pid   text,
  nome  text,
  created_at timestamptz not null default now()
);

-- Funzioni di supporto (leggono il ruolo di chi è collegato)
create or replace function public.my_email() returns text
language sql stable as $$ select lower(coalesce(auth.jwt()->>'email','')) $$;

create or replace function public.my_role() returns text
language sql stable security definer set search_path = public as $$
  select ruolo from members where email = my_email() $$;

create or replace function public.my_pid() returns text
language sql stable security definer set search_path = public as $$
  select pid from members where email = my_email() $$;

create or replace function public.is_member() returns boolean
language sql stable security definer set search_path = public as $$
  select exists(select 1 from members where email = my_email()) $$;

create or replace function public.is_staff() returns boolean
language sql stable security definer set search_path = public as $$
  select coalesce(my_role() in ('staff','dirigente','mister','admin'), false) $$;

create or replace function public.is_manager() returns boolean
language sql stable security definer set search_path = public as $$
  select coalesce(my_role() in ('dirigente','mister','admin'), false) $$;

-- Il primo che entra quando non esiste ancora nessun admin diventa admin
create or replace function public.claim_admin() returns boolean
language plpgsql security definer set search_path = public as $$
begin
  if my_email() = '' then return false; end if;
  if exists(select 1 from members where ruolo = 'admin') then return false; end if;
  insert into members(email, ruolo, nome) values (my_email(), 'admin', 'Amministratore')
  on conflict (email) do update set ruolo = 'admin';
  return true;
end $$;

-- Sicurezza riga per riga
alter table public.docs enable row level security;
alter table public.members enable row level security;

drop policy if exists docs_read  on public.docs;
drop policy if exists docs_ins   on public.docs;
drop policy if exists docs_upd   on public.docs;
drop policy if exists docs_del   on public.docs;

-- Leggere: solo chi ha un account. Cassa e infortuni: lo staff vede tutto,
-- il giocatore solo le proprie righe.
create policy docs_read on public.docs for select to authenticated using (
  is_member() and (
    col not in ('cassa','infortuni') or is_staff() or data->>'pid' = my_pid()
  ));

-- Scrivere: lo staff tutto; il giocatore solo la propria disponibilità
create policy docs_ins on public.docs for insert to authenticated with check (
  is_staff() or (col = 'disp' and data->>'pid' = my_pid()));
create policy docs_upd on public.docs for update to authenticated
  using (is_staff() or (col = 'disp' and data->>'pid' = my_pid()))
  with check (is_staff() or (col = 'disp' and data->>'pid' = my_pid()));
create policy docs_del on public.docs for delete to authenticated using (
  is_staff() or (col = 'disp' and data->>'pid' = my_pid()));

drop policy if exists mem_read on public.members;
drop policy if exists mem_ins  on public.members;
drop policy if exists mem_upd  on public.members;
drop policy if exists mem_del  on public.members;
create policy mem_read on public.members for select to authenticated using (email = my_email() or is_staff());
create policy mem_ins  on public.members for insert to authenticated with check (is_manager());
create policy mem_upd  on public.members for update to authenticated using (is_manager()) with check (is_manager());
create policy mem_del  on public.members for delete to authenticated using (is_manager());

-- Aggiornamenti in tempo reale
alter table public.docs replica identity full;
do $$ begin
  alter publication supabase_realtime add table public.docs;
exception when duplicate_object then null; end $$;
