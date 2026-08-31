"""The worker roster, checked against the file that actually runs them.

`_worker_health` learns its roster from WORKER_THRESHOLDS, and beat discovery can
only see a worker that has beaten at least once. Neither can see a service
that compose runs and that has never beaten at all — synthfunc, 2026-08-31,
ran six workers while /health/ spoke for four and reported `workers: ok`
truthfully the whole time.

Nothing inside the process can close that: the runtime does not know what
compose says should be running. So the roster check lives in CI, where the
compose file is readable. This family has no gap today; these tests are what
keep it that way when the next worker is added.

See conventions/health.md, "discovery cannot see a worker that never beats".

pyyaml is deliberately not a dependency. This reads exactly one shape —
two-space-indented keys inside `services:` — and fails loudly if the file
stops matching it, which is the right failure for a parser this small.
"""

from __future__ import annotations

import re
from pathlib import Path

from config.health import WORKER_THRESHOLDS

COMPOSE = Path(__file__).resolve().parent.parent / "docker-compose.prod.yml"

# Compose services that are deliberately not beat-enrolled workers.
NOT_WORKERS = {
    # Answers /health/; the edge monitor polling it is its check.
    "server",
}

# Beat names produced by something that is not a compose service here.
EXTERNAL_WRITERS: set[str] = set()

# service name -> the worker name its beats use, where the two differ.
SERVICE_TO_WORKER: dict[str, str] = {}


def _compose_services() -> set[str]:
    services: set[str] = set()
    in_services = False
    for line in COMPOSE.read_text().splitlines():
        if re.match(r"^services:\s*$", line):
            in_services = True
            continue
        if in_services and line and not line[0].isspace():
            break
        m = re.match(r"^  ([a-z][a-z0-9_-]*):\s*$", line)
        if in_services and m:
            services.add(m.group(1))
    return services


def test_compose_parse_is_not_silently_empty():
    """An empty roster would make both tests below vacuously pass, which is
    the exact failure mode they exist to prevent."""
    services = _compose_services()
    assert len(services) >= 3, f"compose parse looks broken: {sorted(services)}"
    assert 'server' in services


def test_every_long_lived_service_is_a_declared_worker():
    """A container compose runs that the health endpoint has never heard of is
    watched by nobody, and reads as healthy forever."""
    workers = {
        SERVICE_TO_WORKER.get(s, s) for s in _compose_services() - NOT_WORKERS
    }
    undeclared = workers - set(WORKER_THRESHOLDS)
    assert not undeclared, (
        f"compose runs {sorted(undeclared)} with no WORKER_THRESHOLDS entry — "
        "declare a threshold and emit beats, or add it to NOT_WORKERS with a reason"
    )


def test_every_declared_worker_still_has_a_writer():
    """The other direction: a declaration that outlives its service holds the
    endpoint at degraded forever, about a worker deliberately retired —
    questlog's own Celery did exactly this on 2026-08-28."""
    workers = {
        SERVICE_TO_WORKER.get(s, s) for s in _compose_services() - NOT_WORKERS
    }
    orphaned = set(WORKER_THRESHOLDS) - workers - EXTERNAL_WRITERS
    assert not orphaned, (
        f"WORKER_THRESHOLDS declares {sorted(orphaned)} but no compose service "
        "or known external writer produces those beats — delete the declaration "
        "and the worker's hb:* keys together"
    )
