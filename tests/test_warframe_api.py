from __future__ import annotations

import pytest


@pytest.mark.django_db
class TestWarframeProfile:
    def test_get_profile_empty(self, api_client):
        response = api_client.get("/api/warframe/profile")
        assert response.status_code == 404

    def test_get_profile(self, api_client, warframe_profile, warframe_weapon):
        response = api_client.get("/api/warframe/profile")
        assert response.status_code == 200
        data = response.json()
        assert data["display_name"] == "Avalonstar"
        assert data["account_id"] == "5b2d428bf2f2ebde1070a2b1"
        assert data["mastery_rank"] == 11
        assert data["missions_completed"] == 691
        assert data["time_played_seconds"] == 429758
        assert data["weapons_tracked"] == 1
        assert data["total_weapon_kills"] == 24


@pytest.mark.django_db
class TestWarframeWeapons:
    def test_list_empty(self, api_client):
        response = api_client.get("/api/warframe/weapons")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["weapons"] == []

    def test_list_weapons(self, api_client, warframe_weapons):
        response = api_client.get("/api/warframe/weapons")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 5
        assert len(data["weapons"]) == 5
        # Default sort is by kills descending
        assert data["weapons"][0]["kills"] >= data["weapons"][-1]["kills"]

    def test_sort_by_equip_time(self, api_client, warframe_weapons):
        response = api_client.get("/api/warframe/weapons?sort=equip_time")
        assert response.status_code == 200
        data = response.json()
        weapons = data["weapons"]
        for i in range(len(weapons) - 1):
            assert weapons[i]["equip_time_seconds"] >= weapons[i + 1]["equip_time_seconds"]

    def test_pagination(self, api_client, warframe_weapons):
        response = api_client.get("/api/warframe/weapons?limit=2&offset=0")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 5
        assert len(data["weapons"]) == 2

    def test_min_kills_filter(self, api_client, warframe_weapons):
        response = api_client.get("/api/warframe/weapons?min_kills=400")
        assert response.status_code == 200
        data = response.json()
        # Only weapons 4 and 5 have >= 400 kills (100*4=400, 100*5=500)
        assert data["total"] == 2

    def test_top_weapons(self, api_client, warframe_weapons):
        response = api_client.get("/api/warframe/weapons/top?by=kills&limit=3")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 3
        # Sorted by kills descending
        assert data[0]["kills"] >= data[1]["kills"] >= data[2]["kills"]


@pytest.mark.django_db
class TestWarframeMissions:
    def test_list_empty(self, api_client):
        response = api_client.get("/api/warframe/missions")
        assert response.status_code == 200
        assert response.json() == []

    def test_list_missions(self, api_client, warframe_mission):
        response = api_client.get("/api/warframe/missions")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["node_tag"] == "SolNode27"
        assert data[0]["completes"] == 42


@pytest.mark.django_db
class TestWarframeAffiliations:
    def test_list_empty(self, api_client):
        response = api_client.get("/api/warframe/affiliations")
        assert response.status_code == 200
        assert response.json() == []

    def test_list_affiliations(self, api_client, warframe_affiliation):
        response = api_client.get("/api/warframe/affiliations")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["syndicate_tag"] == "CetusSyndicate"
        assert data[0]["standing"] == 12931
        assert data[0]["title_rank"] == 1


@pytest.mark.django_db
class TestWarframeSnapshots:
    def test_list_empty(self, api_client):
        response = api_client.get("/api/warframe/snapshots")
        assert response.status_code == 200
        assert response.json() == []

    def test_list_snapshots(self, api_client, warframe_snapshot):
        response = api_client.get("/api/warframe/snapshots")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["mastery_rank"] == 11
        assert data[0]["trigger"] == "manual"
        assert data[0]["total_weapon_kills"] == 34229


@pytest.mark.django_db
class TestWarframeStats:
    def test_stats_empty(self, api_client):
        response = api_client.get("/api/warframe/stats")
        assert response.status_code == 404

    def test_stats(self, api_client, warframe_profile, warframe_weapons, warframe_mission, warframe_affiliation):
        response = api_client.get("/api/warframe/stats")
        assert response.status_code == 200
        data = response.json()
        assert data["mastery_rank"] == 11
        assert data["time_played_hours"] > 0
        assert data["missions_completed"] == 691
        # Sum of weapons: 100 + 200 + 300 + 400 + 500 = 1500
        assert data["total_weapon_kills"] == 1500
        assert data["weapons_tracked"] == 5
        assert data["nodes_played"] == 1
        assert data["syndicates_joined"] == 1
        assert data["overall_accuracy"] > 0


@pytest.mark.django_db
class TestWarframeMastery:
    def test_mastery_empty(self, api_client):
        response = api_client.get("/api/warframe/mastery")
        assert response.status_code == 404

    def test_mastery_current_rank(self, api_client, warframe_profile):
        response = api_client.get("/api/warframe/mastery")
        assert response.status_code == 200
        data = response.json()
        assert data["current_rank"] == 11
        assert data["history"] == []

    def test_mastery_changes_granularity(self, api_client, warframe_profile, warframe_mastery_history):
        response = api_client.get("/api/warframe/mastery")
        assert response.status_code == 200
        data = response.json()
        # ranks were 11,11,12,12,12,13 -> change points at 11,12,13 (latest is 13, already a change)
        ranks = [p["mastery_rank"] for p in data["history"]]
        assert ranks == [11, 12, 13]

    def test_mastery_all_granularity(self, api_client, warframe_profile, warframe_mastery_history):
        response = api_client.get("/api/warframe/mastery?granularity=all")
        assert response.status_code == 200
        data = response.json()
        assert len(data["history"]) == 6


@pytest.mark.django_db
class TestWarframeFrames:
    def test_frames_empty(self, api_client):
        response = api_client.get("/api/warframe/frames")
        assert response.status_code == 200
        assert response.json() == []

    def test_frames_excludes_sentinel(self, api_client, warframe_catalog, warframe_frame_weapons):
        """The Helios sentinel has the highest equip time but must NOT appear."""
        response = api_client.get("/api/warframe/frames")
        assert response.status_code == 200
        data = response.json()
        names = [f["name"] for f in data]
        assert names == ["Gauss Prime", "Excalibur"]
        assert "Helios Prime" not in names
        assert "Prime Helios Power Suit" not in names

    def test_frames_metadata(self, api_client, warframe_catalog, warframe_frame_weapons):
        response = api_client.get("/api/warframe/frames")
        data = response.json()
        gauss = data[0]
        assert gauss["name"] == "Gauss Prime"
        assert gauss["image_name"] == "gauss-prime.png"
        assert gauss["is_prime"] is True
        assert gauss["kills"] == 3470
        assert gauss["equip_time_hours"] == round(192849 / 3600, 1)

    def test_frames_prime_only(self, api_client, warframe_catalog, warframe_frame_weapons):
        response = api_client.get("/api/warframe/frames?prime_only=true")
        data = response.json()
        names = [f["name"] for f in data]
        assert names == ["Gauss Prime"]

    def test_frames_limit(self, api_client, warframe_catalog, warframe_frame_weapons):
        response = api_client.get("/api/warframe/frames?limit=1")
        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == "Gauss Prime"
