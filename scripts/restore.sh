#!/bin/bash
# 월별 백업 되살리기 — backup.sh 짝. BACKUP_DEST 의 slack-*.db.gz.enc 를 전부 받아 한 DB 로 합친다
# 사용: restore.sh [내려놓을 경로]   (기본 $SLACK_ARCHIVE_HOME/slack.restored.db — 정본 자리로 옮기는 건 확인하고 직접)
# 합친 뒤 SLACK_DB=<그 경로> python3 slack-export.py 를 한 번 돌리면 검색 색인을 새로 만들고 최근 글을 슬랙에서 다시 받는다
set -eo pipefail
D="$(cd "$(dirname "$0")" && pwd)"
export SLACK_ARCHIVE_HOME="${SLACK_ARCHIVE_HOME:-$HOME/slack-archive}"
ENVF="${SLACK_ARCHIVE_ENV:-$SLACK_ARCHIVE_HOME/.env}"
envget() { [ -f "$ENVF" ] && grep -E "^$1=" "$ENVF" | head -1 | cut -d= -f2- | sed -e 's/^"//' -e 's/"$//'; }
export SLACK_BACKUP_KEY="${SLACK_BACKUP_KEY:-$(envget SLACK_BACKUP_KEY)}"
BACKUP_DEST="${BACKUP_DEST:-$(envget BACKUP_DEST)}"
[ -n "$SLACK_BACKUP_KEY" ] && [ -n "$BACKUP_DEST" ] || { echo "SLACK_BACKUP_KEY · BACKUP_DEST 가 필요해요"; exit 1; }
OUT="${1:-$SLACK_ARCHIVE_HOME/slack.restored.db}"
[ ! -e "$OUT" ] || { echo "이미 있음: $OUT — 지우거나 다른 경로를 줘"; exit 1; }
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
LOCAL=0; case "$BACKUP_DEST" in /*|~*|.*) LOCAL=1; BD="${BACKUP_DEST/#\~/$HOME}";; esac
if [ $LOCAL = 1 ]; then FILES=$(ls "$BD" | grep -E '^slack-.*\.db\.gz\.enc$' | sort)
else FILES=$(rclone lsf "$BACKUP_DEST/" 2>/dev/null | grep -E '^slack-.*\.db\.gz\.enc$' | sort); fi
[ -n "$FILES" ] || { echo "백업 파일이 없음"; exit 1; }
for f in $FILES; do
  if [ $LOCAL = 1 ]; then cat "$BD/$f"; else rclone cat "$BACKUP_DEST/$f" 2>/dev/null; fi \
    | openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -pass env:SLACK_BACKUP_KEY | gunzip > "$TMP/${f%.gz.enc}"
  echo "받음: $f"
done
python3 "$D/month-merge.py" "$OUT" "$TMP"/*.db
chmod 600 "$OUT"; echo "되살림 → $OUT"
