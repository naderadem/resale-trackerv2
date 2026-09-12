"""Discord webhook alerting for flagged listings.

Sends one message per qualifying listing (deal or suspicious) to a Discord
webhook. `dry_run=True` prints the message instead -- no network call at
all, useful for checking what would be sent before wiring up a real
webhook. Deduplication (never alerting on the same listing twice) is not
this module's job -- it's a property of *which listings get sent here*,
tracked via the sent_alerts table (see db/repository.py's
has_been_alerted/record_alert and main.py's `alert` command, which check
before calling send()).
"""
import os
from datetime import datetime
from typing import Optional

import httpx

from pricing import PriceStats


class DiscordAlertError(Exception):
    """Raised when Discord webhook delivery fails."""


def format_alert_message(
    listing_title: str,
    listing_price: float,
    listing_url: str,
    classification: str,
    canonical_item_label: str,
    stats: PriceStats,
) -> str:
    """Build the Discord message text for one flagged listing."""
    emoji = "\U0001f6a9" if classification == "suspicious" else "\U0001f4b0"  # 🚩 / 💰
    return (
        f"{emoji} **{classification.upper()}**: {canonical_item_label}\n"
        f"${listing_price:.2f} (median ${stats.median:.2f}, n={stats.count}) -- {listing_title}\n"
        f"{listing_url}"
    )


class DiscordAlertSender:
    """Sends (or, in dry-run mode, prints) one Discord webhook message per alert."""

    def __init__(self, webhook_url: Optional[str] = None, dry_run: bool = False):
        self.dry_run = dry_run
        self.webhook_url = webhook_url or os.environ.get("DISCORD_WEBHOOK_URL")
        if not self.dry_run and not self.webhook_url:
            raise ValueError(
                "DISCORD_WEBHOOK_URL must be set (env var or constructor arg), "
                "or construct with dry_run=True."
            )
        self._client = httpx.Client(timeout=10.0)

    def send(self, message: str) -> None:
        """Send `message` to the webhook, or print it if dry_run."""
        if self.dry_run:
            print(f"[DRY RUN] Would send Discord alert at {datetime.now().isoformat()}:")
            print(message)
            print()
            return

        try:
            response = self._client.post(self.webhook_url, json={"content": message})
        except httpx.HTTPError as exc:
            raise DiscordAlertError(f"Failed to reach Discord webhook: {exc}") from exc

        if response.status_code >= 300:
            raise DiscordAlertError(
                f"Discord webhook returned {response.status_code}: {response.text}"
            )
