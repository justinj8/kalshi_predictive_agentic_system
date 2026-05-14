# Railway Deployment

Deploy this project as two Railway services that share the same Postgres database.

## Dashboard service

Use the default service command from `railway.toml`:

```bash
uvicorn src.dashboard.app:app --host 0.0.0.0 --port ${PORT:-8000}
```

Required variables:

```bash
DATABASE_URL=<Railway Postgres connection string>
DASHBOARD_USERNAME=admin
DASHBOARD_PASSWORD=<strong password>
TRADING_MODE=paper
```

## Cron worker service

Create a separate Railway service from the same repo and configure a cron schedule.
Use this command:

```bash
python src/main.py --once
```

Recommended first cadence:

```text
*/30 * * * 1-5
```

That runs every 30 minutes, Monday through Friday, in UTC. Keep `TRADING_MODE=paper`
until paper results are calibrated and the dashboard confirms stable execution.

## Notes

- Use Railway Postgres for persistence; do not rely on local SQLite for deployed runs.
- The app normalizes Railway `postgres://` URLs to SQLAlchemy `postgresql://`.
- The dashboard is read-only and protected by HTTP Basic credentials.
- The cron worker exits after one cycle, which is required for Railway cron jobs.
