#!/bin/sh
# Runs in a Linux task container on the worker -- the ephemeral pg/redis
# from start-services.yml are published on Saya, not localhost, since
# that's the host actually running them.
set -eu

apt-get update -qq && apt-get install -y -qq curl openssh-client git >/dev/null
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"

export DATABASE_URL="postgresql://questlog:questlog@10.0.20.10:5439/questlog"
export REDIS_URL="redis://10.0.20.10:6399/0"

uv run --group dev pytest -q

echo "=== doctrine-grep ==="
# Full-repo content scan plus HEAD's commit message -- see
# synthcore/ci/test.sh for the fuller rationale (full scan avoids a range
# computation that check_every can silently under-cover; the commit-message
# half only checks HEAD, a real named gap, not a hidden one).
mkdir -p ~/.ssh
echo "$SSH_KEY" > ~/.ssh/id_ed25519
chmod 600 ~/.ssh/id_ed25519
echo "$KNOWN_HOSTS" > ~/.ssh/known_hosts

STD=$(mktemp -d)
GIT_SSH_COMMAND="ssh -i ~/.ssh/id_ed25519 -o UserKnownHostsFile=~/.ssh/known_hosts -o ConnectTimeout=10" \
  git clone --depth 1 -q Avalonstar@10.0.20.10:git/standards.git "$STD"

git log -1 --format=%B > /tmp/commit-msg
bash "$STD/checks/doctrine-grep.sh" "$PWD" /tmp/commit-msg
rm -rf "$STD"
