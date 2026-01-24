from __future__ import annotations

import pytest


@pytest.mark.django_db
class TestFranchiseAPI:
    """Tests for /api/franchises endpoints."""

    def test_list_franchises_empty(self, api_client):
        """GET /api/franchises returns empty list when no franchises exist."""
        response = api_client.get("/api/franchises")
        assert response.status_code == 200
        assert response.json() == []

    def test_list_franchises(self, api_client, franchise):
        """GET /api/franchises returns list with correct schema."""
        response = api_client.get("/api/franchises")
        assert response.status_code == 200

        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == "Final Fantasy"
        assert data[0]["slug"] == "final-fantasy"
        assert "id" in data[0]


@pytest.mark.django_db
class TestGenreAPI:
    """Tests for /api/genres endpoints."""

    def test_list_genres_empty(self, api_client):
        """GET /api/genres returns empty list when no genres exist."""
        response = api_client.get("/api/genres")
        assert response.status_code == 200
        assert response.json() == []

    def test_list_genres(self, api_client, genre):
        """GET /api/genres returns list with correct schema."""
        response = api_client.get("/api/genres")
        assert response.status_code == 200

        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == "Role-playing (RPG)"
        assert data[0]["slug"] == "role-playing-rpg"
        assert data[0]["igdb_id"] == 12
        assert data[0]["parent_id"] is None
        assert "id" in data[0]

    def test_create_genre(self, api_client, db):
        """POST /api/genres creates genre and returns correct schema."""
        response = api_client.post(
            "/api/genres",
            data={"name": "Action", "slug": "action", "igdb_id": 1},
            content_type="application/json",
        )
        assert response.status_code == 200

        data = response.json()
        assert data["name"] == "Action"
        assert data["slug"] == "action"
        assert data["igdb_id"] == 1
        assert data["parent_id"] is None
        assert "id" in data


@pytest.mark.django_db
class TestWorksAPI:
    """Tests for /api/works endpoints."""

    def test_list_works_empty(self, api_client):
        """GET /api/works returns empty list when no works exist."""
        response = api_client.get("/api/works")
        assert response.status_code == 200
        assert response.json() == []

    def test_list_works(self, api_client, work):
        """GET /api/works returns list with correct schema."""
        response = api_client.get("/api/works")
        assert response.status_code == 200

        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == "Final Fantasy VII"
        assert data[0]["slug"] == "final-fantasy-vii"
        assert data[0]["original_release_year"] == 1997
        assert data[0]["franchise"]["name"] == "Final Fantasy"
        assert "id" in data[0]

    def test_list_works_without_franchise(self, api_client, standalone_work):
        """GET /api/works handles works without franchise."""
        response = api_client.get("/api/works")
        assert response.status_code == 200

        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == "Bastion"
        assert data[0]["franchise"] is None

    def test_list_works_filter_by_franchise(self, api_client, work, standalone_work):
        """GET /api/works?franchise=slug filters by franchise."""
        response = api_client.get("/api/works?franchise=final-fantasy")
        assert response.status_code == 200

        data = response.json()
        assert len(data) == 1
        assert data[0]["slug"] == "final-fantasy-vii"

    def test_list_works_pagination(self, api_client, work, standalone_work):
        """GET /api/works supports limit and offset."""
        response = api_client.get("/api/works?limit=1&offset=0")
        assert response.status_code == 200
        assert len(response.json()) == 1

        response = api_client.get("/api/works?limit=1&offset=1")
        assert response.status_code == 200
        assert len(response.json()) == 1

    def test_get_work(self, api_client, work, edition):
        """GET /api/works/{slug} returns work with editions."""
        response = api_client.get("/api/works/final-fantasy-vii")
        assert response.status_code == 200

        data = response.json()
        assert data["name"] == "Final Fantasy VII"
        assert data["slug"] == "final-fantasy-vii"
        assert data["original_release_year"] == 1997
        assert data["franchise"]["name"] == "Final Fantasy"
        assert len(data["editions"]) == 1
        assert data["editions"][0]["name"] == "Final Fantasy VII"

    def test_get_work_not_found(self, api_client, db):
        """GET /api/works/{slug} returns 404 for unknown slug."""
        response = api_client.get("/api/works/unknown-game")
        assert response.status_code == 404


@pytest.mark.django_db
class TestEditionsAPI:
    """Tests for /api/editions endpoints."""

    def test_list_editions_empty(self, api_client):
        """GET /api/editions returns empty list when no editions exist."""
        response = api_client.get("/api/editions")
        assert response.status_code == 200
        assert response.json() == []

    def test_list_editions(self, api_client, edition):
        """GET /api/editions returns list with correct schema."""
        response = api_client.get("/api/editions")
        assert response.status_code == 200

        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == "Final Fantasy VII"
        assert data[0]["slug"] == "final-fantasy-vii"
        assert data[0]["edition_type"] == "original"
        assert data[0]["igdb_id"] == 427
        assert "id" in data[0]
        assert "work_id" in data[0]

    def test_list_editions_filter_by_work(self, api_client, edition, standalone_work):
        """GET /api/editions?work=slug filters by work."""
        # Create another edition for standalone work
        from apps.library.models import Edition

        Edition.objects.create(
            work=standalone_work,
            name="Bastion",
            slug="bastion",
            edition_type="original",
        )

        response = api_client.get("/api/editions?work=final-fantasy-vii")
        assert response.status_code == 200

        data = response.json()
        assert len(data) == 1
        assert data[0]["slug"] == "final-fantasy-vii"

    def test_get_edition(self, api_client, edition):
        """GET /api/editions/{slug} returns edition with correct schema."""
        response = api_client.get("/api/editions/final-fantasy-vii")
        assert response.status_code == 200

        data = response.json()
        assert data["name"] == "Final Fantasy VII"
        assert data["slug"] == "final-fantasy-vii"
        assert data["edition_type"] == "original"
        assert data["igdb_id"] == 427

    def test_get_edition_not_found(self, api_client, db):
        """GET /api/editions/{slug} returns 404 for unknown slug."""
        response = api_client.get("/api/editions/unknown-edition")
        assert response.status_code == 404
