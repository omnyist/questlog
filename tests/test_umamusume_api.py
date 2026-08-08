from __future__ import annotations

import datetime

import pytest
from django.utils import timezone

from apps.library.models import Work
from apps.profiles.umamusume.models import CareerRun
from apps.profiles.umamusume.models import Character
from apps.profiles.umamusume.models import Outfit
from apps.profiles.umamusume.models import Profile


@pytest.fixture
def uma_setup(db):
    """Two characters; one has two outfits, mirroring El Condor Pasa in the
    real archive. Ratings are chosen so best-per-character is unambiguous."""
    work = Work.objects.create(name="Umamusume: Pretty Derby", slug="umamusume-pretty-derby")
    profile = Profile.objects.create(work=work)

    oguri = Character.objects.create(profile=profile, name="Oguri Cap", slug="oguri-cap")
    condor = Character.objects.create(profile=profile, name="El Condor Pasa", slug="el-condor-pasa")

    starlight = Outfit.objects.create(character=oguri, title="Starlight Beat", slug="oguri-starlight")
    numero = Outfit.objects.create(character=condor, title="El Numero 1", slug="condor-numero")
    kukulkan = Outfit.objects.create(character=condor, title="Kukulkan Warrior", slug="condor-kukulkan")

    base = timezone.make_aware(datetime.datetime(2026, 7, 1, 12, 0))

    def run(outfit, fp, rating, rank, races, wins, days, platform="steam", **extra):
        return CareerRun.objects.create(
            outfit=outfit, fingerprint=fp, rating=rating, rank=rank,
            races=races, wins=wins, run_date=base + datetime.timedelta(days=days),
            platform=platform, **extra,
        )

    run(starlight, "fp-oguri-best", 17867, "SS", 18, 16, 0, speed=1136, fans=928253)
    run(starlight, "fp-oguri-older", 9000, "B+", 12, 10, -30, platform="ios")
    # Best El Condor Pasa run sits on the *second* outfit — the Hall of Fame
    # entry must reach across outfits, not stop at the first one.
    run(numero, "fp-condor-low", 8000, "B+", 10, 5, -10)
    run(kukulkan, "fp-condor-best", 15000, "S", 14, 14, -5)
    return profile


@pytest.mark.django_db
class TestHallOfFame:
    def test_one_entry_per_character_ranked(self, api_client, uma_setup):
        data = api_client.get("/api/umamusume/halloffame").json()
        assert [e["name"] for e in data] == ["Oguri Cap", "El Condor Pasa"]
        assert [e["best_rating"] for e in data] == [17867, 15000]

    def test_best_run_spans_outfits(self, api_client, uma_setup):
        condor = next(
            e for e in api_client.get("/api/umamusume/halloffame").json()
            if e["slug"] == "el-condor-pasa"
        )
        # 15000 lives on the second outfit; 8000 on the first.
        assert condor["best_rating"] == 15000
        assert condor["best_rank"] == "S"
        assert condor["outfit_count"] == 2
        assert condor["run_count"] == 2

    def test_counts_perfect_runs(self, api_client, uma_setup):
        entries = {e["slug"]: e for e in api_client.get("/api/umamusume/halloffame").json()}
        assert entries["el-condor-pasa"]["perfect_runs"] == 1  # 14/14
        assert entries["oguri-cap"]["perfect_runs"] == 0

    def test_empty_archive_is_not_an_error(self, api_client, db):
        assert api_client.get("/api/umamusume/halloffame").json() == []


@pytest.mark.django_db
class TestCharacterDetail:
    def test_returns_outfits_and_runs(self, api_client, uma_setup):
        data = api_client.get("/api/umamusume/characters/el-condor-pasa").json()
        assert data["name"] == "El Condor Pasa"
        assert {o["title"] for o in data["outfits"]} == {"El Numero 1", "Kukulkan Warrior"}
        assert len(data["runs"]) == 2

    def test_run_carries_character_and_outfit(self, api_client, uma_setup):
        data = api_client.get("/api/umamusume/characters/oguri-cap").json()
        best = max(data["runs"], key=lambda r: r["rating"])
        assert best["character"] == "Oguri Cap"
        assert best["outfit_title"] == "Starlight Beat"
        assert best["speed"] == 1136

    def test_unknown_slug_404s(self, api_client, uma_setup):
        assert api_client.get("/api/umamusume/characters/nope").status_code == 404


@pytest.mark.django_db
class TestRuns:
    def test_paginated_shape(self, api_client, uma_setup):
        data = api_client.get("/api/umamusume/runs").json()
        assert data["count"] == 4
        assert len(data["items"]) == 4

    def test_filter_by_character_slug_or_name(self, api_client, uma_setup):
        by_slug = api_client.get("/api/umamusume/runs?character=oguri-cap").json()
        by_name = api_client.get("/api/umamusume/runs?character=Oguri%20Cap").json()
        assert by_slug["count"] == by_name["count"] == 2

    def test_filter_by_platform(self, api_client, uma_setup):
        assert api_client.get("/api/umamusume/runs?platform=ios").json()["count"] == 1

    def test_filter_min_rating(self, api_client, uma_setup):
        data = api_client.get("/api/umamusume/runs?min_rating=15000").json()
        assert data["count"] == 2

    def test_perfect_only(self, api_client, uma_setup):
        data = api_client.get("/api/umamusume/runs?perfect_only=true").json()
        assert data["count"] == 1
        assert data["items"][0]["races"] == data["items"][0]["wins"] == 14
        assert data["items"][0]["is_perfect"] is True


@pytest.mark.django_db
class TestStats:
    def test_aggregates(self, api_client, uma_setup):
        data = api_client.get("/api/umamusume/stats").json()
        assert data["characters"] == 2
        assert data["outfits"] == 3
        assert data["runs"] == 4
        assert data["best_rating"] == 17867
        assert data["perfect_runs"] == 1
        assert data["total_races"] == 18 + 12 + 10 + 14
        assert data["total_wins"] == 16 + 10 + 5 + 14

    def test_empty_archive(self, api_client, db):
        data = api_client.get("/api/umamusume/stats").json()
        assert data["runs"] == 0
        assert data["best_rating"] is None
        assert data["total_races"] == 0
