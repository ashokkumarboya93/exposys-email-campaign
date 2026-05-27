# RUNBOOK

## 1) Install and migrate

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
```

## 2) Start Redis

```bash
redis-server
```

## 3) Start Django API

```bash
gunicorn config.wsgi:application -c config/gunicorn.conf.py
# Local dev fallback:
# python manage.py runserver 0.0.0.0:8000
```

## 4) Start Celery workers (3 separate terminals)

### Process A: Email worker (async sender inside task)

```bash
celery -A config worker -Q email_sending -P solo --loglevel=info --max-tasks-per-child=10
```

### Process B: File + bulk worker

```bash
celery -A config worker -Q file_processing,bulk_ops,celery -P prefork --concurrency=4 --loglevel=info
```

### Process C: Beat scheduler

```bash
celery -A config beat --loglevel=info
```

## 5) Verification checklist

1. Login at `/login/` and confirm dashboard loads.
2. Upload a CSV/XLSX at `/upload/` and verify `/api/contacts/upload/<file_id>/progress/` updates every 1.5s.
3. Open `/contacts/` and confirm server-side pagination (`50/page`) and `Showing X-Y of N`.
4. Create a campaign at `/campaigns/` and launch it.
5. Verify launch API returns `202` quickly with `task_id`.
6. Verify `/api/campaigns/<id>/status/` updates every second while running.
7. Confirm Redis keys exist during send:
   - `campaign:<id>:sent`
   - `campaign:<id>:failed`
   - `campaign:<id>:total`
   - `campaign:<id>:status`
   - `campaign:<id>:results`
8. Kill/restart email worker during a run and relaunch task. Confirm task resumes DB write from Redis results without duplicate sends.
9. Trigger bulk delete from contacts UI and confirm response `202` + task polling through `/api/tasks/<task_id>/status/`.
10. Trigger contacts export and confirm async task returns `download_url` on success.

## 6) Performance defaults

- Brevo free: set `brevo_max_concurrent=30` in Settings.
- Brevo starter: set `brevo_max_concurrent=50`.
- SES sandbox: set `ses_max_concurrent=14`.
- SES production: raise `ses_max_concurrent` to approved sending rate.
