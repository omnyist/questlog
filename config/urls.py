from __future__ import annotations

from django.contrib import admin
from django.urls import path
from ninja import NinjaAPI

from apps.integrations.api import router as integrations_router
from apps.library.api import router as library_router
from apps.lists.api import router as lists_router

api = NinjaAPI(
    title="Questlog API",
    description="Personal gaming data backend",
    version="0.1.0",
)

api.add_router("/", integrations_router)
api.add_router("/", library_router)
api.add_router("/", lists_router)

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", api.urls),
]
