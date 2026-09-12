"""Alerting tests. The Discord webhook is always mocked -- these must
never make a real HTTP request.
"""
from datetime import datetime, timezone
from unittest.mock import MagicMock

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from alerting import DiscordAlertError, DiscordAlertSender, format_alert_message
from db.models import Base, CanonicalItem, ListingRecord
from db.repository import has_been_alerted, record_alert
from pricing import PriceStats


class TestFormatAlertMessage:
    def test_deal_message_contains_key_fields(self):
        stats = PriceStats(median=1000.0, p25=800.0, count=8)
        message = format_alert_message(
            listing_title="Rick Owens Geobasket size 42",
            listing_price=650.0,
            listing_url="https://example.com/listing/1",
            classification="deal",
            canonical_item_label="Rick Owens Geobasket",
            stats=stats,
        )
        assert "DEAL" in message
        assert "650.00" in message
        assert "1000.00" in message
        assert "Rick Owens Geobasket" in message
        assert "https://example.com/listing/1" in message

    def test_suspicious_message_uses_different_marker_than_deal(self):
        stats = PriceStats(median=1000.0, p25=800.0, count=8)
        deal_msg = format_alert_message(
            "t", 650.0, "u", "deal", "item", stats
        )
        suspicious_msg = format_alert_message(
            "t", 300.0, "u", "suspicious", "item", stats
        )
        assert "SUSPICIOUS" in suspicious_msg
        assert "DEAL" in deal_msg
        assert deal_msg != suspicious_msg


class TestDiscordAlertSenderDryRun:
    def test_dry_run_never_calls_httpx(self, capsys):
        sender = DiscordAlertSender(dry_run=True)
        sender._client.post = MagicMock()  # would fail the test if called

        sender.send("test alert message")

        sender._client.post.assert_not_called()
        captured = capsys.readouterr()
        assert "DRY RUN" in captured.out
        assert "test alert message" in captured.out

    def test_dry_run_does_not_require_webhook_url(self):
        # Must not raise even with no DISCORD_WEBHOOK_URL configured.
        DiscordAlertSender(webhook_url=None, dry_run=True)

    def test_real_mode_without_webhook_url_raises(self, monkeypatch):
        monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
        with pytest.raises(ValueError):
            DiscordAlertSender(webhook_url=None, dry_run=False)


class TestDiscordAlertSenderRealSend:
    def test_successful_send_posts_content_to_webhook(self):
        sender = DiscordAlertSender(webhook_url="https://discord.com/api/webhooks/fake", dry_run=False)
        ok_response = MagicMock(spec=httpx.Response)
        ok_response.status_code = 204
        mock_post = MagicMock(return_value=ok_response)
        sender._client.post = mock_post

        sender.send("hello discord")

        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert args[0] == "https://discord.com/api/webhooks/fake"
        assert kwargs["json"] == {"content": "hello discord"}

    def test_non_2xx_response_raises(self):
        sender = DiscordAlertSender(webhook_url="https://discord.com/api/webhooks/fake", dry_run=False)
        bad_response = MagicMock(spec=httpx.Response)
        bad_response.status_code = 404
        bad_response.text = "Unknown Webhook"
        sender._client.post = MagicMock(return_value=bad_response)

        with pytest.raises(DiscordAlertError):
            sender.send("hello discord")

    def test_network_error_raises_discord_alert_error(self):
        sender = DiscordAlertSender(webhook_url="https://discord.com/api/webhooks/fake", dry_run=False)
        sender._client.post = MagicMock(side_effect=httpx.ConnectError("boom"))

        with pytest.raises(DiscordAlertError):
            sender.send("hello discord")


class TestDedupe:
    """Same listing must never alert twice, across separate 'runs'."""

    @pytest.fixture
    def session(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        return sessionmaker(bind=engine)()

    def test_has_been_alerted_false_until_recorded(self, session):
        item = CanonicalItem(brand="Rick Owens", line_or_era=None, model_name="Geobasket")
        session.add(item)
        session.commit()

        # Built directly rather than via upsert_listing(), which relies on
        # Postgres's INSERT ... ON CONFLICT and isn't SQLite-compatible --
        # this test only needs a persisted ListingRecord to dedupe against.
        listing = ListingRecord(
            source="ebay",
            external_id="dedupe-test-1",
            title="Rick Owens Geobasket size 42",
            brand="Rick Owens",
            price=600.0,
            currency="USD",
            size="42",
            condition=None,
            seller_rating=99.0,
            photo_count=5,
            url="https://example.com/1",
            fetched_at=datetime.now(timezone.utc),
        )
        session.add(listing)
        session.commit()

        assert has_been_alerted(session, listing.id) is False

        record_alert(session, listing.id, "deal")

        assert has_been_alerted(session, listing.id) is True

    def test_second_alert_pass_skips_already_alerted_listing(self, session):
        """Simulates two separate `alert` command runs against the same
        data: the first sends and records; the second must see it as
        already-alerted and skip it, which is the whole point of dedupe.
        """
        item = CanonicalItem(brand="Rick Owens", line_or_era=None, model_name="Geobasket")
        session.add(item)
        session.commit()

        listing_record = ListingRecord(
            source="ebay",
            external_id="dedupe-test-2",
            title="Rick Owens Geobasket size 42",
            brand="Rick Owens",
            price=400.0,  # deliberately low -- would classify as suspicious/deal
            currency="USD",
            size="42",
            condition=None,
            seller_rating=99.0,
            photo_count=5,
            url="https://example.com/2",
            fetched_at=datetime.now(timezone.utc),
        )
        session.add(listing_record)
        session.commit()

        # --- run 1: not yet alerted -> would send, then record ---
        assert has_been_alerted(session, listing_record.id) is False
        record_alert(session, listing_record.id, "suspicious")

        # --- run 2: same listing, should now be skipped ---
        assert has_been_alerted(session, listing_record.id) is True
