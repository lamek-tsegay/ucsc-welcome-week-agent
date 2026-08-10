#!/usr/bin/env bash
# Start all three agents on localhost endpoints, drive them with a real client
# uAgent over HTTP, then tear everything down.
#
# No Agentverse account, no API keys, no mailbox. Exits non-zero if any agent
# fails to answer.
set -uo pipefail

cd "$(dirname "$0")/.."

PY="${PY:-.venv/bin/python}"
if [ ! -x "$PY" ]; then
  PY="python3"
fi

LOG_DIR="$(mktemp -d)"
PIDS=()

cleanup() {
  for pid in "${PIDS[@]:-}"; do
    kill "$pid" 2>/dev/null
  done
  wait 2>/dev/null
}
trap cleanup EXIT INT TERM

echo "Starting agents in local-endpoint mode (logs: $LOG_DIR)"

for spec in "navigation:8021" "events:8022" "clubs:8023"; do
  name="${spec%%:*}"
  port="${spec##*:}"
  UCSC_LOCAL_ENDPOINT=1 "$PY" -m "agents.${name}.agent" \
    > "$LOG_DIR/${name}.log" 2>&1 &
  PIDS+=($!)
done

# Wait for all three HTTP servers to be listening before driving them.
for port in 8021 8022 8023; do
  for _ in $(seq 1 40); do
    if nc -z 127.0.0.1 "$port" 2>/dev/null; then
      break
    fi
    sleep 0.5
  done
  if ! nc -z 127.0.0.1 "$port" 2>/dev/null; then
    echo "ERROR: nothing listening on port $port"
    echo "--- logs ---"
    tail -n 30 "$LOG_DIR"/*.log
    exit 1
  fi
done

echo "All three listening. Running client."
echo

UCSC_LOCAL_ENDPOINT=1 "$PY" -m scripts.chat_client
STATUS=$?

if [ $STATUS -ne 0 ]; then
  echo "--- agent logs ---"
  for name in navigation events clubs; do
    echo "=== $name ==="
    grep -iE "error|traceback|exception|warning" "$LOG_DIR/${name}.log" | tail -n 15
  done
fi

exit $STATUS
