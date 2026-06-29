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
from apps.profiles.warframe.models import CatalogItem as WarframeCatalogItem
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


@pytest.fixture
def warframe_mastery_history(db, warframe_profile):
    """Snapshots spanning MR11 -> MR13 for progression testing."""
    from django.utils import timezone

    base = timezone.now() - timezone.timedelta(days=10)
    ranks = [11, 11, 12, 12, 12, 13]
    snaps = []
    for i, rank in enumerate(ranks):
        s = WarframeSnapshot.objects.create(
            profile=warframe_profile,
            trigger="session_end",
            mastery_rank=rank,
            time_played_seconds=400000 + i * 1000,
            missions_completed=690 + i,
        )
        # auto_now_add ignores explicit values, so stamp captured_at after create
        WarframeSnapshot.objects.filter(pk=s.pk).update(
            captured_at=base + timezone.timedelta(days=i)
        )
        snaps.append(s)
    return snaps


@pytest.fixture
def warframe_catalog(db):
    """Two real Warframes + one sentinel that should be excluded from frames."""
    items = [
        WarframeCatalogItem.objects.create(
            unique_name="/Lotus/Powersuits/Runner/GaussPrime",
            name="Gauss Prime",
            category="Warframes",
            item_type="Warframe",
            mastery_req=0,
            masterable=True,
            is_prime=True,
            image_name="gauss-prime.png",
        ),
        WarframeCatalogItem.objects.create(
            unique_name="/Lotus/Powersuits/Excalibur/Excalibur",
            name="Excalibur",
            category="Warframes",
            item_type="Warframe",
            mastery_req=0,
            masterable=True,
            is_prime=False,
            image_name="excalibur.png",
        ),
        WarframeCatalogItem.objects.create(
            unique_name="/Lotus/Types/Sentinels/SentinelPowersuits/PrimeHeliosPowerSuit",
            name="Helios Prime",
            category="Sentinels",
            item_type="Sentinel",
            mastery_req=0,
            masterable=True,
            is_prime=True,
            image_name="helios-prime.png",
        ),
    ]
    return items


@pytest.fixture
def warframe_completion_setup(db, warframe_work):
    """Profile with XPInfo + catalog: 3 masterable items, 2 mastered."""
    profile = WarframeProfile.objects.create(
        work=warframe_work,
        account_id="completion-test",
        display_name="Avalonstar",
        platform="pc",
        mastery_rank=25,
        profile_data={
            "LoadOutInventory": {
                "XPInfo": [
                    {"ItemType": "/Lotus/Powersuits/Runner/GaussPrime", "XP": 10_000_000},  # frame, maxed
                    {"ItemType": "/Lotus/Weapons/Tenno/Rifle/TennoAR", "XP": 600_000},       # weapon, maxed (>=450k)
                    {"ItemType": "/Lotus/Weapons/Tenno/Pistol/Lato", "XP": 50_000},          # weapon, NOT maxed
                ]
            }
        },
    )
    WarframeCatalogItem.objects.create(
        unique_name="/Lotus/Powersuits/Runner/GaussPrime",
        name="Gauss Prime", category="Warframes", masterable=True, max_level_cap=30,
    )
    WarframeCatalogItem.objects.create(
        unique_name="/Lotus/Weapons/Tenno/Rifle/TennoAR",
        name="Soma", category="Primary", masterable=True, max_level_cap=30,
    )
    WarframeCatalogItem.objects.create(
        unique_name="/Lotus/Weapons/Tenno/Pistol/Lato",
        name="Lato", category="Secondary", masterable=True, max_level_cap=30,
    )
    # A non-masterable item that must be excluded from totals.
    WarframeCatalogItem.objects.create(
        unique_name="/Lotus/Types/Sentinels/Sentinel",
        name="Some Skin", category="Sentinels", masterable=False, max_level_cap=30,
    )
    return profile


@pytest.fixture
def warframe_remaining_setup(db, warframe_work):
    """Profile (MR27) + catalog covering mastered/unmastered/vaulted/gated cases."""
    profile = WarframeProfile.objects.create(
        work=warframe_work,
        account_id="remaining-test",
        display_name="Avalonstar",
        platform="pc",
        mastery_rank=27,
        profile_data={
            "LoadOutInventory": {
                "XPInfo": [
                    {"ItemType": "/w/maxed", "XP": 999_999},  # mastered → excluded
                ]
            }
        },
    )
    rows = [
        # (unique_name, name, category, req, prime, vaulted, acquisition, tags)
        ("/w/maxed", "Maxed Rifle", "Primary", 0, False, False, "Market", []),
        ("/w/base", "Base Rifle", "Primary", 5, False, False, "Market", []),
        ("/f/frame", "Cool Frame", "Warframes", 8, False, False, "Foundry", []),
        ("/w/vault", "Vaulted Prime", "Melee", 0, True, True, "Void Relic", ["Prime"]),
        ("/w/gated", "Gated Gun", "Secondary", 30, False, False, "Kuva Lich", ["Kuva Lich"]),
    ]
    for uname, name, cat, req, prime, vaulted, acq, tags in rows:
        WarframeCatalogItem.objects.create(
            unique_name=uname, name=name, category=cat, mastery_req=req,
            masterable=True, max_level_cap=30, is_prime=prime, vaulted=vaulted,
            acquisition=acq, tags=tags,
        )
    return profile


@pytest.fixture
def warframe_frame_weapons(db, warframe_profile):
    """WeaponStat rows: two frames + a sentinel with the highest equip time."""
    paths = [
        # (path, name, equip_time, kills) — sentinel has MOST equip time
        ("/Lotus/Types/Sentinels/SentinelPowersuits/PrimeHeliosPowerSuit", "Prime Helios Power Suit", 486233, 73),
        ("/Lotus/Powersuits/Runner/GaussPrime", "Gauss Prime", 192849, 3470),
        ("/Lotus/Powersuits/Excalibur/Excalibur", "Excalibur", 80000, 1500),
    ]
    rows = []
    for path, name, equip, kills in paths:
        rows.append(
            WarframeWeaponStat.objects.create(
                profile=warframe_profile,
                weapon_path=path,
                weapon_name=name,
                equip_time_seconds=equip,
                kills=kills,
            )
        )
    return rows
