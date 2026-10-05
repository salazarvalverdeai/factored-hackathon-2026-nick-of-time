-- Nick of Time — Postgres schema of spec 01 §6.5 (ADR 0010). Idempotent: infra/deploy.sh applies it on every deploy, so a
-- table added later is created and nothing existing changes (new columns need a migration). apps/api/migrations adopts this file as its first
-- migration (D-002); tests/test_spec01_store_schema.py keeps it in step with the spec table.
-- Conventions [assumption]: a column the spec leaves untyped is text (timestamps timestamptz, counters integer); a
-- column is not null unless the spec marks it null. Rows are never updated or deleted in the append-only (AO) tables.
-- A "sub not blank" holds a character outside Python's str.isspace() set, spelled out so no server locale changes it;
-- (?p) keeps `.` off newlines, as in the store's ACTOR.

create table if not exists sessions (
  session_id text primary key,
  customer_id text null,
  otp_hash text not null,
  verified_at timestamptz null,
  expires_at timestamptz not null,
  language text not null,
  mode text not null check (mode in ('replay', 'live')),            -- fixed at creation (AC-07)
  display_currency text null,
  tool_faults text[] not null default array[]::text[],
  run_id text null,                                                  -- eval seed or a demo session (§6.8, ADR 0026)
  arm text null,                                                     -- eval seed or DEFAULT_ARM
  display_name text null,                                            -- a demo visitor's typed name (ADR 0026)
  created_at timestamptz not null default now()
);

create table if not exists cases (                                                 -- AO, insert-only; status = last event
  case_id text primary key,                                          -- K- + 6 digits: the insert retries (T9)
  customer_id text not null,
  transaction_id text not null,
  product_id text not null,
  country text not null,
  product_type text not null check (product_type in ('debit', 'credit')),
  zone text not null check (zone in ('high', 'medium', 'human')),
  dispute_type text not null check (dispute_type in ('unrecognized_charge', 'wrongful_charge')),
  opened_on date not null,                                           -- business date (D-023)
  credit_deadline date null,                                         -- stored once, never recomputed
  ruling_deadline date null,
  deadline_source text null check (deadline_source <> ''),
  deadline_source_url text null check (deadline_source_url is null or deadline_source_url ~ '^https://\S+$'),
  deadline_verified_on date null,                                    -- [assumption] D-014
  related_case_id text null,
  mode text not null check (mode in ('replay', 'live')),
  run_id text null,
  trace_id text not null,
  created_at timestamptz not null default now(),
  -- a legal date travels with its source, its https:// URL (column check) and the date it was verified (§6.6,
  -- ADR 0019, D-014). Every term is "is not null": a check that evaluates to null passes.
  check ((credit_deadline is null and ruling_deadline is null)
         or (deadline_source is not null and deadline_source_url is not null and deadline_verified_on is not null))
);

create table if not exists demo_transactions (                                     -- live mode only; gold transactions columns
  transaction_id text primary key,
  transaction_date timestamp not null,
  process_date date not null,
  product_id text not null,
  customer_id text not null,
  transaction_type text not null,
  transaction_category text null,
  amount double precision not null,
  currency text not null,
  amount_usd double precision null,
  channel text null,
  branch_id text null,
  merchant_name text null,
  merchant_category text null,
  transaction_country text null,
  transaction_city text null,
  transaction_status text not null,
  response_code text null,
  fraud_score double precision null,
  latitude double precision null,
  longitude double precision null,
  product_type text null,                                                          -- the card type, as transactions_enriched
  synthetic boolean not null default true check (synthetic),
  scenario text not null,
  run_id text null,                                                                -- the demo session's run (ADR 0026)
  generated_at timestamptz not null default now()
);

create table if not exists case_events (                                           -- AO
  event_id text primary key,
  case_id text not null references cases (case_id),
  seq integer not null check (seq >= 1),
  type text not null check (type in ('case_opened', 'card_blocked', 'block_verified', 'action_verified',
    'status_changed', 'handoff_emitted', 'assigned', 'analyst_action', 'customer_info_added', 'call_requested',
    'reevaluation_requested', 'related_case_opened', 'notification_sent', 'receipt_issued', 'telegram_linked',
    'email_confirmed')),
  actor text not null check (actor in ('agent', 'customer', 'system')
    or actor ~ '(?p)^analyst:.*[^\t\n\v\f\r\u001c-\u001f \u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000].*$'),
  payload jsonb not null default '{}',
  customer_visible boolean not null,
  trace_id text not null,
  created_at timestamptz not null default now(),
  unique (case_id, seq),
  -- the store's rules as rows (D-025, D-034). Every pattern is anchored: DuckDB's ~ matches the whole string.
  -- An action id is always an A- id; the writes (a summary send only on request) and the two reads always carry one,
  -- and a read always carries its V- id.
  check ((payload ->> 'action_id') is null or (payload ->> 'action_id') ~ '^A-[0-9A-F]{12}$'),
  check (type not in ('case_opened', 'card_blocked', 'customer_info_added', 'call_requested', 'reevaluation_requested',
                      'action_verified', 'block_verified')
         or (payload ->> 'action_id') is not null),
  check (type <> 'action_verified' or coalesce(payload ->> 'verification_id', '') ~ '^V-[0-9A-F]{12}$'),
  -- a status change names its status; only a person acts, takes, resolves and closes (constitution #6)
  check (type <> 'status_changed'
         or coalesce(payload ->> 'to', '') in ('verification', 'review', 'resolved', 'closed')),
  check (type not in ('analyst_action', 'assigned') or actor like 'analyst:%'),
  check (type <> 'status_changed' or coalesce(payload ->> 'to', '') not in ('resolved', 'closed')
         or actor like 'analyst:%'),
  -- visibility follows the §6.5 ✓ list
  check (customer_visible = (type not in ('action_verified', 'handoff_emitted', 'analyst_action')))
);

create table if not exists product_overrides (                                     -- AO; status = latest row_no of the same run_id
  override_id text primary key,                                      -- the action_id of the write (D-025)
  product_id text not null,
  status text not null check (status in ('Active', 'Blocked', 'Closed', 'Suspended')),
  case_id text not null,
  actor text not null check (actor in ('agent', 'customer', 'system')
    or actor ~ '(?p)^analyst:.*[^\t\n\v\f\r\u001c-\u001f \u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000].*$'),
  run_id text null,
  created_at timestamptz not null default now(),
  row_no bigint not null generated always as identity                -- insertion order: "latest" (T9)
);

create table if not exists notifications (                                         -- AO
  notification_id text primary key,
  case_id text not null,
  customer_id text not null,
  event text not null,
  channel text not null check (channel in ('log', 'telegram', 'email')),
  masked_address text null,
  text text not null,
  trigger text not null check (trigger in ('auto', 'on_request')),
  provider_message_id text null,
  created_at timestamptz not null default now()
);

create table if not exists notification_deliveries (                               -- AO; delivery status = latest row_no
  delivery_id text primary key,
  notification_id text not null references notifications (notification_id),
  status text not null check (status in ('queued', 'sent', 'delivered', 'bounced', 'failed')),
  provider_event jsonb null,
  created_at timestamptz not null default now(),
  row_no bigint not null generated always as identity                -- insertion order: "latest" (T9)
);

create table if not exists customer_channels (                                     -- AO; latest row_no per channel wins
  channel_id text primary key,
  customer_id text not null,
  channel text not null,
  address text not null,
  event text not null check (event in ('linked', 'confirmed', 'revoked')),
  created_at timestamptz not null default now(),
  row_no bigint not null generated always as identity                -- insertion order: "latest" (T9)
);

create table if not exists call_requests (                           -- AO; a call asked for with no case (D-026)
  event_id text primary key,                                         -- the E- id request_call returns
  action_id text not null check (action_id ~ '^A-[0-9A-F]{12}$'),    -- used once (the store checks it)
  customer_id text not null,
  session_id text not null,
  preferred_time text null,
  expected_contact_by date null,                                     -- D-008: stored, never recomputed
  run_id text null,
  trace_id text not null,
  created_at timestamptz not null default now()
);

create table if not exists link_tokens (                                           -- one-time
  token text primary key,
  case_id text not null,
  channel text not null,
  expires_at timestamptz not null,
  used_at timestamptz null
);

create table if not exists idempotency (                                           -- key prefixed with run_id when present
  key text primary key,
  action text not null,
  result jsonb not null,
  run_id text null,
  created_at timestamptz not null default now(),
  args_hash text not null                                            -- sha256 of the call's arguments: a reused key must match
);

create table if not exists policy_denials (                                        -- AO
  denial_id text primary key,
  trace_id text not null,
  session_id text null,                                              -- null for api and analyst denials (D-023)
  actor text not null check (actor in ('agent', 'customer')
    or actor ~ '(?p)^analyst:.*[^\t\n\v\f\r\u001c-\u001f \u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000].*$'),
  policy_id text not null,
  guardrail_id text not null,                                        -- a rule-only denial cites G-POL-01
  detail jsonb not null,
  run_id text null,
  created_at timestamptz not null default now()
);

create table if not exists llm_calls (                                             -- AO
  call_id text primary key,
  trace_id text not null,
  provider text not null,
  model text not null,
  tokens_in integer not null,
  tokens_out integer not null,
  latency_ms integer not null,
  cost_usd numeric not null,
  run_id text null,                                                  -- a run's tokens and cost sum alone (D-023)
  created_at timestamptz not null default now()
);

create table if not exists settings_events (                                       -- AO; supervised_mode = latest row_no
  event_id text primary key,
  key text not null,
  value jsonb not null,
  actor text not null,
  created_at timestamptz not null default now(),
  row_no bigint not null generated always as identity                -- insertion order: "latest" (T9)
);

-- postgres-only: the action-id index and the append-only guard. The offline DuckDB check stops at this line.
-- A customer write's action id is written once, so one read never verifies two actions (D-025).
create unique index if not exists case_events_action_id_once on case_events ((payload ->> 'action_id'))
  where type in ('case_opened', 'card_blocked', 'customer_info_added', 'call_requested', 'reevaluation_requested',
                 'notification_sent');
-- A call request's action id is used once too (D-026).
create unique index if not exists call_requests_action_id_once on call_requests (action_id);
create index if not exists demo_transactions_run on demo_transactions (customer_id, run_id);   -- a run's charges

create or replace function forbid_append_only_change() returns trigger language plpgsql as $$
begin
  raise exception '% is append-only: % is not allowed', tg_table_name, tg_op;
end $$;

do $$
declare t text;
begin
  foreach t in array array['cases', 'case_events', 'product_overrides', 'notifications', 'notification_deliveries',
                           'customer_channels', 'call_requests', 'idempotency', 'policy_denials', 'llm_calls',
                           'settings_events'] loop
    if not exists (select 1 from pg_trigger where tgrelid = to_regclass(t) and tgname = t || '_append_only') then
      execute format('create trigger %I before update or delete or truncate on %I '
                     'for each statement execute function forbid_append_only_change()', t || '_append_only', t);
    end if;
  end loop;
end $$;
