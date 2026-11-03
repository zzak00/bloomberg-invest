#!/usr/bin/env bash
# Read-only: is the local stack worth driving? Exits non-zero on the first problem.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
base="${1:-http://localhost:8080}"

command -v docker >/dev/null || { echo "FAIL docker not on PATH (OrbStack: ~/.orbstack/bin)"; exit 1; }
[ -f .env ] || { echo "FAIL .env missing: cp .env.example .env and set NEO4J_PASSWORD"; exit 1; }

for service in neo4j api web; do
  status=$(docker compose ps --format '{{.Service}}|{{.Status}}' | awk -F'|' -v s="$service" '$1 == s {print $2}')
  case "$status" in
    *unhealthy*) echo "FAIL $service: $status"; exit 1 ;;
    Up*) echo "OK   $service: $status" ;;
    *) echo "FAIL $service not running (docker compose up -d --build --wait)"; exit 1 ;;
  esac
done

health=$(curl -fsS "$base/api/health") || { echo "FAIL $base/api/health unreachable"; exit 1; }
echo "OK   api health: $health"

count=$(curl -fsS "$base/api/documents" | python3 -c "import json,sys; print(len(json.load(sys.stdin)))")
if [ "$count" -lt 1 ]; then
  echo "FAIL no filings ingested: see SKILL.md, Launch step 3"
  exit 1
fi
echo "OK   $count filing(s) ingested"
