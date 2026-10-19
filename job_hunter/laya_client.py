"""
Laya Decision Engine Client: Speaks TypeSafe-compatible /v1/systemone wire format.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class LayaClient:
    def __init__(self, host: str = "http://127.0.0.1:11435", default_model: str = "laya"):
        self.host = host.rstrip("/")
        self.default_model = default_model

    def is_available(self) -> bool:
        """Check if the local Ollaya daemon is reachable."""
        try:
            req = urllib.request.Request(f"{self.host}/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                return resp.status == 200
        except Exception:
            return False

    def decide(
        self,
        state: str | Dict[str, Any],
        questions: Dict[str, Any],
        model: Optional[str] = None,
        timeout: float = 15.0,
    ) -> Dict[str, Any]:
        """
        Send a state + typed questions request to Ollaya.
        Returns the raw parsed response containing 'answers'.
        """
        target_model = model or self.default_model
        payload = {
            "model": target_model,
            "state": state,
            "questions": questions,
        }

        url = f"{self.host}/v1/systemone"
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw)
        except urllib.error.URLError as e:
            msg = (
                f"Ollaya daemon unreachable at {self.host} ({e}). "
                "Ensure Ollaya is running via: 'ollaya serve'"
            )
            logger.error(msg)
            raise ConnectionError(msg) from e
        except Exception as e:
            logger.error(f"Error querying Ollaya decision API: {e}")
            raise
