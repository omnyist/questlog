from __future__ import annotations

from django.conf import settings
from ninja.security import HttpBearer


class ApiKeyAuth(HttpBearer):
    def authenticate(self, request, token):
        if token and token == settings.API_KEY:
            return token
        return None
