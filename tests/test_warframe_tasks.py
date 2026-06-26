from __future__ import annotations

from datetime import UTC
from datetime import datetime
from datetime import timedelta

from apps.profiles.warframe.api import compute_completion
from apps.profiles.warframe.api import compute_remaining
from apps.profiles.warframe.api import mastery_threshold
from apps.profiles.warframe.api import mastery_value
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


class TestMasteryValue:
    def test_weapon(self):
        assert mastery_value("Primary", 30) == 3000  # 100 * 30
        assert mastery_value("Melee", 40) == 4000  # 100 * 40

    def test_frame_companion(self):
        assert mastery_value("Warframes", 30) == 6000  # 200 * 30
        assert mastery_value("Sentinels", 30) == 6000


class TestComputeRemaining:
    # (unique_name, name, category, mastery_req, cap, is_prime, vaulted, acquisition)
    ITEMS = [
        ("/w/maxed", "Maxed Rifle", "Primary", 0, 30, False, False, "market"),
        ("/w/base", "Base Rifle", "Primary", 5, 30, False, False, "market"),
        ("/f/frame", "Cool Frame", "Warframes", 8, 30, False, False, "foundry"),
        ("/w/vault", "Vaulted Prime", "Melee", 0, 30, True, True, "foundry"),
        ("/w/gated", "Gated Gun", "Secondary", 30, 30, False, False, ""),
    ]

    def test_excludes_mastered_ranks_by_value(self):
        xp = {"/w/maxed": 999_999}  # only the maxed rifle is mastered
        out = compute_remaining(xp, self.ITEMS, current_mr=27)
        names = [r["name"] for r in out]
        assert "Maxed Rifle" not in names
        assert len(out) == 4
        # sorted by mastery_value desc -> frame (6000) first
        assert out[0]["name"] == "Cool Frame"
        assert out[0]["mastery_value"] == 6000

    def test_equippable_flag(self):
        out = {r["name"]: r for r in compute_remaining({}, self.ITEMS, current_mr=27)}
        assert out["Base Rifle"]["equippable"] is True       # req 5 <= 27
        assert out["Gated Gun"]["equippable"] is False        # req 30 > 27
        assert out["Vaulted Prime"]["vaulted"] is True

    def test_carries_judge_fields(self):
        out = {r["name"]: r for r in compute_remaining({}, self.ITEMS, current_mr=27)}
        frame = out["Cool Frame"]
        assert frame["category"] == "Warframes"
        assert frame["mastery_req"] == 8
        assert frame["acquisition"] == "foundry"
        assert frame["is_prime"] is False


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
