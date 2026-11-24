# slack-archive-kit

무료 슬랙에서 90일이 지나 가려지는 대화를 내 컴퓨터 SQLite에 계속 쌓아 두고, 슬랙처럼 생긴 화면에서 찾아보는 OpenClaw 스킬이에요.

- 슬랙 로그인(Sign in with Slack)으로 들어오면, 그 사람이 들어가 있는 채널만 보여요 (구글 회사계정·테일넷 로그인도 고를 수 있어요)
- 스레드마다 고유 주소가 있고, "링크 복사" 버튼이 있어요
- 봇은 `scripts/archive.py`로 보관함을 검색하고 스레드를 읽을 수 있어요
- 대화 원본은 내 컴퓨터에만 두고, 보기 화면만 Cloudflare Tunnel로 열어요

설치: 봇에게 `openclaw skills install git:nodak-co/slack-archive-kit` 해 달라고 하거나, 이 폴더를 스킬 폴더에 넣어 주세요. 자세한 절차는 [SKILL.md](SKILL.md)에 있어요.
