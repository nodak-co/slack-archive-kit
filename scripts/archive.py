#!/usr/bin/env python3
"""봇용 슬랙 보관함 읽기 CLI — DB 를 읽기 전용으로만 연다(슬랙 API 안 부름). 결과마다 보기 화면 링크가 붙는다.
  archive.py search <검색어> [--channel 이름|ID] [--since YYYY-MM-DD] [--until YYYY-MM-DD] [--limit 20] [--json]
  archive.py thread <채널 이름|ID> <ts> [--json]        스레드 전체 글 (ts 는 스레드 첫 글이든 답글이든 됨)
  archive.py recent <채널 이름|ID> [--limit N] [--since …] [--json]   채널 최근 N글(channel 로도 부름) (스레드 답글 제외, 최신이 아래)
  archive.py channels [--json]                          채널 목록
링크 기준 주소: ARCHIVE_BASE_URL (없으면 PUBLIC_URL, 둘 다 없으면 링크 생략). 링크 형식 /c/<채널ID>/t/<스레드ts> · /c/<채널ID>/m/<ts>
이 CLI 는 이 컴퓨터의 DB 전체를 본다(주인용). 링크를 열 때는 보기 화면이 로그인·채널 멤버 검사를 다시 한다.
"""
import argparse, datetime as dt, json, os, sqlite3, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import DB, env  # noqa: E402

BASE = (env('ARCHIVE_BASE_URL') or env('VIEWER_BASE_URL') or env('PUBLIC_URL')).rstrip('/')
KST = dt.timezone(dt.timedelta(hours=9))


def conn():
    if not os.path.isfile(DB):
        sys.exit(f'DB 가 없어요: {DB} (먼저 slack-export.py 로 받기)')
    return sqlite3.connect(f'file:{DB}?mode=ro', uri=True)


def resolve(c, key):
    r = c.execute('select id, name from channels where id=? or name=? or name=?', (key, key, key.lstrip('#'))).fetchone()
    if not r:
        sys.exit(f'채널을 못 찾았어요: {key} (channels 로 목록 보기)')
    return r


def link(cid, ts, tts=None):
    if not BASE:
        return None
    return f'{BASE}/c/{cid}/t/{tts}' + (f'?m={ts}' if tts != ts else '') if tts else f'{BASE}/c/{cid}/m/{ts}'


def when(ts):
    return dt.datetime.fromtimestamp(float(ts), KST).strftime('%Y-%m-%d %H:%M')


def day_ts(s, end=False):
    d = dt.datetime.strptime(s, '%Y-%m-%d').replace(tzinfo=KST)
    return (d + dt.timedelta(days=1 if end else 0)).timestamp()


def row(c, names, users, cid, ts, tts, uid, text):
    top = tts if tts and tts != ts else ts  # 답글이면 부모 스레드, 아니면 자기 자신
    has_thread = bool(tts) or bool(c.execute('select 1 from messages where channel=? and thread_ts=? and ts!=? limit 1', (cid, ts, ts)).fetchone())
    return {'channel_id': cid, 'channel': names.get(cid, cid), 'ts': ts, 'thread_ts': top if has_thread else None, 'time': when(ts),
            'user_id': uid, 'user': users.get(uid, uid), 'text': text or '',
            'url': link(cid, ts, top if has_thread else None)}


def show(rows, as_json, extra=None):
    if as_json:
        print(json.dumps({**(extra or {}), 'count': len(rows), 'results': rows}, ensure_ascii=False, indent=1))
        return
    for r in rows:
        print(f"[{r['time']}] #{r['channel']} {r['user']}: {' '.join(r['text'].split())[:200]}")
        if r['url']:
            print(f"  {r['url']}")
    print(f'— {len(rows)}건', file=sys.stderr)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest='cmd', required=True)
    s = sp.add_parser('search'); s.add_argument('query'); s.add_argument('--channel'); s.add_argument('--since'); s.add_argument('--until'); s.add_argument('--limit', type=int, default=20); s.add_argument('--json', action='store_true')
    t = sp.add_parser('thread'); t.add_argument('channel'); t.add_argument('ts'); t.add_argument('--json', action='store_true')
    h = sp.add_parser('recent', aliases=['channel']); h.add_argument('channel'); h.add_argument('--limit', type=int, default=20); h.add_argument('--since'); h.add_argument('--json', action='store_true')
    l = sp.add_parser('channels'); l.add_argument('--json', action='store_true')
    a = ap.parse_args()
    c = conn()
    names, users = dict(c.execute('select id, name from channels')), dict(c.execute('select id, name from users'))

    if a.cmd == 'channels':
        rows = [{'id': i, 'name': n, 'private': bool(p), 'messages': m, 'url': f'{BASE}/#c={i}' if BASE else None}
                for i, n, p, m in c.execute('select c.id, c.name, c.private, (select count(*) from messages m where m.channel=c.id) from channels c order by c.name')]
        if a.json:
            print(json.dumps({'count': len(rows), 'results': rows}, ensure_ascii=False, indent=1))
        else:
            for r in rows: print(f"{r['id']}  #{r['name']}{' 🔒' if r['private'] else ''}  글 {r['messages']}")
        return
    if a.cmd == 'search':
        q, where, p = a.query, [], []
        if len(q) >= 3:
            sql, p = 'select m.channel, m.ts, m.thread_ts, m.user, m.text from messages_fts f join messages m on m.rowid = f.rowid where messages_fts match ?', ['"' + q.replace('"', '""') + '"']
        else:
            sql, p = 'select m.channel, m.ts, m.thread_ts, m.user, m.text from messages m where m.text like ?', [f'%{q}%']
        if a.channel: sql += ' and m.channel = ?'; p.append(resolve(c, a.channel)[0])
        if a.since: sql += ' and cast(m.ts as real) >= ?'; p.append(day_ts(a.since))
        if a.until: sql += ' and cast(m.ts as real) < ?'; p.append(day_ts(a.until, True))  # until 날짜 하루 끝까지 포함
        rows = [row(c, names, users, *r) for r in c.execute(sql + ' order by cast(m.ts as real) desc limit ?', p + [a.limit]).fetchall()]
        return show(rows, a.json, {'query': q})
    a.cmd = 'recent' if a.cmd == 'channel' else a.cmd
    cid, cname = resolve(c, a.channel)
    if a.cmd == 'thread':
        r = c.execute('select thread_ts from messages where channel=? and ts=?', (cid, a.ts)).fetchone()
        if not r: sys.exit(f'글을 못 찾았어요: {cname} {a.ts}')
        top = r[0] or a.ts
        ms = c.execute('select channel, ts, thread_ts, user, text from messages where channel=? and (ts=? or thread_ts=?) order by cast(ts as real)', (cid, top, top)).fetchall()
        rows = [row(c, names, users, *m) for m in ms]
        for x in rows: x['thread_ts'] = top
        if a.json:
            print(json.dumps({'channel': cname, 'channel_id': cid, 'thread_ts': top, 'url': link(cid, top, top), 'count': len(rows), 'results': rows}, ensure_ascii=False, indent=1))
        else:
            print(f"#{cname} 스레드 {top} · 글 {len(rows)}개" + (f"\n{link(cid, top, top)}" if BASE else ''))
            for x in rows: print(f"[{x['time']}] {x['user']}: {x['text']}\n")
        return
    sql, p = "select channel, ts, thread_ts, user, text from messages where channel=? and (thread_ts is null or thread_ts=ts) and coalesce(json_extract(raw,'$.subtype'),'') not in ('channel_join','channel_leave')", [cid]
    if a.since: sql += ' and cast(ts as real) >= ?'; p.append(day_ts(a.since))
    ms = c.execute(sql + ' order by cast(ts as real) desc limit ?', p + [a.limit]).fetchall()[::-1]
    show([row(c, names, users, *m) for m in ms], a.json, {'channel': cname, 'channel_id': cid})


main()
