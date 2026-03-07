from __future__ import annotations

import pytest
from django.test import Client

from apps.profiles.ironmon.models import Challenge
from apps.profiles.ironmon.models import Checkpoint
from apps.profiles.ironmon.models import CheckpointResult
from apps.profiles.ironmon.models import Run

TEST_API_KEY = "test-api-key-for-ironmon"


@pytest.fixture
def api_client():
    return Client()


@pytest.fixture(autouse=True)
def _set_api_key(settings):
    settings.API_KEY = TEST_API_KEY


@pytest.fixture
def auth_headers():
    return {"HTTP_AUTHORIZATION": f"Bearer {TEST_API_KEY}"}


@pytest.fixture
def challenge(db):
    return Challenge.objects.create(slug="kaizo", name="Kaizo")


@pytest.fixture
def checkpoints(challenge):
    cp1 = Checkpoint.objects.create(
        challenge=challenge, name="Brock", trainer="Brock", order=1
    )
    cp2 = Checkpoint.objects.create(
        challenge=challenge, name="Misty", trainer="Misty", order=2
    )
    cp3 = Checkpoint.objects.create(
        challenge=challenge, name="Surge", trainer="Lt. Surge", order=3
    )
    return [cp1, cp2, cp3]


@pytest.fixture
def run(challenge):
    return Run.objects.create(seed_number=100, challenge=challenge)


# --- Read endpoints (no auth required) ---


@pytest.mark.django_db
class TestChallengeEndpoint:
    def test_get_challenge_returns_checkpoints(self, api_client, challenge, checkpoints):
        response = api_client.get(f"/api/ironmon/challenges/{challenge.slug}")
        assert response.status_code == 200

        data = response.json()
        assert data["slug"] == "kaizo"
        assert data["name"] == "Kaizo"
        assert len(data["checkpoints"]) == 3
        assert data["checkpoints"][0]["name"] == "Brock"
        assert data["checkpoints"][0]["order"] == 1

    def test_get_challenge_not_found(self, api_client):
        response = api_client.get("/api/ironmon/challenges/nonexistent")
        assert response.status_code == 404

    def test_stats_no_auth_required(self, api_client, challenge):
        response = api_client.get("/api/ironmon/stats")
        assert response.status_code == 200

    def test_runs_no_auth_required(self, api_client, challenge):
        response = api_client.get("/api/ironmon/runs")
        assert response.status_code == 200


# --- Write endpoints (auth required) ---


@pytest.mark.django_db
class TestCreateRun:
    def test_create_run(self, api_client, auth_headers, challenge):
        response = api_client.post(
            "/api/ironmon/runs",
            data={"seed_number": 42, "challenge_slug": "kaizo"},
            content_type="application/json",
            **auth_headers,
        )
        assert response.status_code == 200

        data = response.json()
        assert data["seed_number"] == 42
        assert data["challenge"] == "Kaizo"
        assert data["created"] is True

        assert Run.objects.filter(seed_number=42).exists()

    def test_create_run_idempotent(self, api_client, auth_headers, challenge):
        api_client.post(
            "/api/ironmon/runs",
            data={"seed_number": 42, "challenge_slug": "kaizo"},
            content_type="application/json",
            **auth_headers,
        )
        response = api_client.post(
            "/api/ironmon/runs",
            data={"seed_number": 42, "challenge_slug": "kaizo"},
            content_type="application/json",
            **auth_headers,
        )
        assert response.status_code == 200

        data = response.json()
        assert data["created"] is False
        assert Run.objects.filter(seed_number=42).count() == 1

    def test_create_run_rejects_no_auth(self, api_client, challenge):
        response = api_client.post(
            "/api/ironmon/runs",
            data={"seed_number": 42, "challenge_slug": "kaizo"},
            content_type="application/json",
        )
        assert response.status_code == 401

    def test_create_run_rejects_bad_key(self, api_client, challenge):
        response = api_client.post(
            "/api/ironmon/runs",
            data={"seed_number": 42, "challenge_slug": "kaizo"},
            content_type="application/json",
            HTTP_AUTHORIZATION="Bearer wrong-key",
        )
        assert response.status_code == 401


@pytest.mark.django_db
class TestRecordCheckpoint:
    def test_record_checkpoint(self, api_client, auth_headers, run, checkpoints):
        response = api_client.post(
            f"/api/ironmon/runs/{run.seed_number}/results",
            data={"checkpoint_name": "Brock"},
            content_type="application/json",
            **auth_headers,
        )
        assert response.status_code == 200

        data = response.json()
        assert data["seed_number"] == 100
        assert data["checkpoint"] == "Brock"
        assert data["checkpoint_order"] == 1
        assert data["created"] is True

        assert CheckpointResult.objects.filter(run=run).count() == 1

    def test_record_checkpoint_updates_highest(
        self, api_client, auth_headers, run, checkpoints
    ):
        # Clear Brock (order 1)
        api_client.post(
            f"/api/ironmon/runs/{run.seed_number}/results",
            data={"checkpoint_name": "Brock"},
            content_type="application/json",
            **auth_headers,
        )
        run.refresh_from_db()
        assert run.highest_checkpoint.name == "Brock"

        # Clear Misty (order 2) — highest should update
        api_client.post(
            f"/api/ironmon/runs/{run.seed_number}/results",
            data={"checkpoint_name": "Misty"},
            content_type="application/json",
            **auth_headers,
        )
        run.refresh_from_db()
        assert run.highest_checkpoint.name == "Misty"

    def test_record_checkpoint_does_not_lower_highest(
        self, api_client, auth_headers, run, checkpoints
    ):
        # Clear Misty first (order 2)
        api_client.post(
            f"/api/ironmon/runs/{run.seed_number}/results",
            data={"checkpoint_name": "Misty"},
            content_type="application/json",
            **auth_headers,
        )
        run.refresh_from_db()
        assert run.highest_checkpoint.name == "Misty"

        # Clear Brock (order 1) — highest should NOT go down
        api_client.post(
            f"/api/ironmon/runs/{run.seed_number}/results",
            data={"checkpoint_name": "Brock"},
            content_type="application/json",
            **auth_headers,
        )
        run.refresh_from_db()
        assert run.highest_checkpoint.name == "Misty"

    def test_record_checkpoint_idempotent(
        self, api_client, auth_headers, run, checkpoints
    ):
        api_client.post(
            f"/api/ironmon/runs/{run.seed_number}/results",
            data={"checkpoint_name": "Brock"},
            content_type="application/json",
            **auth_headers,
        )
        response = api_client.post(
            f"/api/ironmon/runs/{run.seed_number}/results",
            data={"checkpoint_name": "Brock"},
            content_type="application/json",
            **auth_headers,
        )
        assert response.status_code == 200

        data = response.json()
        assert data["created"] is False
        assert CheckpointResult.objects.filter(run=run).count() == 1

    def test_record_checkpoint_rejects_no_auth(self, api_client, run, checkpoints):
        response = api_client.post(
            f"/api/ironmon/runs/{run.seed_number}/results",
            data={"checkpoint_name": "Brock"},
            content_type="application/json",
        )
        assert response.status_code == 401
