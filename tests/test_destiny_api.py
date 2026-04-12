from __future__ import annotations

import pytest


@pytest.mark.django_db
class TestDestinyProfile:
    def test_get_profile_empty(self, api_client):
        response = api_client.get("/api/destiny/profile")
        assert response.status_code == 404

    def test_get_profile(self, api_client, destiny_profile, destiny_character):
        response = api_client.get("/api/destiny/profile")
        assert response.status_code == 200
        data = response.json()
        assert data["bungie_name"] == "Avalonstar"
        assert data["bungie_name_code"] == 1234
        assert data["membership_type"] == 3
        assert data["character_count"] == 1
        assert len(data["characters"]) == 1
        assert data["characters"][0]["character_class"] == "warlock"


@pytest.mark.django_db
class TestDestinyCharacters:
    def test_list_characters_empty(self, api_client):
        response = api_client.get("/api/destiny/characters")
        assert response.status_code == 200
        assert response.json() == []

    def test_list_characters(self, api_client, destiny_character):
        response = api_client.get("/api/destiny/characters")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["character_class"] == "warlock"
        assert data[0]["light_level"] == 1810


@pytest.mark.django_db
class TestDestinyStats:
    def test_list_stats_empty(self, api_client):
        response = api_client.get("/api/destiny/stats")
        assert response.status_code == 200
        assert response.json() == []

    def test_list_stats(self, api_client, destiny_stats, destiny_account_stats):
        response = api_client.get("/api/destiny/stats")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

    def test_filter_by_scope(self, api_client, destiny_stats, destiny_account_stats):
        response = api_client.get("/api/destiny/stats?scope=account")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["scope"] == "account"
        assert data[0]["mode"] == "allPvE"

    def test_filter_by_mode(self, api_client, destiny_stats, destiny_account_stats):
        response = api_client.get("/api/destiny/stats?mode=raid")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["mode"] == "raid"
        assert data[0]["kills"] == 15234

    def test_get_stats_by_mode(self, api_client, destiny_stats):
        response = api_client.get("/api/destiny/stats/raid")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["kd_ratio"] == 37.9


@pytest.mark.django_db
class TestDestinyActivities:
    def test_list_activities_empty(self, api_client):
        response = api_client.get("/api/destiny/activities")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["activities"] == []

    def test_list_activities(self, api_client, destiny_raid_activity):
        response = api_client.get("/api/destiny/activities")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["activities"]) == 1
        assert data["activities"][0]["activity_name"] == "Last Wish"
        assert data["activities"][0]["mode_category"] == "raid"
        assert data["activities"][0]["has_pgcr"] is False

    def test_filter_by_mode_category(
        self, api_client, destiny_raid_activity, destiny_profile, destiny_character
    ):
        from django.utils import timezone

        from apps.profiles.destiny.models import Activity

        Activity.objects.create(
            profile=destiny_profile,
            character=destiny_character,
            instance_id="9999",
            activity_hash=111,
            activity_name="Trials Match",
            mode=84,
            mode_category="trials",
            period=timezone.now(),
        )
        response = api_client.get("/api/destiny/activities?mode_category=raid")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["activities"][0]["mode_category"] == "raid"

    def test_pagination(self, api_client, destiny_profile, destiny_character):
        from django.utils import timezone

        from apps.profiles.destiny.models import Activity

        for i in range(5):
            Activity.objects.create(
                profile=destiny_profile,
                character=destiny_character,
                instance_id=str(i),
                activity_hash=i,
                activity_name=f"Strike {i}",
                mode=3,
                mode_category="strike",
                period=timezone.now(),
            )

        response = api_client.get("/api/destiny/activities?limit=2&offset=0")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 5
        assert len(data["activities"]) == 2

    def test_get_activity_not_found(self, api_client):
        response = api_client.get("/api/destiny/activities/nope")
        assert response.status_code == 404

    def test_get_activity_without_pgcr(self, api_client, destiny_raid_activity):
        response = api_client.get(f"/api/destiny/activities/{destiny_raid_activity.instance_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["activity_name"] == "Last Wish"
        assert data["pgcr_entries"] is None

    def test_get_activity_with_pgcr(self, api_client, destiny_pgcr, destiny_raid_activity):
        response = api_client.get(f"/api/destiny/activities/{destiny_raid_activity.instance_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["pgcr_entries"] is not None
        assert len(data["pgcr_entries"]) == 2
        self_entries = [e for e in data["pgcr_entries"] if e["is_self"]]
        assert len(self_entries) == 1
        assert self_entries[0]["display_name"] == "Avalonstar"


@pytest.mark.django_db
class TestDestinyRaids:
    def test_raid_stats_empty(self, api_client):
        response = api_client.get("/api/destiny/raids/stats")
        assert response.status_code == 200
        data = response.json()
        assert data["total_attempts"] == 0
        assert data["total_clears"] == 0
        assert data["clear_rate"] == 0.0
        assert data["raids"] == []

    def test_raid_stats(self, api_client, destiny_raid_activity, destiny_profile, destiny_character):
        from django.utils import timezone

        from apps.profiles.destiny.models import Activity

        # Add a failed Last Wish attempt
        Activity.objects.create(
            profile=destiny_profile,
            character=destiny_character,
            instance_id="failed1",
            activity_hash=destiny_raid_activity.activity_hash,
            activity_name="Last Wish",
            mode=4,
            mode_category="raid",
            period=timezone.now(),
            duration_seconds=1200,
            completed=False,
            kills=40,
            deaths=5,
        )

        response = api_client.get("/api/destiny/raids/stats")
        assert response.status_code == 200
        data = response.json()
        assert data["total_attempts"] == 2
        assert data["total_clears"] == 1
        assert data["clear_rate"] == 0.5
        assert data["total_kills"] == 185
        assert len(data["raids"]) == 1
        assert data["raids"][0]["activity_name"] == "Last Wish"
        assert data["raids"][0]["attempts"] == 2
        assert data["raids"][0]["clears"] == 1
