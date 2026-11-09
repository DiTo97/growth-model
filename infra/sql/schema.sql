-- Postgres schema for growth-model-api. Mirrors apps/api/src/growth_model_api/db.py.
-- The API also creates these tables automatically on startup (dev convenience).

create table if not exists api_keys (
  id          bigserial primary key,
  key_hash    char(64)     not null unique,          -- sha256 of the raw key; raw keys are never stored
  prefix      varchar(32)  not null,
  kind        varchar(16)  not null check (kind in ('publishable', 'secret')),
  company_id  varchar(100) not null,
  product_id  varchar(100) not null,
  label       varchar(200) not null default '',
  created_at  timestamptz  not null default now(),
  revoked_at  timestamptz
);
create index if not exists ix_api_keys_prefix on api_keys (prefix);

create table if not exists members (
  subject     varchar(100) not null,                 -- Supabase auth.users.id (JWT sub)
  company_id  varchar(100) not null,
  product_id  varchar(100) not null,
  role        varchar(32)  not null default 'analyst',
  primary key (subject, company_id, product_id)
);

create table if not exists tracked_users (
  company_id  varchar(100) not null,
  product_id  varchar(100) not null,
  user_id     varchar(256) not null,
  first_seen  date         not null,
  primary key (company_id, product_id, user_id)
);

-- One row per tenant/user/UTC day: this is all the model needs.
create table if not exists activity_days (
  company_id  varchar(100) not null,
  product_id  varchar(100) not null,
  day         date         not null,
  user_id     varchar(256) not null,
  metadata    jsonb        not null default '{}',
  primary key (company_id, product_id, day, user_id)
);

create table if not exists segment_counts (
  company_id  varchar(100) not null,
  product_id  varchar(100) not null,
  day         date         not null,
  segment     varchar(32)  not null,
  users       integer      not null,
  primary key (company_id, product_id, day, segment)
);

create table if not exists transition_counts (
  company_id    varchar(100) not null,
  product_id    varchar(100) not null,
  day           date         not null,
  from_segment  varchar(32)  not null,
  to_segment    varchar(32)  not null,
  users         integer      not null,
  primary key (company_id, product_id, day, from_segment, to_segment)
);

create table if not exists rate_fits (
  id                      bigserial primary key,
  company_id              varchar(100) not null,
  product_id              varchar(100) not null,
  as_of                   date         not null,
  window_days             integer      not null,
  rates                   jsonb        not null,
  exposure                jsonb        not null,
  unexpected_transitions  integer      not null default 0,
  created_at              timestamptz  not null default now()
);
create index if not exists ix_rate_fits_tenant on rate_fits (company_id, product_id, as_of);
