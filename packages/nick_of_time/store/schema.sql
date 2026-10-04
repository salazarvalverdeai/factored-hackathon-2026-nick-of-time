-- Nick of Time — Postgres schema of spec 01 §6.5 (ADR 0010). apps/api/migrations adopts this file as its first
-- migration (D-002); tests/test_spec01_store_schema.py keeps it in step with the spec table.
-- Conventions [assumption]: a column the spec leaves untyped is text (timestamps timestamptz, counters integer); a
-- column is not null unless the spec marks it null. Rows are never updated or deleted in the append-only (AO) tables.

create table sessions (
  session_id text primary key,
  customer_id text null,
  otp_hash text not null,
  verified_at timestamptz null,
  expires_at timestamptz not null,
  language text not null,
  mode text not null check (mode in ('replay', 'live')),            -- fixed at creation (AC-07)
  display_currency text null,
  tool_faults text[] not null default array[]::text[],
  run_id text null,                                                  -- run_id and arm: eval seed only (§6.8)
  arm text null,
  created_at timestamptz not null default now()
);

create table cases (                                                 -- AO, insert-only; status = last event
  case_id text primary key,                                          -- K- + 6 digits: the insert retries (T9)
  customer_id text not null,
  transaction_id text not null,
  product_id text not null,
  country text not null,
  product_type text not null,
  zone text not null,
  dispute_type text not null,
  opened_on date not null,                                           -- business date (D-023)
  credit_deadline date null,                                         -- stored once, never recomputed
  ruling_deadline date null,
  deadline_source text null,
  deadline_source_url text null,
  deadline_verified_on date null,                                    -- [assumption] D-014
  related_case_id text null,
  mode text not null,
  run_id text null,
  trace_id text not null,
  created_at timestamptz not null default now(),
  -- a legal date travels with its source, an https:// URL and the date it was verified (§6.6, ADR 0019, D-014)
  check ((credit_deadline is null and ruling_deadline is null)
         or (deadline_source is not null and deadline_source_url like 'https://%'
             and deadline_verified_on is not null))
);

create table demo_transactions (                                     -- live mode only; gold transactions columns
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
  synthetic boolean not null default true check (synthetic),
  scenario text not null,
  generated_at timestamptz not null default now()
);

create table case_events (                                           -- AO
  event_id text primary key,
  case_id text not null references cases (case_id),
  seq integer not null,
  type text not null check (type in ('case_opened', 'card_blocked', 'block_verified', 'action_verified',
    'status_changed', 'handoff_emitted', 'assigned', 'analyst_action', 'customer_info_added', 'call_requested',
    'reevaluation_requested', 'related_case_opened', 'notification_sent', 'receipt_issued', 'telegram_linked',
    'email_confirmed')),
  actor text not null,
  payload jsonb not null default '{}',
  customer_visible boolean not null,
  trace_id text not null,
  created_at timestamptz not null default now(),
  unique (case_id, seq)
);

create table product_overrides (                                     -- AO; status = latest row of the same run_id
  override_id text primary key,                                      -- the action_id of the write (D-025)
  product_id text not null,
  status text not null,
  case_id text not null,
  actor text not null,
  run_id text null,
  created_at timestamptz not null default now()
);

create table notifications (                                         -- AO
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

create table notification_deliveries (                               -- AO; delivery status = latest row
  delivery_id text primary key,
  notification_id text not null references notifications (notification_id),
  status text not null check (status in ('queued', 'sent', 'delivered', 'bounced', 'failed')),
  provider_event jsonb null,
  created_at timestamptz not null default now()
);

create table customer_channels (                                     -- AO; latest row per channel wins
  channel_id text primary key,
  customer_id text not null,
  channel text not null,
  address text not null,
  event text not null check (event in ('linked', 'confirmed', 'revoked')),
  created_at timestamptz not null default now()
);

create table link_tokens (                                           -- one-time
  token text primary key,
  case_id text not null,
  channel text not null,
  expires_at timestamptz not null,
  used_at timestamptz null
);

create table idempotency (                                           -- key prefixed with run_id when present
  key text primary key,
  action text not null,
  result jsonb not null,
  run_id text null,
  created_at timestamptz not null default now()
);

create table policy_denials (                                        -- AO
  denial_id text primary key,
  trace_id text not null,
  session_id text null,                                              -- null for api and analyst denials (D-023)
  actor text not null check (actor in ('agent', 'customer') or actor like 'analyst:_%'),
  policy_id text not null,
  guardrail_id text not null,                                        -- a rule-only denial cites G-POL-01
  detail jsonb not null,
  run_id text null,
  created_at timestamptz not null default now()
);

create table llm_calls (                                             -- AO
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

create table settings_events (                                       -- AO; supervised_mode = latest
  event_id text primary key,
  key text not null,
  value jsonb not null,
  actor text not null,
  created_at timestamptz not null default now()
);

-- postgres-only: the append-only guard. The offline DuckDB check stops at this line.
create function forbid_append_only_change() returns trigger language plpgsql as $$
begin
  raise exception '% is append-only: % is not allowed', tg_table_name, tg_op;
end $$;

do $$
declare t text;
begin
  foreach t in array array['cases', 'case_events', 'product_overrides', 'notifications', 'notification_deliveries',
                           'customer_channels', 'policy_denials', 'llm_calls', 'settings_events'] loop
    execute format('create trigger %I before update or delete or truncate on %I '
                   'for each statement execute function forbid_append_only_change()', t || '_append_only', t);
  end loop;
end $$;
