from __future__ import annotations

from ninja import Router
from ninja import Schema

from .igdb import IGDBClient

router = Router(tags=["igdb"])


class IGDBGameSchema(Schema):
    igdb_id: int
    name: str
    slug: str
    cover_url: str | None = None
    release_date: str | None = None
    summary: str | None = None


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
            )
        )

    return IGDBSearchResponse(results=games)
