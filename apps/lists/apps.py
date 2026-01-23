from __future__ import annotations

from django.apps import AppConfig


class ListsConfig(AppConfig):
    name = "apps.lists"
    verbose_name = "Game Lists"

    def ready(self):
        from . import signals  # noqa: F401
