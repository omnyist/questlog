from __future__ import annotations

"""
IGDB API Client

Authenticates via Twitch OAuth (client credentials flow).
Requires IGDB_CLIENT_ID and IGDB_CLIENT_SECRET in settings.

Usage:
    client = IGDBClient()
    results = await client.search("Xenoblade Chronicles 3")
    game = await client.get_by_id(12345)
"""

import httpx
from django.conf import settings


class IGDBClient:
    BASE_URL = "https://api.igdb.com/v4"
    AUTH_URL = "https://id.twitch.tv/oauth2/token"

    def __init__(self):
        self.client_id = settings.IGDB_CLIENT_ID
        self.client_secret = settings.IGDB_CLIENT_SECRET
        self._access_token = None

    async def _get_access_token(self) -> str:
        """Get OAuth access token from Twitch."""
        if self._access_token:
            return self._access_token

        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.AUTH_URL,
                params={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "grant_type": "client_credentials",
                },
            )
            response.raise_for_status()
            data = response.json()
            self._access_token = data["access_token"]
            return self._access_token

    async def _request(self, endpoint: str, body: str) -> dict | list:
        """Make authenticated request to IGDB."""
        token = await self._get_access_token()

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.BASE_URL}/{endpoint}",
                headers={
                    "Client-ID": self.client_id,
                    "Authorization": f"Bearer {token}",
                },
                content=body,
            )
            response.raise_for_status()
            return response.json()

    async def search(self, query: str, limit: int = 10) -> list[dict]:
        """Search for games by name."""
        body = f'''
            search "{query}";
            fields name, slug, cover.url, first_release_date, summary,
                   genres.name, platforms.name, franchise.name, collection.name;
            limit {limit};
        '''
        return await self._request("games", body)

    async def get_by_id(self, igdb_id: int) -> dict | None:
        """Fetch full game data by IGDB ID."""
        body = f'''
            where id = {igdb_id};
            fields name, slug, cover.url, first_release_date, summary,
                   genres.name, platforms.name, franchise.name, collection.name,
                   storyline, rating, aggregated_rating;
        '''
        results = await self._request("games", body)
        return results[0] if results else None

    @staticmethod
    def get_cover_url(cover_id: str, size: str = "cover_big") -> str:
        """
        Get cover image URL.

        Sizes: cover_small, cover_big, 720p, 1080p
        """
        return f"https://images.igdb.com/igdb/image/upload/t_{size}/{cover_id}.jpg"
