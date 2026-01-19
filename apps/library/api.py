from __future__ import annotations

from datetime import datetime

from django.db import IntegrityError
from ninja import Router
from ninja import Schema

from .models import Game

router = Router(tags=["library"])


class GameSchema(Schema):
    id: str
    igdb_id: int | None
    slug: str
    name: str
    cover_url: str | None
    release_date: str | None
    summary: str | None


class GameCreateSchema(Schema):
    igdb_id: int | None = None
    slug: str
    name: str
    cover_url: str | None = None
    release_date: str | None = None
    summary: str | None = None
    igdb_data: dict | None = None


class BulkImportGameSchema(Schema):
    igdb_id: int | None = None
    slug: str
    name: str
    cover_url: str | None = None
    release_date: str | None = None
    summary: str | None = None
    igdb_data: dict | None = None


class BulkImportRequest(Schema):
    games: list[BulkImportGameSchema]


class BulkImportResult(Schema):
    created: int
    skipped: int
    errors: list[str]


@router.get("/games", response=list[GameSchema])
def list_games(request, limit: int = 100, offset: int = 0):
    """List all games in the library."""
    games = Game.objects.all()[offset : offset + limit]
    return [
        GameSchema(
            id=str(g.id),
            igdb_id=g.igdb_id,
            slug=g.slug,
            name=g.name,
            cover_url=g.cover_url or None,
            release_date=g.release_date.isoformat() if g.release_date else None,
            summary=g.summary or None,
        )
        for g in games
    ]


@router.get("/games/{slug}", response=GameSchema)
def get_game(request, slug: str):
    """Get a single game by slug."""
    g = Game.objects.get(slug=slug)
    return GameSchema(
        id=str(g.id),
        igdb_id=g.igdb_id,
        slug=g.slug,
        name=g.name,
        cover_url=g.cover_url or None,
        release_date=g.release_date.isoformat() if g.release_date else None,
        summary=g.summary or None,
    )


@router.post("/games", response=GameSchema)
def create_game(request, data: GameCreateSchema):
    """Create a new game."""
    release_date = None
    if data.release_date:
        release_date = datetime.strptime(data.release_date, "%Y-%m-%d").date()

    game = Game.objects.create(
        igdb_id=data.igdb_id,
        slug=data.slug,
        name=data.name,
        cover_url=data.cover_url or "",
        release_date=release_date,
        summary=data.summary or "",
        igdb_data=data.igdb_data or {},
        last_synced=datetime.now() if data.igdb_id else None,
    )
    return GameSchema(
        id=str(game.id),
        igdb_id=game.igdb_id,
        slug=game.slug,
        name=game.name,
        cover_url=game.cover_url or None,
        release_date=game.release_date.isoformat() if game.release_date else None,
        summary=game.summary or None,
    )


@router.post("/games/bulk", response=BulkImportResult)
def bulk_import_games(request, data: BulkImportRequest):
    """Bulk import games. Skips games that already exist by igdb_id or slug."""
    created = 0
    skipped = 0
    errors = []

    for game_data in data.games:
        try:
            # Check if game already exists
            existing = None
            if game_data.igdb_id:
                existing = Game.objects.filter(igdb_id=game_data.igdb_id).first()
            if not existing:
                existing = Game.objects.filter(slug=game_data.slug).first()

            if existing:
                skipped += 1
                continue

            release_date = None
            if game_data.release_date:
                release_date = datetime.strptime(game_data.release_date, "%Y-%m-%d").date()

            Game.objects.create(
                igdb_id=game_data.igdb_id,
                slug=game_data.slug,
                name=game_data.name,
                cover_url=game_data.cover_url or "",
                release_date=release_date,
                summary=game_data.summary or "",
                igdb_data=game_data.igdb_data or {},
                last_synced=datetime.now() if game_data.igdb_id else None,
            )
            created += 1
        except IntegrityError as e:
            errors.append(f"{game_data.name}: {str(e)}")
        except Exception as e:
            errors.append(f"{game_data.name}: {str(e)}")

    return BulkImportResult(created=created, skipped=skipped, errors=errors)
