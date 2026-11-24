-- =====================================================================
--  FCORE · FASE 1 — Fondamenta: società, stagioni, squadre, ruoli, permessi
--  Incolla tutto in: Supabase → SQL Editor → New query → Run
--  È sicuro rieseguirlo. Non cancella nessun dato: l'Oneglia diventa la
--  società n° 1 e la Sq. B la sua prima squadra.
-- =====================================================================

-- ---------- 1. Società, stagioni, squadre ----------
create table if not exists public.clubs (
  id          text primary key,                 -- es. 'oneglia'
  nome        text not null,                    -- denominazione ufficiale
  tipo        text check (tipo in ('ASD','SSD','altro')),
  codice_fiscale text,
  partita_iva text,
  sede        text,
  email       text,
  telefono    text,
  matricola_figc text,
  stato       text not null default 'attiva' check (stato in ('attiva','sospesa','prova')),
  piano       text not null default 'starter',
  created_at  timestamptz not null default now()
);

create table if not exists public.seasons (
  id         text primary key,                  -- es. 'oneglia-2026-27'
  club_id    text not null references public.clubs(id) on delete cascade,
  nome       text not null,                     -- '2026/2027'
  inizio     date,
  fine       date,
  attiva     boolean not null default true,
  created_at timestamptz not null default now()
);

create table if not exists public.teams (
  id         text primary key,                  -- es. 'oneglia-b'
  club_id    text not null references public.clubs(id) on delete cascade,
  season_id  text references public.seasons(id) on delete set null,
  nome       text not null,                     -- 'Oneglia Sq. B'
  categoria  text,                              -- 'Seconda Categoria', 'Juniores', 'Allievi U17'…
  girone     text,
  stemma     text,
  archiviata boolean not null default false,
  created_at timestamptz not null default now()
);

-- ---------- 2. Ruoli e accessi ----------
-- Una riga = una persona con un ruolo in una società, eventualmente limitato a una squadra.
-- team_id NULL = vale per tutta la società (presidente, segretario…).
create table if not exists public.memberships (
  id         uuid primary key default gen_random_uuid(),
  email      text not null,
  club_id    text not null references public.clubs(id) on delete cascade,
  team_id    text references public.teams(id) on delete cascade,
  ruolo      text not null check (ruolo in (
               'proprietario','presidente','amministratore','segretario','direttore_sportivo',
               'resp_giovanile','allenatore','vice_allenatore','preparatore_atletico',
               'preparatore_portieri','dirigente','medico','giocatore','genitore')),
  pid        text,                              -- giocatore collegato (giocatore o figlio per il genitore)
  nome       text,
  perms_add    text[] not null default '{}',    -- permessi aggiunti dalla società
  perms_remove text[] not null default '{}',    -- permessi tolti dalla società
  revocato   boolean not null default false,    -- revoca immediata
  created_at timestamptz not null default now()
);
create unique index if not exists memberships_uni
  on public.memberships (lower(email), club_id, coalesce(team_id,''), ruolo, coalesce(pid,''));

-- Amministratori tecnici della piattaforma FCORE
create table if not exists public.platform_admins (email text primary key);

-- ---------- 3. Dati: ogni documento appartiene a una società (e di solito a una squadra) ----------
alter table public.docs add column if not exists club_id text not null default 'oneglia';
alter table public.docs add column if not exists team_id text default 'oneglia-b';

-- ---------- 4. Registro delle modifiche (storico) ----------
create table if not exists public.audit_log (
  id       bigserial primary key,
  at       timestamptz not null default now(),
  email    text,
  club_id  text,
  team_id  text,
  azione   text,           -- insert / update / delete
  col      text,
  doc_id   text,
  prima    jsonb,
  dopo     jsonb
);
create index if not exists audit_log_club on public.audit_log (club_id, at desc);

-- ---------- 5. Dati iniziali: l'Oneglia diventa la società n° 1 ----------
insert into public.clubs (id, nome, tipo) values ('oneglia','Oneglia Calcio','SSD')
  on conflict (id) do nothing;
insert into public.seasons (id, club_id, nome, inizio, fine) values
  ('oneglia-2026-27','oneglia','2026/2027','2026-07-01','2027-06-30')
  on conflict (id) do nothing;
insert into public.teams (id, club_id, season_id, nome, categoria, girone) values
  ('oneglia-b','oneglia','oneglia-2026-27','Oneglia Sq. B','Seconda Categoria','A')
  on conflict (id) do nothing;

-- Gli account esistenti passano ai nuovi ruoli
insert into public.memberships (email, club_id, team_id, ruolo, pid, nome)
select lower(m.email), 'oneglia',
       case when m.ruolo = 'admin' then null else 'oneglia-b' end,
       case m.ruolo when 'admin' then 'amministratore'
                    when 'mister' then 'allenatore'
                    when 'dirigente' then 'dirigente'
                    when 'staff' then 'dirigente'
                    else 'giocatore' end,
       m.pid, m.nome
from public.members m
where not exists (select 1 from public.memberships x where lower(x.email) = lower(m.email) and x.club_id = 'oneglia')
on conflict do nothing;
-- L'admin che gioca resta anche giocatore della squadra (per la sua scheda)
insert into public.memberships (email, club_id, team_id, ruolo, pid, nome)
select lower(m.email), 'oneglia', 'oneglia-b', 'giocatore', m.pid, m.nome
from public.members m where m.ruolo <> 'giocatore' and m.pid is not null and m.pid <> ''
  and not exists (select 1 from public.memberships x where lower(x.email) = lower(m.email) and x.club_id = 'oneglia' and x.ruolo = 'giocatore')
on conflict do nothing;

-- ---------- 6. Permessi: cosa può fare ogni ruolo (la società può aggiungere o togliere) ----------
create or replace function public.role_perms(r text) returns text[]
language sql immutable as $$
  select case r
    when 'proprietario'        then array['societa.gestire','utenti.gestire','rosa.leggere','rosa.modificare','allenamenti.gestire','presenze.gestire','partite.gestire','convocazioni.gestire','formazioni.gestire','risultati.inserire','statistiche.leggere','comunicazioni.inviare','cassa.leggere','cassa.gestire','documenti.gestire','salute.leggere','registro.leggere']
    when 'presidente'          then array['societa.gestire','utenti.gestire','rosa.leggere','rosa.modificare','allenamenti.gestire','presenze.gestire','partite.gestire','convocazioni.gestire','formazioni.gestire','risultati.inserire','statistiche.leggere','comunicazioni.inviare','cassa.leggere','cassa.gestire','documenti.gestire','registro.leggere']
    when 'amministratore'      then array['societa.gestire','utenti.gestire','rosa.leggere','rosa.modificare','allenamenti.gestire','presenze.gestire','partite.gestire','convocazioni.gestire','formazioni.gestire','risultati.inserire','statistiche.leggere','comunicazioni.inviare','cassa.leggere','cassa.gestire','documenti.gestire','salute.leggere','salute.scrivere','registro.leggere']
    when 'segretario'          then array['rosa.leggere','rosa.modificare','statistiche.leggere','comunicazioni.inviare','cassa.leggere','cassa.gestire','documenti.gestire']
    when 'direttore_sportivo'  then array['rosa.leggere','rosa.modificare','partite.gestire','risultati.inserire','statistiche.leggere','comunicazioni.inviare']
    when 'resp_giovanile'      then array['rosa.leggere','rosa.modificare','allenamenti.gestire','presenze.gestire','partite.gestire','convocazioni.gestire','statistiche.leggere','comunicazioni.inviare','documenti.gestire']
    when 'allenatore'          then array['rosa.leggere','allenamenti.gestire','presenze.gestire','partite.gestire','convocazioni.gestire','formazioni.gestire','risultati.inserire','statistiche.leggere','comunicazioni.inviare','salute.disponibilita']
    when 'vice_allenatore'     then array['rosa.leggere','allenamenti.gestire','presenze.gestire','convocazioni.gestire','formazioni.gestire','statistiche.leggere','salute.disponibilita']
    when 'preparatore_atletico' then array['rosa.leggere','allenamenti.gestire','presenze.gestire','statistiche.leggere','salute.disponibilita']
    when 'preparatore_portieri' then array['rosa.leggere','allenamenti.gestire','presenze.gestire','statistiche.leggere']
    when 'dirigente'           then array['rosa.leggere','rosa.modificare','presenze.gestire','partite.gestire','convocazioni.gestire','risultati.inserire','statistiche.leggere','comunicazioni.inviare','cassa.leggere','cassa.gestire','salute.disponibilita']
    when 'medico'              then array['rosa.leggere','salute.leggere','salute.scrivere','salute.disponibilita']
    else array[]::text[]     -- giocatore e genitore: solo i propri dati
  end $$;

create or replace function public.my_email() returns text
language sql stable as $$ select lower(coalesce(auth.jwt()->>'email','')) $$;

create or replace function public.is_platform_admin() returns boolean
language sql stable security definer set search_path = public as $$
  select exists(select 1 from platform_admins where lower(email) = my_email()) $$;

-- È membro (con qualunque ruolo) della società / squadra?
create or replace function public.in_scope(c text, t text) returns boolean
language sql stable security definer set search_path = public as $$
  select exists(select 1 from memberships m
    where lower(m.email) = my_email() and not m.revocato and m.club_id = c
      and (m.team_id is null or t is null or m.team_id = t)) $$;

-- Ha un permesso su quella società / squadra?
create or replace function public.has_perm(c text, t text, p text) returns boolean
language sql stable security definer set search_path = public as $$
  select is_platform_admin() or exists(select 1 from memberships m
    where lower(m.email) = my_email() and not m.revocato and m.club_id = c
      and (m.team_id is null or t is null or m.team_id = t)
      and ((p = any(role_perms(m.ruolo)) or p = any(m.perms_add)) and not p = any(m.perms_remove))) $$;

-- I giocatori di cui posso vedere i dati personali (me stesso, o i figli se sono genitore)
create or replace function public.my_pids(c text) returns text[]
language sql stable security definer set search_path = public as $$
  select coalesce(array_agg(pid), '{}') from memberships
  where lower(email) = my_email() and not revocato and club_id = c and pid is not null and pid <> '' $$;

-- Permesso necessario per scrivere ogni tipo di dato
create or replace function public.write_perm(col text) returns text
language sql immutable as $$
  select case col
    when 'players'   then 'rosa.modificare'
    when 'staff'     then 'rosa.modificare'
    when 'trainings' then 'allenamenti.gestire'
    when 'matches'   then 'partite.gestire'
    when 'news'      then 'comunicazioni.inviare'
    when 'cassa'     then 'cassa.gestire'
    when 'infortuni' then 'salute.scrivere'
    when 'info'      then 'partite.gestire'
    else 'societa.gestire' end $$;

-- ---------- 7. Regole di accesso ai dati (applicate dal database, non solo dalla grafica) ----------
alter table public.docs        enable row level security;
alter table public.clubs       enable row level security;
alter table public.seasons     enable row level security;
alter table public.teams       enable row level security;
alter table public.memberships enable row level security;
alter table public.audit_log   enable row level security;
alter table public.platform_admins enable row level security;

drop policy if exists docs_read on public.docs;
drop policy if exists docs_ins  on public.docs;
drop policy if exists docs_upd  on public.docs;
drop policy if exists docs_del  on public.docs;

-- Leggere: solo dentro la propria società/squadra.
-- Cassa: chi ha cassa.leggere, oppure solo le proprie righe.
-- Infortuni: chi ha salute.leggere (medico…), chi vede solo la disponibilità, oppure le proprie righe.
create policy docs_read on public.docs for select to authenticated using (
  in_scope(club_id, team_id) and (
    (col not in ('cassa','infortuni'))
    or (col = 'cassa' and (has_perm(club_id, team_id, 'cassa.leggere') or data->>'pid' = any(my_pids(club_id))))
    or (col = 'infortuni' and (has_perm(club_id, team_id, 'salute.leggere') or has_perm(club_id, team_id, 'salute.disponibilita') or data->>'pid' = any(my_pids(club_id))))
  ) or is_platform_admin());

-- Scrivere: serve il permesso giusto; giocatori e genitori solo la propria disponibilità.
create policy docs_ins on public.docs for insert to authenticated with check (
  has_perm(club_id, team_id, write_perm(col))
  or (col = 'disp' and in_scope(club_id, team_id) and data->>'pid' = any(my_pids(club_id))));
create policy docs_upd on public.docs for update to authenticated
  using (has_perm(club_id, team_id, write_perm(col))
    or (col = 'disp' and in_scope(club_id, team_id) and data->>'pid' = any(my_pids(club_id))))
  with check (has_perm(club_id, team_id, write_perm(col))
    or (col = 'disp' and in_scope(club_id, team_id) and data->>'pid' = any(my_pids(club_id))));
create policy docs_del on public.docs for delete to authenticated using (
  has_perm(club_id, team_id, write_perm(col))
  or (col = 'disp' and in_scope(club_id, team_id) and data->>'pid' = any(my_pids(club_id))));

drop policy if exists clubs_read on public.clubs;
drop policy if exists clubs_upd  on public.clubs;
create policy clubs_read on public.clubs for select to authenticated using (in_scope(id, null) or is_platform_admin());
create policy clubs_upd  on public.clubs for update to authenticated using (has_perm(id, null, 'societa.gestire')) with check (has_perm(id, null, 'societa.gestire'));

drop policy if exists seasons_read on public.seasons;
drop policy if exists seasons_all  on public.seasons;
create policy seasons_read on public.seasons for select to authenticated using (in_scope(club_id, null) or is_platform_admin());
create policy seasons_all  on public.seasons for all to authenticated using (has_perm(club_id, null, 'societa.gestire')) with check (has_perm(club_id, null, 'societa.gestire'));

drop policy if exists teams_read on public.teams;
drop policy if exists teams_all  on public.teams;
create policy teams_read on public.teams for select to authenticated using (in_scope(club_id, id) or in_scope(club_id, null) or is_platform_admin());
create policy teams_all  on public.teams for all to authenticated using (has_perm(club_id, null, 'societa.gestire')) with check (has_perm(club_id, null, 'societa.gestire'));

drop policy if exists mship_read on public.memberships;
drop policy if exists mship_all  on public.memberships;
create policy mship_read on public.memberships for select to authenticated using (
  lower(email) = my_email() or has_perm(club_id, team_id, 'utenti.gestire') or is_platform_admin());
create policy mship_all on public.memberships for all to authenticated
  using (has_perm(club_id, team_id, 'utenti.gestire'))
  with check (has_perm(club_id, team_id, 'utenti.gestire')
              and (ruolo <> 'proprietario' or has_perm(club_id, null, 'societa.gestire')));

drop policy if exists audit_read on public.audit_log;
create policy audit_read on public.audit_log for select to authenticated using (
  has_perm(club_id, null, 'registro.leggere') or is_platform_admin());

drop policy if exists padm_read on public.platform_admins;
create policy padm_read on public.platform_admins for select to authenticated using (lower(email) = my_email());

-- ---------- 8. Storico automatico di ogni modifica ----------
create or replace function public.audit_docs() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  if tg_op = 'DELETE' then
    insert into audit_log(email, club_id, team_id, azione, col, doc_id, prima)
    values (my_email(), old.club_id, old.team_id, 'delete', old.col, old.id, old.data);
    return old;
  end if;
  insert into audit_log(email, club_id, team_id, azione, col, doc_id, prima, dopo)
  values (my_email(), new.club_id, new.team_id, lower(tg_op), new.col, new.id,
          case when tg_op = 'UPDATE' then old.data end, new.data);
  return new;
end $$;
drop trigger if exists docs_audit on public.docs;
create trigger docs_audit after insert or update or delete on public.docs
  for each row execute function public.audit_docs();

-- ---------- 9. Il mio profilo: società, squadre e permessi (lo usa l'app all'accesso) ----------
create or replace function public.my_access() returns jsonb
language sql stable security definer set search_path = public as $$
  select coalesce(jsonb_agg(jsonb_build_object(
      'club_id', m.club_id, 'club', c.nome, 'team_id', m.team_id, 'team', t.nome,
      'ruolo', m.ruolo, 'pid', m.pid, 'nome', m.nome,
      'perms', (select coalesce(array_agg(p), '{}') from unnest(role_perms(m.ruolo) || m.perms_add) p
                where not p = any(m.perms_remove)))), '[]'::jsonb)
  from memberships m join clubs c on c.id = m.club_id left join teams t on t.id = m.team_id
  where lower(m.email) = my_email() and not m.revocato $$;

-- Tu (proprietario del progetto) diventi amministratore tecnico della piattaforma
insert into public.platform_admins (email) values ('alessiolosicco10@gmail.com') on conflict do nothing;
update public.memberships set ruolo = 'proprietario'
  where lower(email) = 'alessiolosicco10@gmail.com' and club_id = 'oneglia' and team_id is null and ruolo = 'amministratore'
    and not exists (select 1 from public.memberships x where lower(x.email) = 'alessiolosicco10@gmail.com' and x.club_id = 'oneglia' and x.ruolo = 'proprietario');

-- Indici
create index if not exists docs_scope on public.docs (club_id, team_id, col);
create index if not exists memberships_email on public.memberships (lower(email));

-- ---------- 10. Chiave dei documenti per società (gli id possono ripetersi tra società diverse) ----------
do $$ begin
  if exists (select 1 from information_schema.table_constraints
             where table_name='docs' and constraint_name='docs_pkey'
               and constraint_type='PRIMARY KEY')
     and not exists (select 1 from information_schema.key_column_usage
             where table_name='docs' and constraint_name='docs_pkey' and column_name='club_id') then
    alter table public.docs drop constraint docs_pkey;
    alter table public.docs add primary key (club_id, col, id);
  end if;
end $$;
