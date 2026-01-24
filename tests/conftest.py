from __future__ import annotations

import pytest
from django.test import Client

from apps.library.models import Edition
from apps.library.models import Franchise
from apps.library.models import Genre
from apps.library.models import Work
from apps.lists.models import Entry
from apps.lists.models import List


@pytest.fixture
def api_client():
    """Django test client for API requests."""
    return Client()


@pytest.fixture
def franchise(db):
    """Create a test franchise."""
    return Franchise.objects.create(name="Final Fantasy", slug="final-fantasy")


@pytest.fixture
def genre(db):
    """Create a test genre."""
    return Genre.objects.create(name="Role-playing (RPG)", slug="role-playing-rpg", igdb_id=12)


@pytest.fixture
def work(db, franchise):
    """Create a test work with a franchise."""
    return Work.objects.create(
        name="Final Fantasy VII",
        slug="final-fantasy-vii",
        franchise=franchise,
        original_release_year=1997,
    )


@pytest.fixture
def standalone_work(db):
    """Create a test work without a franchise."""
    return Work.objects.create(
        name="Bastion",
        slug="bastion",
        original_release_year=2011,
    )


@pytest.fixture
def edition(db, work):
    """Create a test edition."""
    return Edition.objects.create(
        work=work,
        name="Final Fantasy VII",
        slug="final-fantasy-vii",
        edition_type="original",
        igdb_id=427,
    )


@pytest.fixture
def game_list(db):
    """Create a test list."""
    return List.objects.create(
        name="Completed RPGs",
        slug="completed-rpgs",
        description="All RPGs I've completed.",
        is_ranked=False,
    )


@pytest.fixture
def list_entry(db, game_list, work):
    """Create a test list entry."""
    return Entry.objects.create(
        list=game_list,
        work=work,
        position=1,
    )
