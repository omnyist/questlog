from __future__ import annotations

import time

import redis
from django.conf import settings
from django.db import connection
from django.http import HttpRequest
from django.http import JsonResponse

from config.heartbeat import KEY_PREFIX


def health_check(request: HttpRequest) -> JsonResponse:
    """Basic health check endpoint for monitoring."""
    status = {"status": "ok", "services": {}}
    http_status = 200

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        status["services"]["database"] = "ok"
    except Exception as e:
        status["services"]["database"] = f"error: {str(e)}"
        status["status"] = "degraded"
        http_status = 503

    try:
        r = redis.from_url(settings.REDIS_URL, socket_connect_timeout=2)
        r.ping()
        status["services"]["redis"] = "ok"
    except Exception as e:
        status["services"]["redis"] = f"error: {str(e)}"
        status["status"] = "degraded"
        http_status = 503

    _worker_health(status)
    if status["status"] != "ok" and http_status == 200:
        http_status = 503

    return JsonResponse(status, status=http_status)


# Two workers since Celery was removed on 2026-08-28, and the reason they are
# two containers is visible right here: these numbers differ by two orders of
# magnitude. One container would have one identity and therefore one threshold,
# so a dead weekly catalog sync would hide for six days behind a healthy poller.
#
#   warframe          300s Steam poll  -> 900s, 3x, one missed cycle is not a page
#   warframe-upkeep   ticks every 60s  -> the JOBS are daily/weekly, but the loop
#                                         beats every tick, so the threshold
#                                         follows the tick and not the jobs.
WORKER_THRESHOLDS = {"warframe": 900, "warframe-upkeep": 600}
LIVENESS_THRESHOLDS = {"warframe": 900, "warframe-upkeep": 600}

# How long a worker may beat with no threshold before its absence is a fault
# rather than a deploy in progress.
UNENROLLED_GRACE = 3600

_SERVER_STARTED = time.time()


def _worker_health(status: dict) -> None:
    """Attach worker heartbeat ages, or say plainly that we cannot tell.

    Redis unreachable renders as `unknown`, never as an error and never as a
    list of stale workers: a Redis outage and a dead worker container are
    different incidents, and collapsing them sends someone to the wrong place.
    """
    client = None
    try:
        client = redis.from_url(settings.REDIS_URL, socket_connect_timeout=2)
    except Exception:  # noqa: BLE001
        status["services"]["workers"] = "unknown (redis unreachable)"
        return

    try:
        now = time.time()
        stale: list[str] = []
        detail: dict[str, dict] = {}

        def _age(worker: str, kind: str):
            raw = client.get(f"{KEY_PREFIX}:{worker}:{kind}")
            if raw is None:
                return None
            value = raw.decode() if isinstance(raw, bytes) else raw
            return round(now - float(value), 1)

        for worker, threshold in WORKER_THRESHOLDS.items():
            boot_age = _age(worker, "boot")
            entry: dict = {"boot": boot_age}
            # The worker's own boot beat, not this process's start: a redeploy
            # restarts Daphne and would otherwise forgive a celery container
            # that has been dead for hours.
            running_for = boot_age if boot_age is not None else now - _SERVER_STARTED

            for kind, limit in (
                ("liveness", LIVENESS_THRESHOLDS.get(worker, 300)),
                ("work", threshold),
            ):
                age = _age(worker, kind)
                entry[kind] = age
                if age is None:
                    if running_for > limit:
                        how = (
                            "has never beat (process never started)"
                            if boot_age is None
                            else f"has never beat since boot {boot_age:.0f}s ago"
                        )
                        stale.append(f"{worker}.{kind} {how}")
                elif age > limit:
                    stale.append(f"{worker}.{kind} {age:.0f}s > {limit}s")
            detail[worker] = entry

        # Discover beats, do not only check declared ones. A worker running and
        # beating with no threshold is unmonitored -- the same hole as one that
        # went quiet, failing at enrollment instead of at runtime.
        unenrolled = _unenrolled(client, now)
        if unenrolled:
            status["services"]["workers_unenrolled"] = ", ".join(
                f"{w} ({state})" for w, state in unenrolled
            )
            if any(state == "unmonitored" for _, state in unenrolled):
                status["status"] = "degraded"

        status["services"]["workers"] = "; ".join(stale) if stale else "ok"
        status["worker_ages"] = detail
        if stale:
            status["status"] = "degraded"
    except Exception as exc:  # noqa: BLE001
        status["services"]["workers"] = f"unknown ({exc})"
    finally:
        try:
            client.close()
        except Exception:  # noqa: BLE001
            pass


def _unenrolled(client, now: float) -> list[tuple[str, str]]:
    """Workers that are beating but that nothing is checking.

    Best-effort: a Redis that answers GET but fails SCAN degrades this check
    alone, never the report built from the GETs.
    """
    try:
        names = set()
        for raw in client.scan_iter(f"{KEY_PREFIX}:*"):
            key = raw.decode() if isinstance(raw, bytes) else raw
            parts = key.split(":")
            if len(parts) >= 3:
                names.add(parts[1])
    except Exception:  # noqa: BLE001 — see docstring
        return []

    out: list[tuple[str, str]] = []
    for name in sorted(names - set(WORKER_THRESHOLDS)):
        try:
            raw = client.get(f"{KEY_PREFIX}:{name}:boot")
        except Exception:  # noqa: BLE001
            raw = None
        if raw is None:
            age = None
        else:
            value = raw.decode() if isinstance(raw, bytes) else raw
            age = now - float(value)
        out.append(
            (
                name,
                "new" if age is not None and age < UNENROLLED_GRACE else "unmonitored",
            )
        )
    return out
