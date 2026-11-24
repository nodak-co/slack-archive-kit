"""슬랙 보관함 공용 설정 읽기 — 모든 스크립트가 맨 앞에서 import 한다.
설정은 환경변수 + 홈 폴더의 .env 파일(권한 600). 비밀키는 코드·SKILL 폴더에 두지 않는다.
  SLACK_ARCHIVE_HOME  보관함 폴더 (기본 ~/slack-archive) — DB·JSON·로그·.env 가 여기 모임
  SLACK_ARCHIVE_ENV   .env 위치 (기본 $SLACK_ARCHIVE_HOME/.env)
"""
import os

HOME = os.path.expanduser(os.environ.get('SLACK_ARCHIVE_HOME') or '~/slack-archive')


def _load_env():
    p = os.path.expanduser(os.environ.get('SLACK_ARCHIVE_ENV') or os.path.join(HOME, '.env'))
    if not os.path.isfile(p):
        return
    for line in open(p, encoding='utf-8'):
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        k, v = line.split('=', 1)
        v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in '"\'':
            v = v[1:-1]
        os.environ.setdefault(k.strip(), v)  # 이미 환경에 있으면 그게 우선


_load_env()


def env(name, default=''):
    return os.environ.get(name) or default


def path(name, default_rel):
    return os.path.expanduser(os.environ.get(name) or os.path.join(HOME, default_rel))


DB = path('SLACK_DB', 'slack.db')
DATA_DIR = path('SLACK_DATA_DIR', 'data')      # 보기 화면용 JSON (채널별)
LOG = path('SLACK_ARCHIVE_LOG', 'archive.log')
