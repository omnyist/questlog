from __future__ import annotations

import pytest

from apps.lists.models import ListActivity


@pytest.mark.django_db
class TestListsAPI:
    """Tests for /api/lists endpoints."""

    def test_list_lists_empty(self, api_client):
        """GET /api/lists returns empty list when no lists exist."""
        response = api_client.get("/api/lists")
        assert response.status_code == 200
        assert response.json() == []

    def test_list_lists(self, api_client, game_list):
        """GET /api/lists returns list with correct schema."""
        response = api_client.get("/api/lists")
        assert response.status_code == 200

        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == "Completed RPGs"
        assert data[0]["slug"] == "completed-rpgs"
        assert data[0]["description"] == "All RPGs I've completed."
        assert data[0]["is_ranked"] is False
        assert data[0]["entry_count"] == 0
        assert "id" in data[0]

    def test_list_lists_with_entries(self, api_client, game_list, list_entry):
        """GET /api/lists includes entry count."""
        response = api_client.get("/api/lists")
        assert response.status_code == 200

        data = response.json()
        assert data[0]["entry_count"] == 1

    def test_create_list(self, api_client, db):
        """POST /api/lists creates list and returns correct schema."""
        response = api_client.post(
            "/api/lists",
            data={
                "name": "Top 25 RPGs",
                "slug": "top-25-rpgs",
                "description": "My favorite RPGs of all time.",
                "is_ranked": True,
            },
            content_type="application/json",
        )
        assert response.status_code == 200

        data = response.json()
        assert data["name"] == "Top 25 RPGs"
        assert data["slug"] == "top-25-rpgs"
        assert data["description"] == "My favorite RPGs of all time."
        assert data["is_ranked"] is True
        assert data["entry_count"] == 0
        assert "id" in data

    def test_get_list(self, api_client, game_list, list_entry):
        """GET /api/lists/{slug} returns list with entries."""
        response = api_client.get("/api/lists/completed-rpgs")
        assert response.status_code == 200

        data = response.json()
        assert data["name"] == "Completed RPGs"
        assert data["slug"] == "completed-rpgs"
        assert len(data["entries"]) == 1
        assert data["entries"][0]["work_name"] == "Final Fantasy VII"
        assert data["entries"][0]["work_slug"] == "final-fantasy-vii"
        assert data["entries"][0]["position"] == 1

    def test_get_list_not_found(self, api_client, db):
        """GET /api/lists/{slug} returns 404 for unknown slug."""
        response = api_client.get("/api/lists/unknown-list")
        assert response.status_code == 404


@pytest.mark.django_db
class TestEntriesAPI:
    """Tests for /api/lists/{slug}/entries endpoints."""

    def test_add_entry(self, api_client, game_list, standalone_work):
        """POST /api/lists/{slug}/entries adds work to list."""
        response = api_client.post(
            "/api/lists/completed-rpgs/entries",
            data={"work_slug": "bastion", "position": 1, "notes": "Great game!"},
            content_type="application/json",
        )
        assert response.status_code == 200

        data = response.json()
        assert data["work_name"] == "Bastion"
        assert data["work_slug"] == "bastion"
        assert data["position"] == 1
        assert data["notes"] == "Great game!"
        assert "id" in data
        assert "work_id" in data

    def test_add_entry_work_not_found(self, api_client, game_list):
        """POST /api/lists/{slug}/entries returns 404 for unknown work."""
        response = api_client.post(
            "/api/lists/completed-rpgs/entries",
            data={"work_slug": "unknown-work"},
            content_type="application/json",
        )
        assert response.status_code == 404

    def test_bulk_add_entries(self, api_client, game_list, work, standalone_work):
        """POST /api/lists/{slug}/entries/bulk adds multiple works."""
        response = api_client.post(
            "/api/lists/completed-rpgs/entries/bulk",
            data={
                "entries": [
                    {"work_slug": "final-fantasy-vii"},
                    {"work_slug": "bastion"},
                ]
            },
            content_type="application/json",
        )
        assert response.status_code == 200

        data = response.json()
        assert data["created"] == 2
        assert data["skipped"] == 0
        assert data["errors"] == []

    def test_bulk_add_entries_skips_duplicates(self, api_client, game_list, list_entry, standalone_work):
        """POST /api/lists/{slug}/entries/bulk skips existing entries."""
        response = api_client.post(
            "/api/lists/completed-rpgs/entries/bulk",
            data={
                "entries": [
                    {"work_slug": "final-fantasy-vii"},  # Already exists
                    {"work_slug": "bastion"},
                ]
            },
            content_type="application/json",
        )
        assert response.status_code == 200

        data = response.json()
        assert data["created"] == 1
        assert data["skipped"] == 1
        assert data["errors"] == []

    def test_bulk_add_entries_reports_errors(self, api_client, game_list, work):
        """POST /api/lists/{slug}/entries/bulk reports errors for unknown works."""
        response = api_client.post(
            "/api/lists/completed-rpgs/entries/bulk",
            data={
                "entries": [
                    {"work_slug": "final-fantasy-vii"},
                    {"work_slug": "unknown-work"},
                ]
            },
            content_type="application/json",
        )
        assert response.status_code == 200

        data = response.json()
        assert data["created"] == 1
        assert data["skipped"] == 0
        assert len(data["errors"]) == 1
        assert "unknown-work" in data["errors"][0]


@pytest.mark.django_db
class TestActivityAPI:
    """Tests for /api/lists/{slug}/activity endpoints."""

    def test_get_activity_empty(self, api_client, game_list):
        """GET /api/lists/{slug}/activity returns empty list for new list."""
        response = api_client.get("/api/lists/completed-rpgs/activity")
        assert response.status_code == 200
        assert response.json() == []

    def test_get_activity_after_add(self, api_client, game_list, standalone_work):
        """GET /api/lists/{slug}/activity shows added entry."""
        # Add an entry (triggers signal)
        api_client.post(
            "/api/lists/completed-rpgs/entries",
            data={"work_slug": "bastion"},
            content_type="application/json",
        )

        response = api_client.get("/api/lists/completed-rpgs/activity")
        assert response.status_code == 200

        data = response.json()
        assert len(data) == 1
        assert data[0]["verb"] == "added"
        assert data[0]["entries"] == ["bastion"]
        assert "id" in data[0]
        assert "timestamp" in data[0]
        assert "metadata" in data[0]

    def test_activity_schema(self, api_client, game_list, standalone_work):
        """Activity response has correct schema."""
        # Create activity manually
        ListActivity.objects.create(
            list=game_list,
            verb="created",
            entries=["bastion", "transistor"],
            metadata={"count": 2},
        )

        response = api_client.get("/api/lists/completed-rpgs/activity")
        assert response.status_code == 200

        data = response.json()
        assert len(data) == 1
        activity = data[0]

        # Verify all expected fields
        assert "id" in activity
        assert "timestamp" in activity
        assert activity["verb"] == "created"
        assert activity["entries"] == ["bastion", "transistor"]
        assert activity["metadata"] == {"count": 2}

    def test_activity_limit(self, api_client, game_list):
        """GET /api/lists/{slug}/activity respects limit param."""
        # Create multiple activities
        for i in range(5):
            ListActivity.objects.create(
                list=game_list,
                verb="added",
                entries=[f"game-{i}"],
            )

        response = api_client.get("/api/lists/completed-rpgs/activity?limit=2")
        assert response.status_code == 200
        assert len(response.json()) == 2

    def test_get_activity_not_found(self, api_client, db):
        """GET /api/lists/{slug}/activity returns 404 for unknown list."""
        response = api_client.get("/api/lists/unknown-list/activity")
        assert response.status_code == 404
