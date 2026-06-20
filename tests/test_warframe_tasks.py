from __future__ import annotations

from datetime import UTC
from datetime import datetime
from datetime import timedelta

from apps.profiles.warframe.api import compute_completion
from apps.profiles.warframe.api import mastery_threshold
from apps.profiles.warframe.tasks import staleness_alert_needed

NOW = datetime(2026, 6, 19, 12, 0, tzinfo=UTC)


class TestMasteryThreshold:
    def test_weapon_rank30(self):
        # 500 * 30^2 = 450,000
        assert mastery_threshold("Primary", 30) == 450_000

    def test_weapon_rank40(self):
        # 500 * 40^2 = 800,000
        assert mastery_threshold("Melee", 40) == 800_000

    def test_frame_rank30(self):
        # 1000 * 30^2 = 900,000
        assert mastery_threshold("Warframes", 30) == 900_000

    def test_unknown_category_defaults_weapon(self):
        assert mastery_threshold("Mystery", 30) == 450_000


class TestComputeCompletion:
    def test_empty(self):
        result = compute_completion({}, [])
        assert result["total_masterable"] == 0
        assert result["completion_pct"] == 0.0

    def test_mastered_vs_partial_vs_absent(self):
        items = [
            ("/w/maxed", "Primary", 30),     # 450k threshold
            ("/w/partial", "Primary", 30),   # below threshold
            ("/w/absent", "Secondary", 30),  # not in xp at all
            ("/f/maxed", "Warframes", 30),   # 900k threshold
        ]
        xp = {
            "/w/maxed": 500_000,      # >= 450k -> mastered
            "/w/partial": 100_000,    # < 450k -> not
            "/f/maxed": 10_000_000,   # >= 900k -> mastered
        }
        result = compute_completion(xp, items)
        assert result["total_masterable"] == 4
        assert result["total_mastered"] == 2
        assert result["completion_pct"] == 50.0
        by_cat = {c["category"]: c for c in result["categories"]}
        assert by_cat["Primary"]["mastered"] == 1
        assert by_cat["Primary"]["total"] == 2
        assert by_cat["Warframes"]["mastered"] == 1
        assert by_cat["Secondary"]["mastered"] == 0

    def test_rank40_boundary(self):
        items = [("/w/kuva", "Melee", 40)]  # 800k threshold
        assert compute_completion({"/w/kuva": 799_999}, items)["total_mastered"] == 0
        assert compute_completion({"/w/kuva": 800_000}, items)["total_mastered"] == 1


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
