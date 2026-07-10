# Grafana / Postgres history

When `DATABASE_URL` is set, the backend persists charging history to Postgres so
you can chart it in Grafana. Persistence is **optional** — leave `DATABASE_URL`
blank and the app runs entirely in memory exactly as before.

The bundled `docker-compose.yml` / `docker-compose.prod.yml` include a
`postgres:16-alpine` service (database `autocharge`, user `autocharge`) with the
port published on **loopback only** (`127.0.0.1:5432`) so a Grafana running on
the same host can query it directly without exposing the database to the LAN.
Set `POSTGRES_PASSWORD` in `.env` to change the password — the backend's
default `DATABASE_URL` picks it up automatically.

## Datasource

In Grafana add a **PostgreSQL** datasource:

| Field    | Value                                  |
| -------- | -------------------------------------- |
| Host     | `127.0.0.1:5432` from the docker host (or `postgres:5432` if Grafana shares the compose network) |
| Database | `autocharge`                           |
| User     | `autocharge`                           |
| Password | `POSTGRES_PASSWORD` from `.env` (default `autocharge`) |
| TLS/SSL  | disable for the internal network       |

## Tables

| Table                | Written when                              | Use for |
| -------------------- | ----------------------------------------- | ------- |
| `telemetry`          | every poll (`POLL_INTERVAL`)              | power / energy / SOC time-series |
| `charge_sessions`    | once per plug-in event                    | when the car was plugged in and what target was set |
| `schedule_snapshots` | when a session is configured              | the Ohme charge schedule for a session |
| `daily_stats`        | every `DAILY_STATS_INTERVAL` + on dashboard views | complete local-day energy in Wh and money in integer minor units (legacy float mirrors retained) |
| `grid_consumption`   | every `DAILY_STATS_INTERVAL` (when Octopus consumption is configured) | half-hourly whole-house import split into car vs rest-of-house |
| `session_events`     | target changes and other session lifecycle events | audit trail for each physical plug-in |
| `tariff_rates`       | every 30 minutes when Agile is enabled | durable tariff windows used for actual cost |
| `charging_intervals` | when a session finishes and reconciles | measured session Wh and integer-minor-unit cost by tariff interval |
| `ingestion_cursors`  | after a successful external-data upsert | resumable source progress and last-ingestion metadata |

Schema changes are versioned with Alembic and applied automatically at backend
startup. `charge_sessions.session_key` is the durable idempotency key for a
physical plug-in; new telemetry and event rows reference `charge_sessions.id`.
`GET /api/data-quality` exposes non-sensitive aggregate completeness counters
and cursor/cache freshness for a Grafana JSON/API datasource or external monitor.

## Ready-made dashboard

A complete dashboard is checked in at [`grafana-dashboard.json`](grafana-dashboard.json).
Import it via **Dashboards → New → Import → Upload JSON file**, then pick the
PostgreSQL datasource above when prompted. It surfaces, at a glance:

- **Live status** — battery SOC gauge, charging power, plug state, current
  session energy, amps/volts and the active charge target.
- **Charging trends** — power over time and battery SOC vs target.
- **Daily energy, cost & savings** — totals and blended £/kWh for the range,
  per-day bars and a cumulative-savings line.
- **Sessions & schedule** — plug-in counts, configured-vs-skipped outcomes, a
  recent-sessions table and the captured Ohme charge schedules.

The time range drives every panel (and the "Plug-in events" annotations on the
time-series), so use the picker to zoom from the last 24h to the last year.

## Example panels

The dashboard above is built from queries like these — handy if you want to add
your own panels.

Charging power over time (time-series):

```sql
SELECT recorded_at AS "time", power_watts
FROM telemetry
WHERE $__timeFilter(recorded_at)
ORDER BY recorded_at;
```

Battery SOC vs target:

```sql
SELECT recorded_at AS "time", battery_percent, target_percent
FROM telemetry
WHERE $__timeFilter(recorded_at)
ORDER BY recorded_at;
```

Energy charged per day (bar chart):

```sql
SELECT stat_date AS "time", energy_wh / 1000.0 AS energy_kwh
FROM daily_stats
WHERE $__timeFilter(stat_date) AND is_complete
ORDER BY stat_date;
```

Cost & savings per day:

```sql
SELECT stat_date AS "time",
       cost_minor / 100.0 AS cost,
       savings_minor / 100.0 AS savings
FROM daily_stats
WHERE $__timeFilter(stat_date) AND is_complete
ORDER BY stat_date;
```

Recent charge sessions (table):

```sql
SELECT plugged_in_at, vehicle_name, soc_percent, target_percent, topup_percent,
       actual_energy_wh / 1000.0 AS actual_kwh,
       actual_cost_minor / 100.0 AS actual_cost,
       cost_currency, tariff_coverage, quality_status,
       action, odometer_miles, soh_percent
FROM charge_sessions
ORDER BY plugged_in_at DESC
LIMIT 50;
```

Battery health (state of health) over time — a degradation trend (time
series). One point per plug-in that reported SoH:

```sql
SELECT plugged_in_at AS time, soh_percent
FROM charge_sessions
WHERE $__timeFilter(plugged_in_at) AND soh_percent IS NOT NULL
ORDER BY plugged_in_at;
```

Home-energy efficiency by vehicle over the selected range. Each session's final
charger energy is paired only with that same vehicle's odometer delta at its
next plug-in. Both ends must fall inside the range; missing energy, odometer
regressions and incomplete boundary intervals are excluded:

```sql
WITH paired AS (
  SELECT vehicle_id, plugged_in_at, odometer_miles, actual_energy_wh,
         LEAD(plugged_in_at) OVER w AS next_plugged_in_at,
         LEAD(odometer_miles) OVER w AS next_odometer_miles
  FROM charge_sessions
  WHERE vehicle_id IS NOT NULL
  WINDOW w AS (PARTITION BY vehicle_id ORDER BY plugged_in_at)
)
SELECT vehicle_id,
       SUM(next_odometer_miles - odometer_miles) * 1000.0
         / NULLIF(SUM(actual_energy_wh), 0) AS home_miles_per_kwh,
       COUNT(*) AS matched_intervals
FROM paired
WHERE plugged_in_at >= $__timeFrom() AND next_plugged_in_at <= $__timeTo()
  AND next_odometer_miles > odometer_miles AND actual_energy_wh > 0
GROUP BY vehicle_id;
```

Latest charge schedule (table):

```sql
SELECT s.recorded_at, s.next_slot_start, s.next_slot_end, s.slots
FROM schedule_snapshots s
ORDER BY s.recorded_at DESC
LIMIT 20;
```

House vs car electricity usage — half-hourly whole-house grid import broken into
the car-charging share and the rest of the household (stacked time series). Only
populated when `OCTOPUS_API_KEY` + `OCTOPUS_ACCOUNT_NUMBER` are set; the car
share is reconstructed from the `telemetry` history, so `DATABASE_URL` is
required too:

```sql
SELECT interval_start AS time,
       car_kwh AS "Car",
       house_kwh AS "Rest of house",
       unattributed_kwh AS "Unattributed"
FROM grid_consumption
WHERE $__timeFilter(interval_start)
ORDER BY interval_start;
```

Daily totals — car vs rest-of-house energy per day (bar chart):

```sql
SELECT
  date_trunc('day', interval_start) AS time,
  SUM(car_kwh)   AS "Car",
  SUM(house_kwh) AS "Rest of house",
  SUM(unattributed_kwh) AS "Unattributed"
FROM grid_consumption
WHERE $__timeFilter(interval_start)
GROUP BY 1
ORDER BY 1;
```
