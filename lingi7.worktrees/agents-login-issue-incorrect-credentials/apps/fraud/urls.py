"""
apps/fraud/urls.py

Internal fraud API endpoints. NOT exposed publicly.
All endpoints require staff authentication.

Document Ref: LG7-BE-008
"""

from django.urls import path

from apps.fraud import views

app_name = "fraud"

urlpatterns = [
    # Internal: run fraud pipeline on demand (staff/admin only)
    path("internal/fraud/score/", views.FraudScoreView.as_view(), name="score"),
]
