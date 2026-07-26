"""
apps/fraud/ml_scorer.py

XGBoost ML fraud scorer — Layer 2 of the fraud pipeline.

The scorer loads the model artifact from disk (or S3) at startup and
keeps it in memory. Inference is synchronous and must complete < 50ms.

Document Ref: LG7-BE-008
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from django.conf import settings

logger = logging.getLogger(__name__)

# Default freeze threshold — configurable via settings
DEFAULT_FREEZE_THRESHOLD = Decimal("0.65")


@dataclass(frozen=True)
class MLScorerResult:
    """Result from XGBoost fraud scorer."""

    risk_score: Decimal  # 0.0000 – 1.0000
    freeze_threshold: Decimal
    should_freeze: bool
    shap_values: dict[str, float]  # feature_name → shap_value
    model_version: str


class MLScorer:
    """
    XGBoost fraud risk scorer.

    Loads model artifact at first call (lazy init) and caches it in memory.
    Thread-safe for concurrent Django/Celery workers.

    Model is NOT loaded in __init__ — loading happens on first .score() call
    to avoid startup failures when the model file hasn't been placed yet
    (e.g. fresh dev environment).
    """

    _model: Any = None  # xgboost.Booster, loaded lazily
    _model_version: str = "unloaded"

    @classmethod
    def _load_model(cls) -> Any:
        """
        Load XGBoost model from disk path specified in settings.

        Returns:
            xgboost.Booster instance.

        Raises:
            RuntimeError: If model file not found or loading fails.
        """
        if cls._model is not None:
            return cls._model

        model_path = getattr(settings, "FRAUD_ML_MODEL_PATH", None)
        if not model_path:
            raise RuntimeError(
                "FRAUD_ML_MODEL_PATH not configured in settings. "
                "ML scorer cannot operate without a trained model."
            )

        model_file = Path(model_path)
        if not model_file.exists():
            raise RuntimeError(
                f"Fraud ML model not found at {model_path}. "
                "Run ml/fraud/train.py to generate the model artifact."
            )

        try:
            import xgboost as xgb  # noqa: F401

            booster = xgb.Booster()
            booster.load_model(str(model_file))
            cls._model = booster
            # Extract version from filename: fraud_model_v3.json → "v3"
            cls._model_version = model_file.stem.split("_")[-1] if "_" in model_file.stem else "v1"
            logger.info("Fraud ML model loaded", extra={"path": str(model_path), "version": cls._model_version})
            return cls._model
        except ImportError as exc:
            raise RuntimeError("xgboost package not installed. Run: pip install xgboost") from exc
        except Exception as exc:
            raise RuntimeError(f"Failed to load fraud ML model: {exc}") from exc

    @classmethod
    def score(cls, features: list[float], feature_names: list[str]) -> MLScorerResult:
        """
        Run XGBoost inference on the provided feature vector.

        Args:
            features: Ordered list of floats from MLFeatures.to_list().
            feature_names: Names in same order, from MLFeatures.feature_names().

        Returns:
            MLScorerResult with risk score and SHAP values.

        Raises:
            RuntimeError: If model is unavailable.
        """
        import xgboost as xgb

        booster = cls._load_model()
        freeze_threshold = Decimal(
            str(getattr(settings, "FRAUD_ML_FREEZE_THRESHOLD", DEFAULT_FREEZE_THRESHOLD))
        )

        dmatrix = xgb.DMatrix([features], feature_names=feature_names)
        raw_score = float(booster.predict(dmatrix)[0])
        risk_score = Decimal(str(round(raw_score, 4)))

        # SHAP values for compliance explainability
        shap_values: dict[str, float] = {}
        try:
            shap_matrix = booster.predict(dmatrix, pred_contribs=True)
            # shap_matrix shape: (1, n_features + 1) — last column is bias
            for i, name in enumerate(feature_names):
                shap_values[name] = round(float(shap_matrix[0][i]), 6)
        except Exception:
            logger.warning("SHAP computation failed — proceeding without explainability")

        return MLScorerResult(
            risk_score=risk_score,
            freeze_threshold=freeze_threshold,
            should_freeze=risk_score >= freeze_threshold,
            shap_values=shap_values,
            model_version=cls._model_version,
        )

    @classmethod
    def invalidate_cache(cls) -> None:
        """Force model reload on next .score() call. Used after model promotion."""
        cls._model = None
        cls._model_version = "unloaded"
        logger.info("ML model cache invalidated — will reload on next inference")
