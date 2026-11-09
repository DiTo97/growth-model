-- Warehouse-native segmentation (Postgres dialect; adapt date functions for BigQuery/Snowflake/ClickHouse).
-- Input:  :activity — any relation with (user_id, day) at one row per active user-day, e.g.
--           select distinct person_id as user_id, timestamp::date as day from posthog_events
-- Output: one row per (day, segment) with user counts, identical to growth_model_core.segment_users
--         with Windows(week=7, month=30). Feed the transition counts into the core library to fit rates.

with activity as (
  select distinct user_id, day from activity_days     -- replace with your source
),
bounds as (
  select user_id, min(day) as first_seen from activity group by user_id
),
calendar as (
  select cast(g.d as date) as day
  from generate_series(
    cast((select min(day) from activity) as timestamp),
    cast((select max(day) from activity) as timestamp),
    interval '1 day'
  ) as g(d)
),
user_days as (
  -- every day from each user's first activity onward
  select b.user_id, c.day
  from bounds b join calendar c on c.day >= b.first_seen
),
with_last as (
  select
    ud.user_id,
    ud.day,
    (a.day is not null) as active_today,
    -- most recent active day strictly before today
    (select max(a2.day) from activity a2 where a2.user_id = ud.user_id and a2.day < ud.day) as prev_active,
    -- most recent active day up to and including today
    (select max(a3.day) from activity a3 where a3.user_id = ud.user_id and a3.day <= ud.day) as last_active
  from user_days ud
  left join activity a on a.user_id = ud.user_id and a.day = ud.day
),
segmented as (
  select
    user_id,
    day,
    case
      when active_today and prev_active is null                 then 'new'
      when active_today and day - prev_active <= 7              then 'current'
      when active_today and day - prev_active <= 30             then 'reactivated'
      when active_today                                         then 'resurrected'
      when day - last_active < 7                                then 'at_risk_wau'
      when day - last_active < 30                               then 'at_risk_mau'
      else                                                           'dormant'
    end as segment
  from with_last
)
-- Daily segment counts:
select day, segment, count(*) as users from segmented group by day, segment order by day, segment;

-- Transition counts (run instead of the final select above):
-- select s.day, p.segment as from_segment, s.segment as to_segment, count(*) as users
-- from segmented s join segmented p on p.user_id = s.user_id and p.day = s.day - 1
-- group by 1, 2, 3 order by 1, 2, 3;
