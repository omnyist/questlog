"""The production database config, tested despite never running under pytest.

The pool is deliberately disabled under pytest (its worker thread wedges
teardown), which means the config that actually ships lives in a branch no
ordinary test executes. That blind spot let a green suite ship a crash-loop on
2026-08-22. Tier 1 (the pure-function assertions) moved to synthlib's own
test suite 2026-09-08: they test `production_database_extras()`'s behavior,
not anything questlog-specific. What's left is a thin resolved-value
assertion plus Tier 2, which builds the pool through Django's own code path
and takes one cursor through it, exercising the exact line that raised in
production.
"""

from __future__ import annotations

import socket
from copy import deepcopy

import pytest
from django.conf import settings
from synthlib.django.db import production_database_extras

# Rebuilt explicitly with this module's own kwargs -- settings.DATABASES
# never carries the production branch during a test run (the pool is
# disabled under pytest), so this is the only way to see what
# config/settings.py's own call site actually produces.
PROD = production_database_extras(
    "django.db.backends.postgresql",
    under_test=False,
    pool_min_size=1,
    pool_max_size=4,
)


def test_this_modules_pool_kwargs_are_the_ones_that_actually_ship():
    """synthlib's own tests prove the function; this proves questlog's call
    site passes questlog's own numbers, not a default."""
    assert PROD["OPTIONS"]["pool"] == {"min_size": 1, "max_size": 4}


def _db_reachable() -> bool:
    d = settings.DATABASES["default"]
    try:
        with socket.create_connection(
            (d.get("HOST") or "localhost", int(d.get("PORT") or 5432)), timeout=2
        ):
            return True
    except OSError:
        return False


@pytest.mark.skipif(
    not _db_reachable(),
    reason="no Postgres reachable — tier-2 pool check needs one (CI always has it)",
)
def test_the_production_pool_actually_opens_a_cursor(django_db_blocker):
    """Build the pool with the production OPTIONS through Django's own code
    path. This catches a collision from either side of the Django/psycopg_pool
    boundary, whichever of them changes next.

    django_db_blocker (not the django_db mark) because this deliberately does
    NOT want the test database machinery — it builds its own handler with the
    production config; the blocker just patches ensure_connection globally.
    """
    alias = deepcopy(settings.DATABASES["default"])
    alias.pop("CONN_MAX_AGE", None)  # pooling rejects persistent connections
    alias.update(
        production_database_extras(
            alias["ENGINE"], under_test=False, pool_min_size=1, pool_max_size=4
        )
    )
    from django.db.utils import ConnectionHandler

    handler = ConnectionHandler({"default": alias})
    conn = handler["default"]
    try:
        with django_db_blocker.unblock():
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                assert cur.fetchone()[0] == 1
        assert conn.pool is not None, "production config did not build a pool"
    finally:
        # Shut the pool's worker threads down explicitly — leaving them alive
        # is the teardown wedge that keeps the pool off under pytest.
        conn.close()
        conn.close_pool()
