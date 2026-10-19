"""
Desktop Notifier: Delivers native macOS notifications for high-match job opportunities.
Uses built-in osascript with graceful fallback.
"""

from __future__ import annotations

import logging
import platform
import subprocess
from typing import Optional
from job_hunter.models import ScoredJob

logger = logging.getLogger(__name__)


class DesktopNotifier:
    """Dispatches native desktop notifications. Disabled by default to prevent UI disruption."""

    ENABLED: bool = False

    @classmethod
    def notify(cls, title: str, subtitle: str, message: str, sound: bool = True) -> bool:
        if not cls.ENABLED:
            logger.debug(f"[Notification Disabled] {title} - {subtitle}: {message}")
            return False

        if platform.system() != "Darwin":
            logger.info(f"[Notification] {title} - {subtitle}: {message}")
            return False

        try:
            # Escape double quotes for AppleScript
            t = title.replace('"', '\\"')
            sub = subtitle.replace('"', '\\"')
            msg = message.replace('"', '\\"')
            sound_clause = ' sound name "Glass"' if sound else ""

            script = f'display notification "{msg}" with title "{t}" subtitle "{sub}"{sound_clause}'
            subprocess.run(["osascript", "-e", script], check=False, capture_output=True, timeout=3.0)
            return True
        except Exception as e:
            logger.debug(f"Notification error: {e}")
            return False

    @classmethod
    def notify_job_match(cls, scored_job: ScoredJob, min_score_threshold: float = 0.70) -> bool:
        """Sends an alert if job fit score exceeds the threshold."""
        score_pct = int(round(scored_job.match.fit_score * 100))
        if scored_job.match.fit_score < min_score_threshold:
            return False

        title = "Ollaya Job Hunter 🎯"
        subtitle = f"{scored_job.job.title} @ {scored_job.job.company}"
        message = f"Eşleşme: %{score_pct} ({scored_job.match.fit_level.upper()}) | Konum: {scored_job.job.location}"

        return cls.notify(title=title, subtitle=subtitle, message=message, sound=True)
