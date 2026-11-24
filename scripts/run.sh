#!/bin/bash
# 슬랙 보관함 이어 받기 1회 — OpenClaw automations(--command) 나 cron 이 매시 부른다.
# 실패하면 ALERT_SLACK_CHANNEL 이 있을 때만 경보 한 줄.
# 시험: SLACK_DB=/없는/곳/x.db bash run.sh  (토큰이 없으면 실패 → 로그에 남는다)
D="$(cd "$(dirname "$0")" && pwd)"
export SLACK_ARCHIVE_HOME="${SLACK_ARCHIVE_HOME:-$HOME/slack-archive}"
mkdir -p "$SLACK_ARCHIVE_HOME"
LOG="${SLACK_ARCHIVE_LOG:-$SLACK_ARCHIVE_HOME/archive.log}"
LOCK="$SLACK_ARCHIVE_HOME/.archive.lock"
PY="${PY:-$(command -v python3)}"

if ! mkdir "$LOCK" 2>/dev/null; then
  echo "$(date '+%F %T') 앞 실행이 아직 도는 중 — 건너뜀" | tee -a "$LOG"; exit 0
fi
trap 'rmdir "$LOCK"' EXIT

OUT=$("$PY" "$D/slack-export.py" "$@" 2>&1); RC=$?
{ echo "=== $(date '+%F %T') rc=$RC"; echo "$OUT" | tail -5; } >> "$LOG"
echo "$OUT" | tail -3
if [ $RC -ne 0 ]; then
  "$PY" "$D/alert.py" "🚨 슬랙 보관함 이어 받기 실패 (rc=$RC)" "$(echo "$OUT" | tail -3)" "run.sh" || true
  exit $RC
fi
