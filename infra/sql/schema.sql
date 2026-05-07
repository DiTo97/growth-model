create table if not exists activity_events (
  id bigserial primary key,
  company_id text not null,
  product_id text not null,
  user_id text not null,
  occurred_at timestamptz not null,
  metadata jsonb not null,
  created_at timestamptz not null default now()
);

create index if not exists idx_activity_company_time on activity_events(company_id, occurred_at);
create index if not exists idx_activity_product on activity_events(product_id);

create table if not exists api_keys (
  id bigserial primary key,
  api_key text not null unique,
  company_id text not null,
  product_id text not null,
  product_version text not null default 'v1',
  is_active int not null default 1,
  created_at timestamptz not null default now()
);

create index if not exists idx_api_keys_scope on api_keys(company_id, product_id);

create table if not exists daily_state_snapshots (
  id bigserial primary key,
  company_id text not null,
  day date not null,
  segment text not null,
  user_count int not null,
  created_at timestamptz not null default now()
);

create index if not exists idx_snapshot_company_day on daily_state_snapshots(company_id, day);

create table if not exists weekly_transition_rates (
  id bigserial primary key,
  company_id text not null,
  day date not null,
  from_segment text not null,
  to_segment text not null,
  rate double precision not null,
  created_at timestamptz not null default now()
);

create index if not exists idx_rates_company_day on weekly_transition_rates(company_id, day);
