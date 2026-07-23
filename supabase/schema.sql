-- supabase/schema.sql — paste into Supabase SQL Editor once.
create table if not exists price_bars (
  ticker   text        not null,
  interval text        not null,   -- '1d' or '60m'
  ts       timestamptz not null,
  open     double precision,
  high     double precision,
  low      double precision,
  close    double precision,
  volume   bigint,
  primary key (ticker, interval, ts)
);
create index if not exists price_bars_lookup on price_bars (ticker, interval, ts desc);

-- Phase-1 parallel table: Ajaib OHLCV lands here for accuracy comparison
-- against price_bars (yfinance). Same shape as price_bars.
create table if not exists price_bars_ajaib (
  ticker   text        not null,
  interval text        not null,   -- '1d' or '60m'
  ts       timestamptz not null,
  open     double precision,
  high     double precision,
  low      double precision,
  close    double precision,
  volume   bigint,
  primary key (ticker, interval, ts)
);
create index if not exists price_bars_ajaib_lookup on price_bars_ajaib (ticker, interval, ts desc);

-- Single-row store for the current Ajaib refresh token, so the GitHub Actions
-- fetcher survives token rotation unattended. id is always 1.
create table if not exists ajaib_token (
  id            int primary key default 1,
  refresh_token text not null,
  updated_at    timestamptz not null default now()
);
