from __future__ import annotations

from django.conf import settings
from ninja import Router
from ninja import Schema

from .igdb import IGDBClient
from .steam import SteamClient

router = Router(tags=["igdb"])


class IGDBGameSchema(Schema):
    igdb_id: int
    name: str
    slug: str
    cover_url: str | None = None
    release_date: str | None = None
    summary: str | None = None
    igdb_data: dict | None = None


class IGDBSearchResponse(Schema):
    results: list[IGDBGameSchema]


@router.get("/igdb/search", response=IGDBSearchResponse)
async def search_igdb(request, q: str, limit: int = 10):
    """Search IGDB for games by name."""
    client = IGDBClient()
    results = await client.search(q, limit=limit)

    games = []
    for game in results:
        cover_url = None
        if cover := game.get("cover"):
            cover_id = cover.get("url", "").split("/")[-1].replace(".jpg", "")
            if cover_id:
                cover_url = IGDBClient.get_cover_url(cover_id)

        release_date = None
        if timestamp := game.get("first_release_date"):
            from datetime import datetime

            release_date = datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d")

        games.append(
            IGDBGameSchema(
                igdb_id=game["id"],
                name=game["name"],
                slug=game.get("slug", ""),
                cover_url=cover_url,
                release_date=release_date,
                summary=game.get("summary", ""),
                igdb_data=game,
            )
        )

    return IGDBSearchResponse(results=games)


# ---- Steam proxy endpoints (for Synthform's co-working overlay) ----


class SteamPlayerSchema(Schema):
    personaName: str
    personaState: int
    currentGame: str | None = None
    currentGameId: str | None = None
    avatarUrl: str


class SteamRecentGameSchema(Schema):
    appId: int
    name: str
    playtime2Weeks: int
    playtimeForever: int
    iconUrl: str


@router.get("/steam/player", response=SteamPlayerSchema, tags=["steam"])
async def steam_player(request):
    """Current Steam player state. Proxies Steam's GetPlayerSummaries."""
    client = SteamClient()
    summary = await client.get_player_summary(settings.STEAM_ID)
    return SteamPlayerSchema(
        personaName=summary.get("personaname", ""),
        personaState=int(summary.get("personastate", 0) or 0),
        currentGame=summary.get("gameextrainfo") or None,
        currentGameId=summary.get("gameid") or None,
        avatarUrl=summary.get("avatarfull", ""),
    )


@router.get("/steam/recent", response=list[SteamRecentGameSchema], tags=["steam"])
async def steam_recent(request, count: int = 5):
    """Recently played Steam games. Proxies GetRecentlyPlayedGames."""
    client = SteamClient()
    count = max(1, min(count, 20))
    games = await client.get_recent_games(settings.STEAM_ID, count=count)
    return [
        SteamRecentGameSchema(
            appId=game.get("appid", 0),
            name=game.get("name", ""),
            playtime2Weeks=int(game.get("playtime_2weeks", 0) or 0),
            playtimeForever=int(game.get("playtime_forever", 0) or 0),
            iconUrl=SteamClient.game_icon_url(
                game.get("appid", 0),
                game.get("img_icon_url", ""),
            ),
        )
        for game in games
    ]
