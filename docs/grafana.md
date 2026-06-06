# Grafana / Postgres history

When `DATABASE_URL` is set, the backend persists charging history to Postgres so
you can chart it in Grafana. Persistence is **optional** — leave `DATABASE_URL`
blank and the app runs entirely in memory exactly as before.

The bundled `docker-compose.yml` / `docker-compose.prod.yml` include a
`postgres:16-alpine` service (database `autocharge`, user `autocharge`) with the
port published on `5432` so an existing Grafana can query it directly.

## Datasource

In Grafana add a **PostgreSQL** datasource:

| Field    | Value                                  |
| -------- | -------------------------------------- |
| Host     | `<docker-host>:5432` (or `postgres:5432` if Grafana shares the compose network) |
| Database | `autocharge`                           |
| User     | `autocharge`                           |
| Password | `autocharge` (override `POSTGRES_PASSWORD` in prod) |
| TLS/SSL  | disable for the internal network       |

## Tables

| Table                | Written when                              | Use for |
| -------------------- | ----------------------------------------- | ------- |
| `telemetry`          | every poll (`POLL_INTERVAL`)              | power / energy / SOC time-series |
| `charge_sessions`    | once per plug-in event                    | when the car was plugged in and what target was set |
| `schedule_snapshots` | when a session is configured              | the Ohme charge schedule for a session |
| `daily_stats`        | every `DAILY_STATS_INTERVAL` + on dashboard views | per-day energy / cost / savings |

## Example panels

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
SELECT plugged_in_at, vehicle_name, soc_percent, target_percent, topup_percent, action
FROM charge_sessions
ORDER BY plugged_in_at DESC
LIMIT 50;
```

Latest charge schedule (table):

```sql
SELECT s.recorded_at, s.next_slot_start, s.next_slot_end, s.slots
FROM schedule_snapshots s
ORDER BY s.recorded_at DESC
LIMIT 20;
```
