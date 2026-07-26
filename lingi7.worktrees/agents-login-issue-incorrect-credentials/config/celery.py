"""
config/celery.py
================
Celery application instance for Lingi7.

Queues:
  default       — general tasks (reconciliation, order timers)
  payments      — payment initiation and webhook processing (higher priority)
  notifications — email and SMS dispatch
  fraud         — fraud scoring and ML inference

Start workers with:
  celery -A config worker --queues=default,payments,notifications,fraud -l info
Start beat with:
  celery -A config beat --scheduler django_celery_beat.schedulers:DatabaseScheduler -l info
"""

import os

from celery import Celery

# Default to dev settings — overridden in production via env var
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

app = Celery("lingi7")

# Load Celery config from Django settings using the CELERY_ namespace
app.config_from_object("django.conf:settings", namespace="CELERY")

# Autodiscover tasks from all INSTALLED_APPS
# Celery will look for a tasks.py module in each app
app.autodiscover_tasks()


@app.task(bind=True, ignore_result=True)
def debug_task(self) -> None:
    """Diagnostic task — confirms Celery is running correctly."""
    print(f"Request: {self.request!r}")
