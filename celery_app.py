"""Celery app bootstrap and queue routing."""
import os

from celery import Celery
from celery.schedules import crontab
from kombu import Exchange, Queue

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("exposys_campaign")
app.config_from_object("django.conf:settings", namespace="CELERY")

app.conf.task_queues = (
    Queue("email_sending", Exchange("email_sending", type="direct"), routing_key="email_sending"),
    Queue("file_processing", Exchange("file_processing", type="direct"), routing_key="file_processing"),
    Queue("bulk_ops", Exchange("bulk_ops", type="direct"), routing_key="bulk_ops"),
    Queue("celery", Exchange("celery", type="direct"), routing_key="celery"),
)

app.conf.task_default_queue = "celery"
app.conf.task_default_exchange = "celery"
app.conf.task_default_routing_key = "celery"

app.conf.task_routes = {
    "apps.campaigns.tasks.launch_campaign_task": {"queue": "email_sending", "routing_key": "email_sending"},
    "apps.contacts.tasks.process_uploaded_file": {"queue": "file_processing", "routing_key": "file_processing"},
    "apps.contacts.tasks.bulk_delete_contacts": {"queue": "bulk_ops", "routing_key": "bulk_ops"},
    "apps.contacts.tasks.generate_contacts_export": {"queue": "bulk_ops", "routing_key": "bulk_ops"},
    "apps.analytics.tasks.aggregate_daily_analytics": {"queue": "celery", "routing_key": "celery"},
    "apps.analytics.tasks.aggregate_campaign_analytics": {"queue": "celery", "routing_key": "celery"},
}

app.conf.task_acks_late = True
app.conf.task_reject_on_worker_lost = True
app.conf.task_track_started = True
app.conf.worker_prefetch_multiplier = 1
app.conf.result_expires = 3600

app.conf.beat_schedule = {
    "aggregate-daily-analytics": {
        "task": "apps.analytics.tasks.aggregate_daily_analytics",
        "schedule": crontab(hour=0, minute=0),
        "options": {"queue": "celery"},
    },
}

app.autodiscover_tasks()
