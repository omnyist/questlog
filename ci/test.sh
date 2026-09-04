#!/bin/sh
# Runs in a Linux task container on the worker -- the ephemeral pg/redis
# from start-services.yml are published on Saya, not localhost, since
# that's the host actually running them.
set -eu

curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"

export DATABASE_URL="postgresql://questlog:questlog@10.0.20.10:5439/questlog"
export REDIS_URL="redis://10.0.20.10:6399/0"

uv run --group dev pytest -q
