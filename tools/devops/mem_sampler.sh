#!/usr/bin/env bash
# Sample RSS/VSZ of a PID every second to a CSV.
# Usage: tools/devops/mem_sampler.sh <pid> <out.csv>
set -euo pipefail
PID="${1:?pid required}"
OUT="${2:?output csv required}"
echo "ts_iso,epoch,rss_kb,vsz_kb" > "$OUT"
while kill -0 "$PID" 2>/dev/null; do
  read -r RSS VSZ < <(ps -o rss=,vsz= -p "$PID" 2>/dev/null || echo "")
  if [[ -z "${RSS:-}" ]]; then break; fi
  printf "%s,%d,%s,%s\n" "$(date -u +%FT%TZ)" "$(date +%s)" "$RSS" "$VSZ" >> "$OUT"
  sleep 1
done
echo "[mem_sampler] PID $PID exited; final samples in $OUT" >&2
