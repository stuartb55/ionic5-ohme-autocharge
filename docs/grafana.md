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
| `daily_stats`        | every `DAILY_STATS_INTERVAL` + on dashboard views | per-day energy / cost / savings |

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
SELECT stat_date AS "time", energy_kwh
FROM daily_stats
WHERE $__timeFilter(stat_date)
ORDER BY stat_date;
```

Cost & savings per day:

```sql
SELECT stat_date AS "time", cost, savings
FROM daily_stats
WHERE $__timeFilter(stat_date)
ORDER BY stat_date;
```

Recent charge sessions (table):

```sql
SELECT plugged_in_at, vehicle_name, soc_percent, target_percent, topup_percent, action, odometer_miles, soh_percent
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

Driving efficiency (miles per kWh) over the selected range — distance covered
between the first and last plug-in, divided by the energy charged in that
window (stat panel). Needs a couple of plug-ins with odometer data to be
meaningful:

```sql
SELECT
  (MAX(odometer_miles) - MIN(odometer_miles))::float
    / NULLIF((SELECT SUM(energy_kwh) FROM daily_stats WHERE $__timeFilter(stat_date)), 0)
    AS miles_per_kwh
FROM charge_sessions
WHERE $__timeFilter(plugged_in_at) AND odometer_miles IS NOT NULL;
```

Latest charge schedule (table):

```sql
SELECT s.recorded_at, s.next_slot_start, s.next_slot_end, s.slots
FROM schedule_snapshots s
ORDER BY s.recorded_at DESC
LIMIT 20;
```
