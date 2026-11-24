---
name: slack-archive-kit
description: 슬랙 무료 플랜 아카이빙, 슬랙 보관함 만들어줘, 3개월 지난 슬랙 대화 보관, 슬랙 대화 SQLite로 백업, 슬랙 로그인 보기 화면 — 내 슬랙 대화를 내 컴퓨터 SQLite에 이어 받아 쌓고, 슬랙 모양 보기 화면(Sign in with Slack, 멤버 채널만)을 Cloudflare Tunnel로 연다.
---

# 슬랙 보관함 키트

슬랙 대화를 **내 컴퓨터의 SQLite 한 파일**에 쌓고, 슬랙처럼 생긴 보기 화면(채널 | 글 | 스레드, 전문 검색)을 띄운다. 파이썬 표준 라이브러리만 쓴다(설치할 패키지 없음).

- 데이터(DB)는 항상 내 컴퓨터에만 있다. 인터넷에 열리는 건 **보기 화면 서버 하나**뿐이다.
- 보는 사람은 슬랙으로 로그인하고, **자기가 슬랙에서 멤버인 채널만** 본다. 손으로 관리하는 명단이 없다.

> ⚠️ **90일 제약은 확인 필요.** 슬랙 무료 플랜은 오래된 대화(대략 90일 전 것)를 가리거나 접근을 막는다고 알려져 있지만, 정확한 기준·API로 받을 수 있는 범위는 이 키트에서 확인하지 않았다. 슬랙 공식 안내(Free plan limits)로 확인할 것. 확인과 상관없이 **일찍 시작할수록 안전하다** — 한번 접근이 막힌 글은 못 받을 수 있다. 첫 이어 받기를 제일 먼저 돌려서 지금 받을 수 있는 만큼부터 확보한다.

## 만들어지는 것

```
~/slack-archive/            ← 보관함 폴더 (SLACK_ARCHIVE_HOME, 바꿀 수 있음)
  .env                      ← 설정·비밀키 (권한 600)
  slack.db                  ← 정본 SQLite (글·스레드·이모지 반응 raw JSON + 전문 검색 색인 + 채널 멤버)
  data/                     ← 보기 화면용 JSON (이어 받을 때마다 다시 만들어짐)
  archive.log · viewer.log
```
스킬 폴더(`skills/slack-archive-kit/`)는 코드만 있고 읽기 전용으로 쓴다. 파일: `scripts/archive.py`(봇용 읽기 CLI) · `scripts/slack-export.py`(받기) · `run.sh`(1회 실행+경보) · `slack-search.py`(검색) · `viewer/`(보기 화면) · `backup.sh`·`restore.sh`·`month-*.py`(선택 백업) · `templates/`(launchd·cloudflared 틀) · `.env.example`.

## 먼저 정할 것 (사용자에게 물어볼 것)

1. 슬랙 워크스페이스에 **앱을 만들 권한**이 있나? (관리자 승인이 필요할 수 있다)
2. 보기 화면 로그인 방식(`AUTH_MODE`): **slack**(기본, 슬랙 계정) / **google**(구글 회사계정 Workspace, 도메인 제한) / **tailnet**(테일넷 안에서만)? slack·google은 공개 주소(Cloudflare Tunnel)로 연다.
3. 공개 모드면: Cloudflare에 올려 둔 **내 도메인**이 있나? (없으면 도메인 하나가 필요 — 이 키트가 대신 사 주지 않는다. 도메인이 없으면 테일넷 모드를 권한다.)
4. (선택) 월별 암호화 백업을 어디에 둘까? 외장 디스크 폴더 / R2·S3·구글드라이브(rclone)

## 1단계 — 슬랙 앱 만들기

https://api.slack.com/apps → Create New App → From a manifest → 워크스페이스 선택 → 아래 붙여 넣기(`내도메인` 바꿈. 테일넷 모드면 `oauth_config.redirect_urls`와 `user` 블록은 빼도 된다).

```yaml
display_information:
  name: 슬랙 보관함
oauth_config:
  redirect_urls:
    - https://archive.내도메인.com/auth/callback
  scopes:
    user:                  # Sign in with Slack 용 (slack·google 모드)
      - openid
      - profile
      - email
    bot:
      - users:read.email   # 선택: 구글 로그인(AUTH_MODE=google)일 때만 — 이메일로 슬랙 사람을 찾음
      - channels:history
      - channels:read
      - groups:history
      - groups:read
      - users:read
      - emoji:read
      - chat:write         # 선택: 경보 채널에 알림 보낼 때만
settings:
  org_deploy_enabled: false
  socket_mode_enabled: false
  token_rotation_enabled: false
```

각 권한을 **코드가 어디에 쓰는지**:

| 권한 | 쓰는 곳 |
|---|---|
| `channels:read` · `groups:read` | `conversations.list`(공개·비공개 채널 목록) · `conversations.members`(채널 멤버 = 보기 화면 접근 기준) |
| `channels:history` · `groups:history` | `conversations.history` · `conversations.replies`(글·스레드 답글, 이모지 반응이 글 안에 같이 옴) |
| `users:read` | `users.list`(이름·사진) |
| `emoji:read` | `emoji.list`(우리 워크스페이스 커스텀 이모지) |
| `chat:write` (선택) | 이어 받기 실패 경보 `alert.py` |
| 사용자 `openid` `profile` `email` | Sign in with Slack: 코드가 `openid.connect.token`·`openid.connect.userInfo`로 슬랙 user id·team id를 받는다 (이메일은 코드가 쓰지 않음 — 빼도 로그인은 됨) |

- `users:read.email`은 **google 모드에서만** 필요하다(슬랙 users 표의 이메일로 슬랙 user id 매칭). slack·tailnet 모드와 `reactions:read` 등은 코드가 쓰지 않으니 달지 않는다. 권한을 추가하면 앱 **재설치** 후 이어 받기를 한 번 돌려야 users 표에 이메일이 채워진다.
- 받는 범위는 **봇이 들어가 있는 공개·비공개 채널**뿐이다. DM·그룹DM은 받지 않는다.
- 만든 뒤: **Install to Workspace**(승인) → **Bot User OAuth Token(`xoxb-…`)** 복사. **Basic Information**에서 Client ID·Client Secret 복사. 공개 모드의 리다이렉트 URL은 **OAuth & Permissions → Redirect URLs**에 정확히 `https://archive.내도메인.com/auth/callback`(끝 슬래시 없음, https)로 들어가 있어야 한다.
- **보관할 채널마다 봇을 초대한다**: 채널에서 `/invite @슬랙 보관함`(비공개 채널도 같다). 봇이 못 들어간 채널은 안 받아진다.
- Team ID(`T…`): 브라우저에서 슬랙을 열 때 주소 `app.slack.com/client/T…/…` 의 `T…`.

확인: 앱 화면에 Installed 표시, 토큰이 `xoxb-`로 시작.

## 2단계 — 보관함 폴더와 설정 만들기

```bash
KIT=~/.openclaw/skills/slack-archive-kit      # 이 스킬 폴더 (설치 위치에 맞게)
mkdir -p ~/slack-archive && cp $KIT/.env.example ~/slack-archive/.env && chmod 600 ~/slack-archive/.env
python3 -c "import secrets;print(secrets.token_urlsafe(48))"   # → SESSION_SECRET 에 넣을 값
```
`~/slack-archive/.env`를 열어 `SLACK_BOT_TOKEN`, `SLACK_TEAM_ID`, (slack·google 모드) `PUBLIC_URL`·`SLACK_CLIENT_ID`·`SLACK_CLIENT_SECRET`·`SESSION_SECRET`을 채운다. **비밀키는 이 .env 밖(스킬 폴더, 메모, 채팅)에 쓰지 않는다.**

확인(슬랙을 부르지 않는 점검): `python3 $KIT/scripts/slack-export.py --dry-run` → `드라이런 ok: DB … · 토큰 있음` 이 나오면 설정을 읽은 것.

## 3단계 — 첫 이어 받기

```bash
python3 $KIT/scripts/slack-export.py        # 처음엔 글이 많으면 몇 분 걸린다
```
채널마다 `#이름: 스레드 새로 받음 N` 이 찍히고 `받기 끝: 채널 N개 · 새 글 N · API N번`, `사이트 JSON: …`이 나오면 성공.
- `invalid_auth` → 토큰 잘못/미설치. `missing_scope` → 위 권한 누락(앱에서 권한 추가 후 **재설치**해야 새 토큰/권한 적용). 채널 0개 → 봇을 채널에 초대 안 함.
- 슬랙이 429를 주면 코드가 알아서 기다렸다 이어간다.
- 같은 명령을 다시 돌리면 **이어 받기**(바뀐 것만 새로 받음). 검색은 아래 「봇이 보관함 읽기」의 `archive.py`(옛 `slack-search.py`도 남아 있음).
- 선택: 한 채널 글을 다른 채널에도 같이 보이게(예: 잘못 올린 채널 정리) → `slack-export.py --add-moves <탭구분.tsv> <원래채널ID> <보일채널ID>` (tsv: `글ts<탭>메모`). 쓸 일 없으면 건너뛴다.

## 4단계 — 보기 화면 (모드 고르기)

### A. 공개 배포 (기본): Cloudflare Tunnel + Sign in with Slack

흐름: 접속 → `/login` → 슬랙 로그인 → `/auth/callback`에서 `openid.connect.token`으로 코드 교환 → `openid.connect.userInfo`로 슬랙 user id·team id → **team id가 `SLACK_TEAM_ID`와 다르면 거부** → 서명된 세션 쿠키(HttpOnly, `PUBLIC_URL`이 https면 Secure, 7일) → 화면은 DB의 `channel_members`에 그 사람이 있는 채널만 내준다(글·검색 모두). 로그인 안 했거나 다른 워크스페이스면 0채널/거부.

1. 서버를 먼저 로컬에서 시험: `cd $KIT/scripts/viewer && python3 server.py` → `슬랙 보관함 보기 화면: http://127.0.0.1:43140`. 필요한 설정이 빠지면 서버가 시작을 거부하고 무엇이 없는지 알려준다.
2. 터널 만들기(한 번만, 터미널 — 사람이 브라우저로 Cloudflare 로그인해야 함): `brew install cloudflared` → `cloudflared tunnel login` → `cloudflared tunnel create slack-archive` → `cloudflared tunnel route dns slack-archive archive.내도메인.com` → `templates/cloudflared-config.example.yml`을 `~/.cloudflared/config.yml`로 복사해 터널 ID·도메인 채움 → 시험 `cloudflared tunnel run`.
3. **공개 주소를 열기 전에 사용자에게 확인받는다**(밖으로 열리는 일이다): "데이터는 이 컴퓨터에 있고, 주소는 슬랙 로그인한 우리 워크스페이스 멤버만 글을 볼 수 있어요. 열까요?"
4. 확인:
   - 로그인 없이 `curl -s https://archive.내도메인.com/api/slack` → `{"error": "로그인이 필요해요"}` (401)
   - 브라우저로 주소 접속 → 로그인 안내 → Sign in with Slack → 내가 멤버인 채널만 왼쪽에 보임
   - 비멤버 채널 요청은 403, 다른 워크스페이스 계정은 "이 워크스페이스 멤버만" 거부 화면.
5. 로그아웃: `/logout`. 멤버가 슬랙 채널에서 빠지면 **다음 이어 받기(멤버 갱신) 뒤**부터 그 채널이 안 보인다 — 세션 쿠키가 아니라 DB 멤버 표가 기준.

### A-2. 구글 회사계정 로그인 (`AUTH_MODE=google`)

슬랙 계정 대신 **Google Workspace 회사 구글 계정**으로 로그인한다. 슬랙 앱의 Redirect URL/user scope는 필요 없다(봇 권한 `users:read.email`만 추가).
1. https://console.cloud.google.com → 프로젝트 → API 및 서비스 → OAuth 동의 화면(사용자 유형 **내부**를 권장: 회사 도메인 사용자만) → 사용자 인증 정보 → OAuth 클라이언트 ID(웹 애플리케이션) → **승인된 리디렉션 URI**에 `https://archive.내도메인.com/auth/callback`.
2. `.env`: `AUTH_MODE=google`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_HD=회사도메인.com`, `PUBLIC_URL`, `SESSION_SECRET`, `SLACK_TEAM_ID`.
3. 흐름: `/login` → 구글(`hd` 힌트 포함) → 서버가 코드를 id_token으로 교환 → **id_token의 aud·iss·exp·nonce·`email_verified`·`hd`가 모두 맞고 이메일이 `@GOOGLE_HD`일 때만** 통과(`hd` 파라미터는 힌트일 뿐이라 서버가 다시 검사) → 이메일을 슬랙 `users` 표의 email과 대조해 슬랙 user id 매칭 → 그 사람이 멤버인 채널만. **매칭 안 되면(슬랙 이메일이 다르거나 둘 이상) 로그인은 되지만 0채널**, 다른 도메인은 거부.
4. 확인: `/login` 주소가 `accounts.google.com`으로 가고 `hd=` 가 붙는다 / 다른 도메인 구글 계정은 "회사 구글 계정만" 거부 / 슬랙에 같은 이메일이 없는 직원은 "볼 수 있는 채널이 없어요".

### B. 테일넷 (선택, `AUTH_MODE=tailnet`)

`.env`에 `AUTH_MODE=tailnet`(옛 이름 `tailscale`도 인식), `SLACK_VIEWER_ACCESS=~/slack-archive/viewer-access.json`. 이 파일은 손으로 관리: `{"사람@메일": "U슬랙ID"}`. 서버는 127.0.0.1에만 붙고, `tailscale serve --https=43141 http://127.0.0.1:43140`(테일넷 안에서만, Funnel은 켜지 않음)로 내보낸다. `Tailscale-User-Login` 헤더 → 매핑 → 그 사람이 멤버인 채널만. 매핑이 없는 로그인은 0채널.

### 개발·시험용 (사용자에게 권하지 않음)
`DEV_USER=U슬랙ID python3 server.py` → 로그인 없이 그 사람 시점으로 본다. 기본 꺼짐, `PUBLIC_URL`이 있으면 서버가 켜기를 거부한다. 공개 .env에 넣지 않는다.

## 5단계 — 자동화

**이어 받기 주기는 내가 고른다.** 기본 예시는 **매달 1회**: 무료 플랜이 오래된 대화를 가리기 전(대략 90일 — 확인 필요)에 한 달에 한 번이면 다 들어온다. 단 한 번 돌릴 때 빠뜨리면 안 되니 **달 초(1일)**에, 그리고 맨 처음엔 바로 한 번 돌려 둔다. 글을 더 빨리 찾고 싶으면 더 자주.
```bash
# 기본: 매달 1일 새벽 3시 17분 (OpenClaw automations, 셸 명령)
openclaw automations add --name slack-archive-monthly --cron "17 3 1 * *" \
  --command "bash $KIT/scripts/run.sh"
# 더 자주: 매일 새벽 → "17 3 * * *" · 매시 17분 → "17 * * * *" · 평일 업무시간 2시간마다 → "17 9-19/2 * * 1-5"
```
(옵션 이름은 환경에 따라 다를 수 있다 → `openclaw automations add --help`. 시스템 cron이면 `17 3 1 * * bash $KIT/scripts/run.sh`.) 자주 돌릴수록 보기 화면 데이터가 최신이고 채널 멤버 변화도 빨리 반영된다(접근 권한은 이어 받을 때 갱신되는 멤버 표 기준). 지난 글은 매번 다시 훑되 바뀐 스레드만 새로 받아서 부담은 작다. `run.sh`는 앞 실행이 안 끝났으면 건너뛰고, 로그는 `~/slack-archive/archive.log`, 실패하면 `ALERT_SLACK_CHANNEL`이 있을 때만 경보. 확인: 실행 뒤 `tail ~/slack-archive/archive.log`에 `rc=0`.

**맥에서 보기 화면 서버 자동 시작(launchd)**:
```bash
sed -e "s#__KIT__#$KIT#g" -e "s#__HOME__#$HOME#g" $KIT/templates/launchd-viewer.plist > ~/Library/LaunchAgents/local.slack-archive-viewer.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/local.slack-archive-viewer.plist
curl -s http://127.0.0.1:43140/healthz        # → ok
```
터널도 같게(`templates/launchd-cloudflared.plist`, `which cloudflared`로 경로 확인). 끄기: `launchctl bootout gui/$(id -u)/local.slack-archive-viewer`. 맥이 잠자기 하면 터널·서버도 멈추니 전원 설정(잠자기 방지)을 같이 안내한다.

## 봇이 보관함 읽기 — `archive.py` (핵심 사용법)

보관함의 목적은 **필요할 때 슬랙 대화를 찾아서 보는 것**이다. 봇은 슬랙 API를 부르지 않고 이 CLI로 DB를 읽기 전용으로 읽는다. 모든 명령에 `--json`이 있고, 각 결과에 보기 화면 링크(`url`)가 붙는다. 링크 기준 주소는 `.env`의 `ARCHIVE_BASE_URL`(없으면 `PUBLIC_URL`; 둘 다 없으면 링크 생략).
```bash
CLI="python3 $KIT/scripts/archive.py"
$CLI channels                                           # 채널 목록(이름·ID)
$CLI search 견적서 --channel 행정업무 --since 2026-09-01 --until 2026-11-30 --limit 10 [--json]
$CLI thread 행정업무 1795402500.852659 [--json]         # 스레드 전체 글(ts는 첫 글이든 답글이든 됨)
$CLI recent 행정업무 --limit 20 [--since 2026-11-01] [--json]   # 채널 최근 N글(답글 제외)
```
- 채널은 이름 또는 ID. 검색은 세 글자 이상이면 색인, 두 글자 이하는 전체 훑기. 기간은 한국 시간 날짜, `--until`은 그날 끝까지 포함.
- JSON 결과 필드: `channel_id, channel, ts, thread_ts, time, user, text, url`.
- 사용자가 "그 얘기 어디서 했지?"라고 물으면: `search`로 찾고 → 필요하면 `thread`로 맥락을 읽고 → 요약과 함께 `url`을 준다. 링크를 열면 그 사람의 슬랙 멤버 권한으로 다시 검사된다(이 CLI는 주인 컴퓨터의 DB 전체를 보므로, 멤버가 아닌 사람에게 **본문을 옮겨 적어 주지 않는다** — 링크만 준다).
- 확인: `$CLI channels`에 채널이 나오고, `search`가 결과와 `url`을 돌려준다.

## 딥링크 (스레드·글마다 고유 주소)

- 스레드: `{주소}/c/<채널ID>/t/<스레드ts>` (답글 하나를 짚으려면 `?m=<답글ts>`) · 글 하나: `{주소}/c/<채널ID>/m/<ts>` (스레드 답글이면 부모 스레드를 펼치고 그 글로 스크롤).
- 열면 그 채널·스레드가 바로 펼쳐지고 가리킨 글이 노랗게 강조되며 그 위치로 스크롤된다. 오래된 글이면 그 글이 보이게 이전 글을 더 불러온다.
- 화면의 **링크 복사**: 스레드 위쪽 버튼(스레드 주소), 글에 마우스를 올리면 나오는 🔗(글 주소).
- 권한은 딥링크에도 똑같다: 로그인 전이면 로그인 화면(로그인 뒤 그 주소로 되돌아옴 — 우리 딥링크 모양만 허용), 채널 멤버가 아니면 403 안내. 데이터 API(`/api/slack`)도 같은 검사를 한다.

## 6단계 (선택) — 월별 암호화 백업

SQLite 한 파일이라 컴퓨터가 고장 나면 같이 사라진다. 슬랙에서 이미 가려진 오래된 글은 다시 못 받을 수 있으므로 **백업을 권한다**(확인 필요 항목과 같은 이유).
1. `.env`에 `SLACK_BACKUP_KEY`(긴 암호 — **비밀번호 관리자에 따로 한 부**, 잃으면 복구 불가)와 `BACKUP_DEST` 설정.
   - 외장 디스크/로컬: `BACKUP_DEST=/Volumes/디스크/slack-archive`
   - 클라우드: `rclone config`로 remote를 먼저 만들고(R2·S3·구글드라이브 등) `BACKUP_DEST=내remote:버킷/slack` (`brew install rclone`)
2. 첫 묶음: `bash $KIT/scripts/backup.sh upto-YYYY-MM`(지난달까지) → 이후 매달 1일 `bash $KIT/scripts/backup.sh`(지난달분)을 automations로.
3. 확인: `slack-….db.gz.enc` 파일이 생겼는지, 한 번은 **복구 시험**: `bash $KIT/scripts/restore.sh /tmp/restored.db` → `무결성: ok`. 복구 DB를 정본 자리로 옮기고 `slack-export.py`를 한 번 돌리면 색인을 다시 만든다.

## 문제 해결

- 화면이 비었다: 로그인한 사람이 채널 멤버로 DB에 없다(`slack-export.py --members`로 멤버 새로 받기), 또는 봇이 채널에 없다.
- 로그인 뒤 `redirect_uri` 오류: 앱의 Redirect URLs와 `PUBLIC_URL/auth/callback`이 글자 하나까지 같아야 한다.
- 로그인 뒤 "이 워크스페이스 멤버만": `SLACK_TEAM_ID`가 틀렸거나 다른 워크스페이스 계정으로 로그인함.
- 다른 sqlite 도구가 DB를 못 연다(샌드박스 폴더): `/tmp`에 복사해서 연다.
- 전문 검색은 세 글자 이상이 색인 검색, 두 글자 이하는 전체 훑기. FTS5 trigram은 SQLite 3.34 이상 필요(`python3 -c "import sqlite3;print(sqlite3.sqlite_version)"`).

## 이 키트에서 확인한 것 / 못 한 것

확인함(2026-11-24, 실제 운영 중인 보관함 DB 사본으로): CLI search/thread/channel/channels(+`--json`, 링크 생성), 딥링크 열기(스레드·`?m=` 답글 강조·캡처 확인)·비멤버 채널 딥링크 403·로그인 전 딥링크에 되돌아올 주소 쿠키, 구글 모드 로그인 주소(`hd` 포함)·필수 설정 누락 시 시작 거부·이메일→슬랙 ID 매칭(임시 사본에 이메일을 넣어 시험, 없는 메일은 매칭 없음), 보기 화면(채널·스레드·반응·커스텀 이모지·검색), 멤버 채널 필터(12/18/0채널), 서명된 세션·위조 쿠키 거부·비멤버 채널 403, DEV_USER 공개 배포 거부, 월별 백업→복구(로컬 경로), 이어 받기 `--dry-run`·`--build-only`.
**못 함**: 슬랙·구글 OAuth 실제 왕복(로그인 → 코드 교환 → userInfo/id_token 검사. 구글 쪽 id_token 검사 분기는 코드 리뷰만), Cloudflare Tunnel 실제 개방, 실제 슬랙 API 이어 받기, rclone 원격 백업. 슬랙 OIDC 요청 형식은 공식 문서 기준으로 짰다 — 첫 실전 로그인에서 막히면 서버 로그(`viewer.log`의 `로그인 실패:`)를 본다.
