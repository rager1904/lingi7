"""
config/__init__.py
==================
Import the Celery application so it is initialised whenever Django starts.
This ensures all @shared_task decorators are registered correctly.
"""

from .celery import app as celery_app

__all__ = ("celery_app",)
