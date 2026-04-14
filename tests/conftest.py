from __future__ import annotations

import pytest
from django.test import Client

from apps.library.models import Edition
from apps.library.models import Franchise
from apps.library.models import Genre
from apps.library.models import Work
from apps.lists.models import Entry
from apps.lists.models import List
from apps.profiles.destiny.models import Activity as DestinyActivity
from apps.profiles.destiny.models import AggregateStats as DestinyAggregateStats
from apps.profiles.destiny.models import CarnageReport as DestinyCarnageReport
from apps.profiles.destiny.models import CarnageReportEntry as DestinyCarnageReportEntry
from apps.profiles.destiny.models import Character as DestinyCharacter
from apps.profiles.destiny.models import Profile as DestinyProfile
from apps.profiles.warframe.models import Affiliation as WarframeAffiliation
from apps.profiles.warframe.models import MissionStat as WarframeMissionStat
from apps.profiles.warframe.models import Profile as WarframeProfile
from apps.profiles.warframe.models import Snapshot as WarframeSnapshot
from apps.profiles.warframe.models import WeaponStat as WarframeWeaponStat

TEST_API_KEY = "test-api-key"


@pytest.fixture
def api_client():
    """Django test client for API requests."""
    return Client()


@pytest.fixture(autouse=True)
def _set_api_key(settings):
    settings.API_KEY = TEST_API_KEY


@pytest.fixture
def auth_headers():
    return {"HTTP_AUTHORIZATION": f"Bearer {TEST_API_KEY}"}


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


@pytest.fixture
def destiny_work(db):
    return Work.objects.create(name="Destiny 2", slug="destiny-2")


@pytest.fixture
def destiny_profile(db, destiny_work):
    return DestinyProfile.objects.create(
        work=destiny_work,
        bungie_name="Avalonstar",
        bungie_name_code=1234,
        membership_type=3,
        membership_id="4611686018428389571",
    )


@pytest.fixture
def destiny_character(db, destiny_profile):
    return DestinyCharacter.objects.create(
        profile=destiny_profile,
        character_id="2305843009301234567",
        character_class="warlock",
        race="awoken",
        gender="female",
        light_level=1810,
        minutes_played=85000,
    )


@pytest.fixture
def destiny_stats(db, destiny_profile, destiny_character):
    return DestinyAggregateStats.objects.create(
        profile=destiny_profile,
        character=destiny_character,
        scope="character",
        mode="raid",
        activities_entered=120,
        activities_cleared=87,
        kills=15234,
        deaths=402,
        assists=2105,
        kd_ratio=37.9,
        seconds_played=360000,
    )


@pytest.fixture
def destiny_account_stats(db, destiny_profile):
    return DestinyAggregateStats.objects.create(
        profile=destiny_profile,
        character=None,
        scope="account",
        mode="allPvE",
        activities_entered=5000,
        activities_cleared=4700,
        kills=250000,
        deaths=8500,
        assists=45000,
        kd_ratio=29.4,
        seconds_played=18000000,
    )


@pytest.fixture
def destiny_raid_activity(db, destiny_profile, destiny_character):
    from django.utils import timezone

    return DestinyActivity.objects.create(
        profile=destiny_profile,
        character=destiny_character,
        instance_id="1234567890",
        activity_hash=260765522,
        activity_name="Last Wish",
        mode=4,
        mode_name="Raid",
        mode_category="raid",
        period=timezone.now(),
        duration_seconds=3200,
        completed=True,
        kills=145,
        deaths=2,
        assists=38,
        score=0,
        kd_ratio=72.5,
        efficiency=91.5,
    )


@pytest.fixture
def destiny_pgcr(db, destiny_raid_activity, destiny_profile):
    report = DestinyCarnageReport.objects.create(
        activity=destiny_raid_activity,
        instance_id=destiny_raid_activity.instance_id,
        activity_hash=destiny_raid_activity.activity_hash,
        activity_name=destiny_raid_activity.activity_name,
        period=destiny_raid_activity.period,
    )
    DestinyCarnageReportEntry.objects.create(
        report=report,
        membership_id=destiny_profile.membership_id,
        membership_type=destiny_profile.membership_type,
        display_name="Avalonstar",
        character_class="warlock",
        light_level=1810,
        is_self=True,
        kills=145,
        deaths=2,
        assists=38,
        completed=True,
        time_played_seconds=3200,
    )
    DestinyCarnageReportEntry.objects.create(
        report=report,
        membership_id="9999",
        membership_type=3,
        display_name="Fireteam Mate",
        character_class="titan",
        light_level=1805,
        is_self=False,
        kills=98,
        deaths=5,
        assists=42,
        completed=True,
        time_played_seconds=3200,
    )
    return report


@pytest.fixture
def warframe_work(db):
    return Work.objects.create(name="Warframe", slug="warframe")


@pytest.fixture
def warframe_profile(db, warframe_work):
    return WarframeProfile.objects.create(
        work=warframe_work,
        account_id="5b2d428bf2f2ebde1070a2b1",
        display_name="Avalonstar",
        platform="pc",
        mastery_rank=11,
        player_level=12,
        title="/Lotus/Types/Items/Titles/SecondDreamTitle",
        missions_completed=691,
        missions_quit=35,
        missions_failed=46,
        time_played_seconds=429758,
        pickup_count=59449,
    )


@pytest.fixture
def warframe_weapon(db, warframe_profile):
    return WarframeWeaponStat.objects.create(
        profile=warframe_profile,
        weapon_path="/Lotus/Weapons/MK1Series/MK1Kunai",
        weapon_name="MK1 Kunai",
        fired=196,
        hits=76,
        kills=24,
        headshots=1,
        assists=4,
        equip_time_seconds=2583.72,
        xp=544432,
        accuracy=0.3878,
        headshot_rate=0.0417,
    )


@pytest.fixture
def warframe_weapons(db, warframe_profile):
    """A small set of weapons with varied stats for sort/filter tests."""
    return [
        WarframeWeaponStat.objects.create(
            profile=warframe_profile,
            weapon_path=f"/Lotus/Weapons/Test/Weapon{i}",
            weapon_name=f"Weapon {i}",
            fired=1000 * (i + 1),
            hits=800 * (i + 1),
            kills=100 * (i + 1),
            headshots=10 * (i + 1),
            assists=5 * (i + 1),
            equip_time_seconds=100.0 * (i + 1),
            xp=10000 * (i + 1),
            accuracy=0.8,
            headshot_rate=0.1,
        )
        for i in range(5)
    ]


@pytest.fixture
def warframe_mission(db, warframe_profile):
    return WarframeMissionStat.objects.create(
        profile=warframe_profile,
        node_tag="SolNode27",
        completes=42,
    )


@pytest.fixture
def warframe_affiliation(db, warframe_profile):
    return WarframeAffiliation.objects.create(
        profile=warframe_profile,
        syndicate_tag="CetusSyndicate",
        standing=12931,
        title_rank=1,
    )


@pytest.fixture
def warframe_snapshot(db, warframe_profile):
    return WarframeSnapshot.objects.create(
        profile=warframe_profile,
        trigger="manual",
        mastery_rank=11,
        time_played_seconds=429758,
        missions_completed=691,
        pickup_count=59449,
        total_weapon_kills=34229,
        weapons_tracked=188,
    )
