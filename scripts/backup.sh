#!/bin/bash
# (선택) 슬랙 보관함 월별 암호화 백업. 그달에 쓰인 글만 한 파일: slack-YYYY-MM.db.gz.enc (채널·사람·멤버 표는 매번 통째로)
# 저장 위치는 BACKUP_DEST 로 고른다:
#   - 로컬/외장 폴더:  BACKUP_DEST=/Volumes/백업디스크/slack-archive   (rclone 없이 복사)
#   - 클라우드(R2·S3·구글드라이브 등): BACKUP_DEST=내remote이름:버킷/폴더   (rclone config 로 remote 를 먼저 만들어 둠)
# 암호: .env 의 SLACK_BACKUP_KEY (비밀번호 관리자에도 한 부 — 잃으면 복구 불가). openssl aes-256-cbc + pbkdf2
# 사용: backup.sh              → 지난달
#       backup.sh 2026-11      → 그 달
#       backup.sh upto-2026-10 → 처음부터 그 달 끝까지 (첫 묶음)
# 주의: 글을 쓴 달 기준이라, 지난달 글이 나중에 고쳐진 건 다음 파일에 안 들어간다
set -o pipefail
D="$(cd "$(dirname "$0")" && pwd)"
export SLACK_ARCHIVE_HOME="${SLACK_ARCHIVE_HOME:-$HOME/slack-archive}"
ENVF="${SLACK_ARCHIVE_ENV:-$SLACK_ARCHIVE_HOME/.env}"
envget() { [ -f "$ENVF" ] && grep -E "^$1=" "$ENVF" | head -1 | cut -d= -f2- | sed -e 's/^"//' -e 's/"$//'; }
DB="${SLACK_DB:-$(envget SLACK_DB)}"; DB="${DB:-$SLACK_ARCHIVE_HOME/slack.db}"
export SLACK_BACKUP_KEY="${SLACK_BACKUP_KEY:-$(envget SLACK_BACKUP_KEY)}"
BACKUP_DEST="${BACKUP_DEST:-$(envget BACKUP_DEST)}"
PY="${PY:-$(command -v python3)}"
TAG="${1:-$( (date -v-1m +%Y-%m 2>/dev/null) || date -d 'last month' +%Y-%m)}"
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
NAME="slack-$TAG.db.gz.enc"

fail() {
  echo "실패: $1"
  "$PY" "$D/alert.py" "🚨 슬랙 보관함 월별 백업 실패 ($TAG)" "$1" "backup.sh" || true
  exit 1
}
[ -n "$SLACK_BACKUP_KEY" ] || fail "SLACK_BACKUP_KEY 없음"
[ -n "$BACKUP_DEST" ] || fail "BACKUP_DEST 없음"
[ -f "$DB" ] || fail "DB 없음: $DB"

N=$("$PY" "$D/month-extract.py" "$DB" "$TMP/snap.db" "$TAG" 2>&1) || fail "뽑기 실패: $N"
gzip -6 -c "$TMP/snap.db" | openssl enc -aes-256-cbc -pbkdf2 -iter 200000 -salt -pass env:SLACK_BACKUP_KEY -out "$TMP/out.enc" || fail "압축·암호화 실패"
case "$BACKUP_DEST" in
  /*|~*|.*) mkdir -p "${BACKUP_DEST/#\~/$HOME}" && cp "$TMP/out.enc" "${BACKUP_DEST/#\~/$HOME}/$NAME" || fail "복사 실패: $BACKUP_DEST"
            SZ=$(wc -c < "${BACKUP_DEST/#\~/$HOME}/$NAME") ;;
  *) command -v rclone >/dev/null || fail "rclone 이 없어요 (brew install rclone)"
     rclone copyto "$TMP/out.enc" "$BACKUP_DEST/$NAME" --contimeout 30s --timeout 120s -q || fail "올리기 실패: $BACKUP_DEST/$NAME"
     SZ=$(rclone lsf --format s "$BACKUP_DEST/$NAME" 2>/dev/null) ;;
esac
[ -n "$SZ" ] || fail "올린 뒤 확인 실패"
echo "$(date '+%F %T') 백업 ok: $BACKUP_DEST/$NAME · 글 $N · $SZ bytes" | tee -a "${SLACK_ARCHIVE_LOG:-$SLACK_ARCHIVE_HOME/archive.log}"
