from __future__ import annotations

from datetime import UTC
from datetime import datetime
from datetime import timedelta

from apps.profiles.warframe.tasks import staleness_alert_needed

NOW = datetime(2026, 6, 19, 12, 0, tzinfo=UTC)


class TestStalenessAlertNeeded:
    def test_never_synced_no_alert(self):
        assert staleness_alert_needed(None, NOW, played_recently=True) is False

    def test_not_played_recently_no_alert(self):
        # Stale by a week, but not playing — expected, no alert.
        old = NOW - timedelta(days=7)
        assert staleness_alert_needed(old, NOW, played_recently=False) is False

    def test_fresh_and_playing_no_alert(self):
        recent = NOW - timedelta(hours=6)
        assert staleness_alert_needed(recent, NOW, played_recently=True) is False

    def test_stale_and_playing_alerts(self):
        stale = NOW - timedelta(hours=72)
        assert staleness_alert_needed(stale, NOW, played_recently=True) is True

    def test_threshold_boundary(self):
        # Exactly at 48h is not yet over the threshold; just past it alerts.
        at_threshold = NOW - timedelta(hours=48)
        assert staleness_alert_needed(at_threshold, NOW, played_recently=True) is False
        just_over = NOW - timedelta(hours=48, minutes=1)
        assert staleness_alert_needed(just_over, NOW, played_recently=True) is True
