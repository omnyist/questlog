#!/bin/bash
# Runs ON Saya, right after deploy.sh. Mandatory read-back per deploy.md --
# the shared compose-inspect block (same as five of the other six modules),
# then the pg-ready wait + collectstatic that's specific to questlog.
set -uo pipefail

sleep 30

ids=$(docker compose -f docker-compose.prod.yml ps -aq)
if [ -z "$ids" ]; then
  echo "No containers found for this compose project."
  exit 1
fi

failed=""
for cid in $ids; do
  info=$(docker inspect --format '{{.Name}} {{.State.Status}} {{.State.ExitCode}}' "$cid")
  name=$(echo "$info" | cut -d' ' -f1 | sed 's|^/||')
  state=$(echo "$info" | cut -d' ' -f2)
  code=$(echo "$info" | cut -d' ' -f3)
  case "$state" in
    running|created)
      echo "ok: $name ($state)"
      ;;
    exited)
      if [ "$code" = "0" ]; then
        echo "ok: $name (exited 0, one-shot)"
      else
        echo "FAILED: $name exited $code"
        failed="$failed $name"
      fi
      ;;
    *)
      echo "FAILED: $name is $state"
      failed="$failed $name"
      ;;
  esac
done

if [ -n "$failed" ]; then
  for name in $failed; do
    echo "----- $name: last 30 log lines -----"
    docker logs --tail 30 "$name" 2>&1 || true
  done
  echo "Deploy verification failed:$failed"
  exit 1
fi

timeout 60 sh -c 'until docker exec synthcore-postgres pg_isready -U questlog -d questlog; do sleep 1; done'
sleep 5

docker compose -f docker-compose.prod.yml exec -T server uv run python manage.py collectstatic --noinput
docker image prune -f
