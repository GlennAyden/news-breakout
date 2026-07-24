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
-- (The ajaib_token refresh-token table was dropped: Ajaib's access token is
-- short-lived and cannot be refreshed unattended, so the Ajaib puller is
-- on-demand with a freshly-exported token via AJAIB_ACCESS_TOKEN, not a stored
-- refresh token. If you already created ajaib_token, you can `drop table ajaib_token;`.)
