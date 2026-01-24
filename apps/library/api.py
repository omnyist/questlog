from __future__ import annotations

from datetime import datetime

from django.db import IntegrityError
from ninja import Router, Schema

from .models import Edition, Franchise, Genre, Work

router = Router(tags=["library"])


# Schemas
class FranchiseSchema(Schema):
    id: str
    name: str
    slug: str


class GenreSchema(Schema):
    id: str
    name: str
    slug: str
    igdb_id: int | None = None
    parent_id: str | None = None


class GenreCreateSchema(Schema):
    name: str
    slug: str
    igdb_id: int | None = None
    parent_id: str | None = None


class WorkGenresUpdateSchema(Schema):
    genre_ids: list[str]
    primary_genre_id: str | None = None


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


# Genre endpoints
@router.get("/genres", response=list[GenreSchema])
def list_genres(request):
    """List all genres."""
    return [
        GenreSchema(
            id=str(g.id),
            name=g.name,
            slug=g.slug,
            igdb_id=g.igdb_id,
            parent_id=str(g.parent_id) if g.parent_id else None,
        )
        for g in Genre.objects.all()
    ]


@router.post("/genres", response=GenreSchema)
def create_genre(request, data: GenreCreateSchema):
    """Create a new genre."""
    parent = None
    if data.parent_id:
        parent = Genre.objects.get(id=data.parent_id)

    genre = Genre.objects.create(
        name=data.name,
        slug=data.slug,
        igdb_id=data.igdb_id,
        parent=parent,
    )
    return GenreSchema(
        id=str(genre.id),
        name=genre.name,
        slug=genre.slug,
        igdb_id=genre.igdb_id,
        parent_id=str(genre.parent_id) if genre.parent_id else None,
    )


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


@router.get("/works/{slug}", response={200: WorkDetailSchema, 404: dict})
def get_work(request, slug: str):
    """Get a single work with all its editions."""
    try:
        w = Work.objects.select_related("franchise").prefetch_related("editions").get(slug=slug)
    except Work.DoesNotExist:
        return 404, {"error": "Work not found"}

    return 200, WorkDetailSchema(
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


@router.put("/works/{slug}/genres", response={200: dict, 404: dict})
def update_work_genres(request, slug: str, data: WorkGenresUpdateSchema):
    """Update genres for a work."""
    try:
        work = Work.objects.get(slug=slug)
    except Work.DoesNotExist:
        return 404, {"error": "Work not found"}

    # Set genres
    genres = Genre.objects.filter(id__in=data.genre_ids)
    work.genres.set(genres)

    # Set primary genre
    if data.primary_genre_id:
        try:
            work.primary_genre = Genre.objects.get(id=data.primary_genre_id)
        except Genre.DoesNotExist:
            pass
    else:
        work.primary_genre = None
    work.save()

    return 200, {
        "work": slug,
        "genres": [g.slug for g in work.genres.all()],
        "primary_genre": work.primary_genre.slug if work.primary_genre else None,
    }


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


@router.get("/editions/{slug}", response={200: EditionSchema, 404: dict})
def get_edition(request, slug: str):
    """Get a single edition by slug."""
    try:
        e = Edition.objects.get(slug=slug)
    except Edition.DoesNotExist:
        return 404, {"error": "Edition not found"}

    return 200, EditionSchema(
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


# Bulk import schemas
class BulkFranchiseSchema(Schema):
    name: str
    slug: str


class BulkWorkSchema(Schema):
    name: str
    slug: str
    franchise_slug: str | None = None
    original_release_year: int | None = None


class BulkEditionSchema(Schema):
    work_slug: str
    name: str
    slug: str
    edition_type: str = "original"
    igdb_id: int | None = None
    cover_url: str | None = None
    release_date: str | None = None
    summary: str | None = None
    platforms: list[str] | None = None
    igdb_data: dict | None = None


class BulkImportSchema(Schema):
    franchises: list[BulkFranchiseSchema]
    works: list[BulkWorkSchema]
    editions: list[BulkEditionSchema]


class BulkImportResultSchema(Schema):
    franchises_created: int
    franchises_skipped: int
    works_created: int
    works_skipped: int
    editions_created: int
    editions_skipped: int
    errors: list[str]


@router.post("/import", response=BulkImportResultSchema)
def bulk_import(request, data: BulkImportSchema):
    """Bulk import franchises, works, and editions."""
    result = {
        "franchises_created": 0,
        "franchises_skipped": 0,
        "works_created": 0,
        "works_skipped": 0,
        "editions_created": 0,
        "editions_skipped": 0,
        "errors": [],
    }

    # Create franchises first
    franchise_map = {}  # slug -> Franchise
    for f_data in data.franchises:
        try:
            franchise, created = Franchise.objects.get_or_create(
                slug=f_data.slug,
                defaults={"name": f_data.name},
            )
            franchise_map[f_data.slug] = franchise
            if created:
                result["franchises_created"] += 1
            else:
                result["franchises_skipped"] += 1
        except IntegrityError as e:
            result["errors"].append(f"Franchise {f_data.slug}: {e}")

    # Create works
    work_map = {}  # slug -> Work
    for w_data in data.works:
        try:
            franchise = franchise_map.get(w_data.franchise_slug) if w_data.franchise_slug else None
            work, created = Work.objects.get_or_create(
                slug=w_data.slug,
                defaults={
                    "name": w_data.name,
                    "franchise": franchise,
                    "original_release_year": w_data.original_release_year,
                },
            )
            work_map[w_data.slug] = work
            if created:
                result["works_created"] += 1
            else:
                result["works_skipped"] += 1
        except IntegrityError as e:
            result["errors"].append(f"Work {w_data.slug}: {e}")

    # Create editions
    for e_data in data.editions:
        try:
            work = work_map.get(e_data.work_slug)
            if not work:
                work = Work.objects.get(slug=e_data.work_slug)
                work_map[e_data.work_slug] = work

            release_date = None
            if e_data.release_date:
                release_date = datetime.strptime(e_data.release_date, "%Y-%m-%d").date()

            edition, created = Edition.objects.get_or_create(
                slug=e_data.slug,
                defaults={
                    "work": work,
                    "name": e_data.name,
                    "edition_type": e_data.edition_type,
                    "igdb_id": e_data.igdb_id,
                    "cover_url": e_data.cover_url or "",
                    "release_date": release_date,
                    "summary": e_data.summary or "",
                    "platforms": e_data.platforms or [],
                    "igdb_data": e_data.igdb_data or {},
                    "last_synced": datetime.now() if e_data.igdb_id else None,
                },
            )
            if created:
                result["editions_created"] += 1
            else:
                result["editions_skipped"] += 1
        except IntegrityError as e:
            result["errors"].append(f"Edition {e_data.slug}: {e}")
        except Work.DoesNotExist:
            result["errors"].append(f"Edition {e_data.slug}: Work {e_data.work_slug} not found")

    return BulkImportResultSchema(**result)
