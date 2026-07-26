"""
apps/fraud/views.py

Internal fraud API views. Thin views — all logic in FraudPipeline.

Document Ref: LG7-BE-008
"""

from __future__ import annotations

from rest_framework import status
from rest_framework.permissions import IsAdminUser
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.fraud.pipeline import FraudPipeline


class FraudScoreView(APIView):
    """
    POST /internal/fraud/score/

    Run the full fraud pipeline for a given order_id.
    Internal use only — called by escrow service and admin tooling.
    Not exposed through the public API router.
    """

    permission_classes = [IsAdminUser]

    def post(self, request: Request) -> Response:
        order_id = request.data.get("order_id")
        if not order_id:
            return Response({"error": "order_id is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            verdict = FraudPipeline.run(order_id=int(order_id))
        except Exception as exc:
            return Response(
                {"error": f"Pipeline failed: {exc}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(
            {
                "order_id": verdict.order_id,
                "verdict": verdict.verdict_label,
                "should_freeze": verdict.should_freeze,
                "triggered_rules": verdict.triggered_rule_codes,
                "ml_risk_score": str(verdict.ml_risk_score) if verdict.ml_risk_score else None,
            },
            status=status.HTTP_200_OK,
        )
