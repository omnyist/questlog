from __future__ import annotations

import hmac

from django.conf import settings
from ninja.security import HttpBearer


class ApiKeyAuth(HttpBearer):
    def authenticate(self, request, token):
        if token and settings.API_KEY and hmac.compare_digest(token, settings.API_KEY):
            return token
        return None
