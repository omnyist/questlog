from __future__ import annotations

from datetime import datetime

from django.db import IntegrityError
from ninja import Router, Schema

from .models import Edition, Franchise, Work

router = Router(tags=["library"])


# Schemas
class FranchiseSchema(Schema):
    id: str
    name: str
    slug: str


class WorkSchema(Schema):
    id: str
    name: str
    slug: str
    franchise: FranchiseSchema | None = None
    original_release_year: int | None = None


class EditionSchema(Schema):
    id: str
    work_id: str
    name: str
    slug: str
    edition_type: str
    igdb_id: int | None = None
    cover_url: str | None = None
    release_date: str | None = None
    summary: str | None = None


class WorkDetailSchema(Schema):
    id: str
    name: str
    slug: str
    franchise: FranchiseSchema | None = None
    original_release_year: int | None = None
    editions: list[EditionSchema] = []


class EditionCreateSchema(Schema):
    work_id: str
    name: str
    slug: str
    edition_type: str = "original"
    igdb_id: int | None = None
    cover_url: str | None = None
    release_date: str | None = None
    summary: str | None = None
    platforms: list[str] | None = None
    igdb_data: dict | None = None


# Franchise endpoints
@router.get("/franchises", response=list[FranchiseSchema])
def list_franchises(request):
    """List all franchises."""
    return [
        FranchiseSchema(id=str(f.id), name=f.name, slug=f.slug)
        for f in Franchise.objects.all()
    ]


# Work endpoints
@router.get("/works", response=list[WorkSchema])
def list_works(request, franchise: str | None = None, limit: int = 100, offset: int = 0):
    """List all works, optionally filtered by franchise slug."""
    qs = Work.objects.select_related("franchise")
    if franchise:
        qs = qs.filter(franchise__slug=franchise)
    works = qs[offset : offset + limit]
    return [
        WorkSchema(
            id=str(w.id),
            name=w.name,
            slug=w.slug,
            franchise=FranchiseSchema(
                id=str(w.franchise.id), name=w.franchise.name, slug=w.franchise.slug
            ) if w.franchise else None,
            original_release_year=w.original_release_year,
        )
        for w in works
    ]


@router.get("/works/{slug}", response=WorkDetailSchema)
def get_work(request, slug: str):
    """Get a single work with all its editions."""
    w = Work.objects.select_related("franchise").prefetch_related("editions").get(slug=slug)
    return WorkDetailSchema(
        id=str(w.id),
        name=w.name,
        slug=w.slug,
        franchise=FranchiseSchema(
            id=str(w.franchise.id), name=w.franchise.name, slug=w.franchise.slug
        ) if w.franchise else None,
        original_release_year=w.original_release_year,
        editions=[
            EditionSchema(
                id=str(e.id),
                work_id=str(e.work_id),
                name=e.name,
                slug=e.slug,
                edition_type=e.edition_type,
                igdb_id=e.igdb_id,
                cover_url=e.cover_url or None,
                release_date=e.release_date.isoformat() if e.release_date else None,
                summary=e.summary or None,
            )
            for e in w.editions.all()
        ],
    )


# Edition endpoints
@router.get("/editions", response=list[EditionSchema])
def list_editions(request, work: str | None = None, limit: int = 100, offset: int = 0):
    """List all editions, optionally filtered by work slug."""
    qs = Edition.objects.select_related("work")
    if work:
        qs = qs.filter(work__slug=work)
    editions = qs[offset : offset + limit]
    return [
        EditionSchema(
            id=str(e.id),
            work_id=str(e.work_id),
            name=e.name,
            slug=e.slug,
            edition_type=e.edition_type,
            igdb_id=e.igdb_id,
            cover_url=e.cover_url or None,
            release_date=e.release_date.isoformat() if e.release_date else None,
            summary=e.summary or None,
        )
        for e in editions
    ]


@router.get("/editions/{slug}", response=EditionSchema)
def get_edition(request, slug: str):
    """Get a single edition by slug."""
    e = Edition.objects.get(slug=slug)
    return EditionSchema(
        id=str(e.id),
        work_id=str(e.work_id),
        name=e.name,
        slug=e.slug,
        edition_type=e.edition_type,
        igdb_id=e.igdb_id,
        cover_url=e.cover_url or None,
        release_date=e.release_date.isoformat() if e.release_date else None,
        summary=e.summary or None,
    )


@router.post("/editions", response=EditionSchema)
def create_edition(request, data: EditionCreateSchema):
    """Create a new edition."""
    work = Work.objects.get(id=data.work_id)

    release_date = None
    if data.release_date:
        release_date = datetime.strptime(data.release_date, "%Y-%m-%d").date()

    edition = Edition.objects.create(
        work=work,
        name=data.name,
        slug=data.slug,
        edition_type=data.edition_type,
        igdb_id=data.igdb_id,
        cover_url=data.cover_url or "",
        release_date=release_date,
        summary=data.summary or "",
        platforms=data.platforms or [],
        igdb_data=data.igdb_data or {},
        last_synced=datetime.now() if data.igdb_id else None,
    )
    return EditionSchema(
        id=str(edition.id),
        work_id=str(edition.work_id),
        name=edition.name,
        slug=edition.slug,
        edition_type=edition.edition_type,
        igdb_id=edition.igdb_id,
        cover_url=edition.cover_url or None,
        release_date=edition.release_date.isoformat() if edition.release_date else None,
        summary=edition.summary or None,
    )
