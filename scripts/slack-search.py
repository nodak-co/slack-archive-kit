#!/usr/bin/env python3
# 슬랙 보관함 검색 — messages_fts(FTS5 trigram)로 찾는다
# 사용: python3 slack-search.py <검색어> [--channel C0..] [--limit 20]
#   세 글자 이상: 색인으로 찾음 · 두 글자 이하: 색인이 못 써서 전체를 훑음(LIKE, 2만 건이라 1초 안쪽)
import os, sqlite3, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import DB  # noqa: E402
args = sys.argv[1:]
if not args:
    sys.exit(__doc__ or '사용: python3 slack-search.py <검색어> [--channel C0..] [--limit 20]')
ch = args[args.index('--channel') + 1] if '--channel' in args else None
limit = int(args[args.index('--limit') + 1]) if '--limit' in args else 20
q = next(a for i, a in enumerate(args) if not a.startswith('--') and (i == 0 or args[i - 1] not in ('--channel', '--limit')))

c = sqlite3.connect(f'file:{DB}?mode=ro', uri=True)
where, p = '', []
if len(q) >= 3:
    sql = 'select m.channel, m.ts, m.thread_ts, m.user, m.text from messages_fts f join messages m on m.rowid = f.rowid where messages_fts match ?'
    p.append('"' + q.replace('"', '""') + '"')
else:
    sql = 'select m.channel, m.ts, m.thread_ts, m.user, m.text from messages m where m.text like ?'
    p.append(f'%{q}%')
if ch:
    sql += ' and m.channel = ?'; p.append(ch)
sql += ' order by cast(m.ts as real) desc limit ?'; p.append(limit)

names = dict(c.execute('select id, name from channels'))
users = dict(c.execute('select id, name from users'))
try: team = c.execute("select v from meta where k='team_id'").fetchone()[0]
except Exception: team = os.environ.get('SLACK_TEAM_ID', '')
rows = c.execute(sql, p).fetchall()
for cid, ts, tts, uid, text in rows:
    when = time.strftime('%Y-%m-%d %H:%M', time.localtime(float(ts)))
    line = ' '.join((text or '').split())
    print(f'[{when}] #{names.get(cid, cid)} {users.get(uid, uid)}: {line[:160]}')
    print(f'  https://app.slack.com/client/{team}/{cid}' + (f'/thread/{cid}-{tts}' if tts else ''))
print(f'— {len(rows)}건 (검색어 「{q}」)', file=sys.stderr)
