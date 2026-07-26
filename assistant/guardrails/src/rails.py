"""Content safety guardrails using open source Llama Guard model.

Replaces NeMo Guardrails with direct calls to Llama Guard 3 8B
served via an OpenAI-compatible endpoint (vLLM).
"""
import os
import logging
from openai import OpenAI

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class GuardRails:
    def __init__(self, config_path: str = None):
        base_url = os.environ.get(
            "GUARDRAILS_MODEL_URL",
            "http://llama-guard:8000/v1"
        )
        api_key = os.environ.get("API_KEY", "sk-placeholder")
        self.model = os.environ.get(
            "GUARDRAILS_MODEL_NAME",
            "meta-llama/Llama-Guard-3-8B"
        )
        self.client = OpenAI(base_url=base_url, api_key=api_key)
        logger.info(
            f"GuardRails initialized with model={self.model} url={base_url}"
        )

    def _check(self, messages: list) -> dict:
        """Run content through Llama Guard and return the result."""
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.0,
                max_tokens=50,
            )
            content = response.choices[0].message.content.strip()
            is_safe = "safe" in content.lower()
            logger.info(f"GuardRails check: {content} -> safe={is_safe}")
            return {
                "response": [
                    {
                        "role": "assistant",
                        "content": messages[-1]["content"]
                        if is_safe
                        else "I cannot respond to that request.",
                    }
                ],
                "is_safe": is_safe,
            }
        except Exception as e:
            logger.error(f"GuardRails check failed: {e}")
            return {
                "response": [
                    {"role": "assistant", "content": messages[-1]["content"]}
                ],
                "is_safe": True,
            }

    def call_input_content_rails(self, user_input: str):
        messages = [
            {"role": "user", "content": user_input},
        ]
        return self._check(messages)

    def call_output_content_rails(self, bot_response: str):
        messages = [
            {"role": "assistant", "content": bot_response},
        ]
        return self._check(messages)


config_path = os.path.join(
    os.environ.get("SHARED_CONFIG_ROOT", "/app/shared/configs"), "rails"
)
guardRails = GuardRails(config_path)


class Rails:
    def getGuardRails(self):
        return guardRails
