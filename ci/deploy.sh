#!/bin/bash
# Runs ON Saya, in the persistent checkout at ~/ci/deploys/questlog.
set -euo pipefail

docker compose -f docker-compose.prod.yml up --build -d --remove-orphans
