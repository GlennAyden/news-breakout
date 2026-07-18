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
