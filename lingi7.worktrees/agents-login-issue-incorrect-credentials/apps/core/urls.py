"""
apps/core/urls.py
=================
Health check URL — used by Docker, Uptime Robot, and load balancers.
"""

from django.urls import path

from . import views

urlpatterns = [
    path("", views.health_check, name="health-check"),
]
