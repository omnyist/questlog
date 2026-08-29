"""Celery was removed on 2026-08-28.

This module used to import the Celery app so `@shared_task` autodiscovery
worked at Django startup. The three Warframe jobs are plain functions now,
driven by two looping management-command containers, so there is nothing to
wire in here.

Left as a deliberate note rather than an empty file: an empty `config/__init__`
invites someone to re-add a broker without knowing one was removed on purpose.
The reasoning is in `apps/profiles/warframe/tasks.py` and arbitration q0002.
"""

from __future__ import annotations
