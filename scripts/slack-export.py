#!/usr/bin/env python3
# 슬랙 보관함 이어 받기 — 봇이 들어가 있는 채널 전부를 SQLite 에 원본(raw JSON) 그대로 쌓고, 보기 화면용 JSON 을 만든다
#   DB: $SLACK_ARCHIVE_HOME/slack.db (env SLACK_DB 로 바꿈). messages_fts = 전문 검색 색인(FTS5 trigram, 트리거로 자동 갱신)
#   두 번째부터는 이어 받기: 채널 글 목록은 매번 훑고, 스레드 답글은 latest_reply 가 바뀐 것만 다시 받는다
# 사용: python3 slack-export.py [--only C0..,C0..] [--build-only] [--members] [--dry-run]
#       python3 slack-export.py --add-moves <ts탭요약.tsv> <원래채널ID> <보일채널ID>   (선택: 한 채널 글을 다른 채널에도 같이 보이게)
#   --dry-run : 슬랙을 부르지 않고 설정·DB 만 점검
import json, os, sqlite3, sys, time, urllib.error, urllib.parse, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import DB, DATA_DIR as OUT, env  # noqa: E402
only = sys.argv[sys.argv.index('--only') + 1].split(',') if '--only' in sys.argv else None
calls = 0
DRY = '--dry-run' in sys.argv  # 슬랙을 부르지 않고 설정·DB만 점검


def token():
    t = env('SLACK_BOT_TOKEN')
    if not t:
        sys.exit('SLACK_BOT_TOKEN 이 없어요 (.env 에 xoxb-… 봇 토큰을 넣어요)')
    return t


def api(method, **p):
    global calls
    tok = token()
    while True:
        calls += 1
        req = urllib.request.Request(f'https://slack.com/api/{method}?{urllib.parse.urlencode(p)}', headers={'Authorization': f'Bearer {tok}'})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                j = json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(int(e.headers.get('Retry-After', '5')) + 1); continue
            raise
        if not j.get('ok'):
            if j.get('error') == 'ratelimited':
                time.sleep(5); continue
            raise RuntimeError(f'{method}: {j.get("error")}')
        return j


def pages(method, key, **p):
    cur = ''
    while True:
        j = api(method, limit=200, **({'cursor': cur} if cur else {}), **p)
        yield from j.get(key, [])
        cur = (j.get('response_metadata') or {}).get('next_cursor')
        if not cur:
            return


def db():
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    c = sqlite3.connect(DB)
    c.executescript('''
      create table if not exists channels (id text primary key, name text, private int, purpose text, raw text, updated int);
      create table if not exists users (id text primary key, name text, img text, bot int, raw text, updated int);
      create table if not exists messages (channel text, ts text, thread_ts text, user text, text text, latest_reply text, raw text, updated int, primary key (channel, ts));
      create index if not exists messages_thread on messages (channel, thread_ts);
      create table if not exists moves (channel text, ts text, to_channel text, note text, primary key (channel, ts, to_channel));
      create table if not exists channel_members (channel text, user text, primary key (channel, user));
      create table if not exists runs (at int, channels int, new_msgs int, calls int);
      create table if not exists meta (k text primary key, v text);
      create virtual table if not exists messages_fts using fts5(text, content='messages', content_rowid='rowid', tokenize='trigram');
      create trigger if not exists messages_fts_ai after insert on messages begin
        insert into messages_fts(rowid, text) values (new.rowid, new.text); end;
      create trigger if not exists messages_fts_ad after delete on messages begin
        insert into messages_fts(messages_fts, rowid, text) values ('delete', old.rowid, old.text); end;
      create trigger if not exists messages_fts_au after update of text on messages begin
        insert into messages_fts(messages_fts, rowid, text) values ('delete', old.rowid, old.text);
        insert into messages_fts(rowid, text) values (new.rowid, new.text); end;
    ''')
    if not c.execute("select 1 from messages_fts_idx limit 1").fetchone() and c.execute('select 1 from messages limit 1').fetchone():
        c.execute("insert into messages_fts(messages_fts) values ('rebuild')"); c.commit()  # 처음 한 번: 이미 있는 글 색인
    return c


def save(c, ch, m, now):
    c.execute('insert into messages values (?,?,?,?,?,?,?,?) on conflict(channel, ts) do update set text=excluded.text, latest_reply=excluded.latest_reply, raw=excluded.raw, updated=excluded.updated',
              (ch, m['ts'], m.get('thread_ts'), m.get('user'), m.get('text', ''), m.get('latest_reply'), json.dumps(m, ensure_ascii=False), now))


def fetch(c):
    now = int(time.time())
    at = api('auth.test')  # 어느 워크스페이스인지 기록 — 로그인 때 team id 일치 검사에 쓴다
    c.executemany('insert or replace into meta values (?,?)', [('team_id', at.get('team_id', '')), ('team_name', at.get('team', ''))]); c.commit()
    os.makedirs(OUT, exist_ok=True)  # 워크스페이스 커스텀 이모지 (보기 화면이 :뽀야확인: 같은 걸 그림으로)
    json.dump(api('emoji.list').get('emoji', {}), open(os.path.join(OUT, 'emoji.json'), 'w'), ensure_ascii=False)
    for u in pages('users.list', 'members'):
        pr = u.get('profile', {})
        c.execute('insert or replace into users values (?,?,?,?,?,?)', (u['id'], pr.get('display_name') or pr.get('real_name') or u.get('name'), pr.get('image_72'), int(u.get('is_bot', False)), json.dumps(u, ensure_ascii=False), now))
    chans = [x for x in pages('conversations.list', 'channels', types='public_channel,private_channel', exclude_archived='true') if x.get('is_member')]
    if only: chans = [x for x in chans if x['id'] in only]
    before = c.execute('select count(*) from messages').fetchone()[0]
    for ch in chans:
        c.execute('insert or replace into channels values (?,?,?,?,?,?)', (ch['id'], ch['name'], int(ch.get('is_private', False)), (ch.get('purpose') or {}).get('value', ''), json.dumps(ch, ensure_ascii=False), now))
        known = dict(c.execute('select ts, latest_reply from messages where channel=? and (thread_ts is null or thread_ts=ts)', (ch['id'],)))
        nthreads = 0
        for m in pages('conversations.history', 'messages', channel=ch['id']):
            if m.get('reply_count') and m.get('latest_reply') != known.get(m['ts'], '-'):
                for r in pages('conversations.replies', 'messages', channel=ch['id'], ts=m['ts']):
                    save(c, ch['id'], r, now)
                nthreads += 1
            save(c, ch['id'], m, now)
        c.commit()
        print(f'#{ch["name"]}: 스레드 새로 받음 {nthreads}', flush=True)
    new = c.execute('select count(*) from messages').fetchone()[0] - before
    c.execute('insert into runs values (?,?,?,?)', (now, len(chans), new, calls)); c.commit()
    print(f'받기 끝: 채널 {len(chans)}개 · 새 글 {new} · API {calls}번', flush=True)


def members(c):
    for (cid,) in c.execute('select id from channels').fetchall():
        c.execute('delete from channel_members where channel=?', (cid,))
        c.executemany('insert into channel_members values (?,?)', [(cid, u) for u in pages('conversations.members', 'members', channel=cid)])
    c.commit()
    print('멤버 갱신', c.execute('select count(*) from channel_members').fetchone()[0])


def _inl(els):
    out = ''
    for e in els or []:
        t = e.get('type')
        if t == 'text':
            x, st = e.get('text', ''), e.get('style') or {}
            if x.strip():
                if st.get('code'): x = f'`{x}`'
                if st.get('bold'): x = f'*{x}*'
                if st.get('italic'): x = f'_{x}_'
                if st.get('strike'): x = f'~{x}~'
            out += x
        elif t == 'link': out += f"<{e.get('url', '')}|{e['text']}>" if e.get('text') else f"<{e.get('url', '')}>"
        elif t == 'user': out += f"<@{e.get('user_id')}>"
        elif t == 'usergroup': out += f"<!subteam^{e.get('usergroup_id')}>"
        elif t == 'channel': out += f"<#{e.get('channel_id')}>"
        elif t == 'emoji': out += f":{e.get('name')}:"
        elif t == 'broadcast': out += f"<!{e.get('range')}>"
        elif t == 'date': out += e.get('fallback', '')
    return out


def blocks_text(blocks):
    """rich_text 블록 → 줄바꿈·불렛이 살아 있는 mrkdwn. m.text 는 슬랙이 한 줄로 납작하게 만든 대체 글이라 목록이 다 붙어 보인다"""
    lines = []
    for b in blocks or []:
        if b.get('type') == 'rich_text':
            for el in b.get('elements', []):
                t = el.get('type')
                if t == 'rich_text_section': lines.append(_inl(el.get('elements')))
                elif t == 'rich_text_list':
                    pad = '    ' * el.get('indent', 0)
                    for i, it in enumerate(el.get('elements', [])):
                        mark = f'{el.get("offset", 0) + i + 1}.' if el.get('style') == 'ordered' else '•'
                        lines.append(f'{pad}{mark} {_inl(it.get("elements"))}')
                elif t == 'rich_text_preformatted': lines.append('```' + _inl(el.get('elements')) + '```')
                elif t == 'rich_text_quote': lines.append('\n'.join('> ' + l for l in _inl(el.get('elements')).split('\n')))
        elif b.get('type') in ('section', 'context', 'header'):
            tx = b.get('text') or {}
            if tx.get('text'): lines.append(tx['text'])
            for f in b.get('fields') or []: lines.append(f.get('text', ''))
            for e in b.get('elements') or [] if b.get('type') == 'context' else []: lines.append(e.get('text', ''))
    return '\n'.join(lines).strip('\n')


def slim(raw, users):
    m = json.loads(raw)
    o = {'ts': m['ts'], 'text': (blocks_text(m.get('blocks')) if m.get('blocks') else '') or m.get('text', '')}
    if m.get('user'): o['u'] = m['user']
    bp = m.get('bot_profile')
    if not m.get('user') and (bp or m.get('username')):
        o['bot'] = {'name': m.get('username') or (bp or {}).get('name'), 'img': ((bp or {}).get('icons') or {}).get('image_48') or (m.get('icons') or {}).get('image_48')}
    if m.get('subtype'): o['sub'] = m['subtype']
    if m.get('files'): o['files'] = [f.get('name') or f.get('title') or '파일' for f in m['files']]
    if m.get('reactions'): o['re'] = [[r['name'], r.get('count', 1)] for r in m['reactions']]
    if m.get('edited'): o['ed'] = 1
    return o


def build(c):
    os.makedirs(OUT, exist_ok=True)
    users = {i: {'name': n, 'img': img, 'bot': bool(b)} for i, n, img, b in c.execute('select id, name, img, bot from users')}
    moved = {}
    for ch, ts, to, note in c.execute('select channel, ts, to_channel, note from moves'):
        moved.setdefault(to, []).append((ch, ts, note))
    names = dict(c.execute('select id, name from channels'))
    out = []
    for cid, name, priv, purpose in c.execute('select id, name, private, purpose from channels order by name').fetchall():
        rows = c.execute("select ts, thread_ts, raw from messages where channel=? and coalesce(json_extract(raw,'$.subtype'),'') not in ('channel_join','channel_leave','thread_broadcast') order by cast(ts as real)", (cid,)).fetchall()
        tops, reps = [], {}
        for ts, tts, raw in rows:
            if tts and tts != ts: reps.setdefault(tts, []).append(slim(raw, users))
            else: tops.append((ts, slim(raw, users)))
        msgs = []
        for ts, o in tops:
            if ts in reps: o['replies'] = reps[ts]
            msgs.append(o)
        for src, ts, note in moved.get(cid, []):
            r = c.execute('select raw from messages where channel=? and ts=?', (src, ts)).fetchone()
            if not r: continue
            o = slim(r[0], users); o['from'] = names.get(src, src)
            if note: o['note'] = note
            o['replies'] = [slim(x[0], users) for x in c.execute('select raw from messages where channel=? and thread_ts=? and ts!=? order by cast(ts as real)', (src, ts, ts))]
            if not o['replies']: del o['replies']
            msgs.append(o)
        msgs.sort(key=lambda x: float(x['ts']))
        json.dump(msgs, open(os.path.join(OUT, f'{cid}.json'), 'w'), ensure_ascii=False, separators=(',', ':'))
        n = len(msgs) + sum(len(m.get('replies', [])) for m in msgs)
        out.append({'id': cid, 'name': name, 'private': bool(priv), 'topic': purpose, 'count': n, 'last': msgs[-1]['ts'] if msgs else None})
    acc = {'channels': {}}
    for cid, u in c.execute('select channel, user from channel_members'): acc['channels'].setdefault(cid, []).append(u)
    json.dump(acc, open(os.path.join(OUT, 'access.json'), 'w'), ensure_ascii=False)
    last = c.execute('select max(at) from runs').fetchone()[0] or int(time.time())
    meta = dict(c.execute('select k, v from meta'))
    team = env('SLACK_TEAM_NAME') or meta.get('team_name') or '슬랙'
    json.dump({'team': team, 'team_id': meta.get('team_id') or env('SLACK_TEAM_ID'), 'exported': last, 'channels': out, 'users': users}, open(os.path.join(OUT, 'index.json'), 'w'), ensure_ascii=False, separators=(',', ':'))
    print(f'사이트 JSON: 채널 {len(out)}개 · 글 {sum(x["count"] for x in out)} → {os.path.normpath(OUT)}')


c = db()
if DRY:
    print('드라이런 ok: DB', DB, '· 데이터 폴더', OUT, '· 토큰', '있음' if env('SLACK_BOT_TOKEN') else '없음(실제 받기 전에 필요)')
    sys.exit(0)
if '--add-moves' in sys.argv:
    i = sys.argv.index('--add-moves'); tsv, src, to = sys.argv[i + 1:i + 4]
    rows = [l.rstrip('\n').split('\t', 1) for l in open(tsv) if l.strip()]
    c.executemany('insert or replace into moves values (?,?,?,?)', [(src, r[0], to, r[1] if len(r) > 1 else '') for r in rows]); c.commit()
    print(f'옮김 {len(rows)}줄: {src} → {to}')
elif '--members' in sys.argv: members(c)
elif '--build-only' not in sys.argv:
    fetch(c); members(c)
build(c)
