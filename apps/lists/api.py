from __future__ import annotations

from datetime import datetime

from ninja import Router, Schema

from apps.library.models import Work

from .models import Entry, List, ListActivity

router = Router(tags=["lists"])


# Schemas
class ListSchema(Schema):
    id: str
    slug: str
    name: str
    description: str
    is_ranked: bool
    entry_count: int


class EntrySchema(Schema):
    id: str
    work_id: str
    work_name: str
    work_slug: str
    position: int | None = None
    notes: str


class ListDetailSchema(Schema):
    id: str
    slug: str
    name: str
    description: str
    is_ranked: bool
    entries: list[EntrySchema]


class ListCreateSchema(Schema):
    slug: str
    name: str
    description: str = ""
    is_ranked: bool = False


class EntryCreateSchema(Schema):
    work_slug: str
    position: int | None = None
    notes: str = ""


class BulkEntryCreateSchema(Schema):
    entries: list[EntryCreateSchema]


class BulkEntryResultSchema(Schema):
    created: int
    skipped: int
    errors: list[str]


# List endpoints
@router.get("/lists", response=list[ListSchema])
def list_lists(request):
    """List all lists."""
    lists = List.objects.all()
    return [
        ListSchema(
            id=str(lst.id),
            slug=lst.slug,
            name=lst.name,
            description=lst.description,
            is_ranked=lst.is_ranked,
            entry_count=lst.entries.count(),
        )
        for lst in lists
    ]


@router.post("/lists", response=ListSchema)
def create_list(request, data: ListCreateSchema):
    """Create a new list."""
    lst = List.objects.create(
        slug=data.slug,
        name=data.name,
        description=data.description,
        is_ranked=data.is_ranked,
    )
    return ListSchema(
        id=str(lst.id),
        slug=lst.slug,
        name=lst.name,
        description=lst.description,
        is_ranked=lst.is_ranked,
        entry_count=0,
    )


@router.get("/lists/{slug}", response={200: ListDetailSchema, 404: dict})
def get_list(request, slug: str):
    """Get a list with all its entries."""
    try:
        lst = List.objects.prefetch_related("entries__work").get(slug=slug)
    except List.DoesNotExist:
        return 404, {"error": "List not found"}

    return 200, ListDetailSchema(
        id=str(lst.id),
        slug=lst.slug,
        name=lst.name,
        description=lst.description,
        is_ranked=lst.is_ranked,
        entries=[
            EntrySchema(
                id=str(e.id),
                work_id=str(e.work_id),
                work_name=e.work.name,
                work_slug=e.work.slug,
                position=e.position,
                notes=e.notes,
            )
            for e in lst.entries.all()
        ],
    )


# Entry endpoints
@router.post("/lists/{slug}/entries", response={200: EntrySchema, 404: dict})
def add_entry(request, slug: str, data: EntryCreateSchema):
    """Add a work to a list."""
    try:
        lst = List.objects.get(slug=slug)
    except List.DoesNotExist:
        return 404, {"error": "List not found"}

    try:
        work = Work.objects.get(slug=data.work_slug)
    except Work.DoesNotExist:
        return 404, {"error": "Work not found"}

    entry = Entry.objects.create(
        list=lst,
        work=work,
        position=data.position,
        notes=data.notes,
    )
    return 200, EntrySchema(
        id=str(entry.id),
        work_id=str(entry.work_id),
        work_name=entry.work.name,
        work_slug=entry.work.slug,
        position=entry.position,
        notes=entry.notes,
    )


@router.post("/lists/{slug}/entries/bulk", response=BulkEntryResultSchema)
def bulk_add_entries(request, slug: str, data: BulkEntryCreateSchema):
    """Bulk add works to a list."""
    lst = List.objects.get(slug=slug)

    result = {"created": 0, "skipped": 0, "errors": []}

    for entry_data in data.entries:
        try:
            work = Work.objects.get(slug=entry_data.work_slug)

            entry, created = Entry.objects.get_or_create(
                list=lst,
                work=work,
                defaults={
                    "position": entry_data.position,
                    "notes": entry_data.notes,
                },
            )

            if created:
                result["created"] += 1
            else:
                result["skipped"] += 1

        except Work.DoesNotExist:
            result["errors"].append(f"Work not found: {entry_data.work_slug}")
        except Exception as e:
            result["errors"].append(f"{entry_data.work_slug}: {e}")

    return BulkEntryResultSchema(**result)


# Activity schemas
class ListActivitySchema(Schema):
    id: str
    timestamp: datetime
    verb: str
    entries: list[str]
    metadata: dict


# Activity endpoints
@router.get("/lists/{slug}/activity", response={200: list[ListActivitySchema], 404: dict})
def get_list_activity(request, slug: str, limit: int = 50):
    """Get activity history for a list."""
    try:
        lst = List.objects.get(slug=slug)
    except List.DoesNotExist:
        return 404, {"error": "List not found"}

    activities = lst.activity.all()[:limit]
    return 200, [
        ListActivitySchema(
            id=str(a.id),
            timestamp=a.timestamp,
            verb=a.verb,
            entries=a.entries,
            metadata=a.metadata,
        )
        for a in activities
    ]
