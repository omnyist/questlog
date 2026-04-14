from __future__ import annotations

from unittest.mock import AsyncMock
from unittest.mock import patch

import pytest


@pytest.fixture
def fake_player_summary():
    return {
        "steamid": "76561198009545200",
        "personaname": "Avalonstar",
        "personastate": 1,
        "gameid": "230410",
        "gameextrainfo": "Warframe",
        "avatarfull": "https://avatars.steamstatic.com/avatar_full.jpg",
    }


@pytest.fixture
def fake_recent_games():
    return [
        {
            "appid": 230410,
            "name": "Warframe",
            "playtime_2weeks": 1200,
            "playtime_forever": 50000,
            "img_icon_url": "abc123def456",
        },
        {
            "appid": 570,
            "name": "Dota 2",
            "playtime_2weeks": 0,
            "playtime_forever": 9000,
            "img_icon_url": "0bbb000ccc",
        },
    ]


@pytest.mark.django_db
class TestSteamPlayer:
    def test_player_in_game(self, api_client, fake_player_summary):
        with patch(
            "apps.integrations.api.SteamClient.get_player_summary",
            new=AsyncMock(return_value=fake_player_summary),
        ):
            response = api_client.get("/api/steam/player")
        assert response.status_code == 200
        data = response.json()
        assert data["personaName"] == "Avalonstar"
        assert data["personaState"] == 1
        assert data["currentGame"] == "Warframe"
        assert data["currentGameId"] == "230410"
        assert data["avatarUrl"] == "https://avatars.steamstatic.com/avatar_full.jpg"

    def test_player_offline(self, api_client):
        offline = {
            "personaname": "Avalonstar",
            "personastate": 0,
            "avatarfull": "https://avatars.steamstatic.com/avatar_full.jpg",
        }
        with patch(
            "apps.integrations.api.SteamClient.get_player_summary",
            new=AsyncMock(return_value=offline),
        ):
            response = api_client.get("/api/steam/player")
        assert response.status_code == 200
        data = response.json()
        assert data["currentGame"] is None
        assert data["currentGameId"] is None
        assert data["personaState"] == 0

    def test_player_empty_response(self, api_client):
        with patch(
            "apps.integrations.api.SteamClient.get_player_summary",
            new=AsyncMock(return_value={}),
        ):
            response = api_client.get("/api/steam/player")
        assert response.status_code == 200
        data = response.json()
        assert data["personaName"] == ""
        assert data["currentGame"] is None


@pytest.mark.django_db
class TestSteamRecent:
    def test_list_recent(self, api_client, fake_recent_games):
        with patch(
            "apps.integrations.api.SteamClient.get_recent_games",
            new=AsyncMock(return_value=fake_recent_games),
        ):
            response = api_client.get("/api/steam/recent")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

        warframe = data[0]
        assert warframe["appId"] == 230410
        assert warframe["name"] == "Warframe"
        assert warframe["playtime2Weeks"] == 1200
        assert warframe["playtimeForever"] == 50000
        assert "230410" in warframe["iconUrl"]
        assert warframe["iconUrl"].endswith("abc123def456.jpg")

    def test_recent_empty(self, api_client):
        with patch(
            "apps.integrations.api.SteamClient.get_recent_games",
            new=AsyncMock(return_value=[]),
        ):
            response = api_client.get("/api/steam/recent")
        assert response.status_code == 200
        assert response.json() == []

    def test_recent_count_clamp_low(self, api_client, fake_recent_games):
        captured: dict = {}

        async def fake(_self, _steam_id, count: int = 5):
            captured["count"] = count
            return fake_recent_games

        with patch(
            "apps.integrations.api.SteamClient.get_recent_games",
            new=fake,
        ):
            response = api_client.get("/api/steam/recent?count=0")
        assert response.status_code == 200
        assert captured["count"] == 1  # clamped to min 1

    def test_recent_count_clamp_high(self, api_client, fake_recent_games):
        captured: dict = {}

        async def fake(_self, _steam_id, count: int = 5):
            captured["count"] = count
            return fake_recent_games

        with patch(
            "apps.integrations.api.SteamClient.get_recent_games",
            new=fake,
        ):
            response = api_client.get("/api/steam/recent?count=999")
        assert response.status_code == 200
        assert captured["count"] == 20  # clamped to max 20
