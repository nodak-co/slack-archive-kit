#!/usr/bin/env python3
# restore.sh 가 부른다: 월별 백업 DB 여러 개 → 정본과 같은 꼴의 DB 하나
# 글(messages)·실행기록(runs)은 전부 합치고, 채널·사람·멤버·옮김은 제일 마지막(최근) 파일 것을 쓴다
# 사용: month-merge.py <새.db> <월별1.db> <월별2.db> …   (파일 이름순 = upto-… 다음 달 순서)
import sqlite3, sys

out, parts = sys.argv[1], sorted(sys.argv[2:], key=lambda p: (0 if 'upto-' in p else 1, p))  # upto-… 먼저, 그 뒤 달 순서
d = sqlite3.connect(out)
d.executescript('''
  create table channels (id text primary key, name text, private int, purpose text, raw text, updated int);
  create table users (id text primary key, name text, img text, bot int, raw text, updated int);
  create table messages (channel text, ts text, thread_ts text, user text, text text, latest_reply text, raw text, updated int, primary key (channel, ts));
  create index messages_thread on messages (channel, thread_ts);
  create table moves (channel text, ts text, to_channel text, note text, primary key (channel, ts, to_channel));
  create table channel_members (channel text, user text, primary key (channel, user));
  create table runs (at int, channels int, new_msgs int, calls int);
  create table meta (k text primary key, v text);
''')
for i, p in enumerate(parts):
    d.execute('attach ? as s', (p,))
    d.execute('insert or replace into messages select * from s.messages')
    d.execute('insert into runs select * from s.runs where at not in (select at from runs)')
    if i == len(parts) - 1:
        for t in ('channels', 'users', 'channel_members', 'moves', 'meta'):
            d.execute(f'insert or replace into {t} select * from s.{t}')
    d.commit()
    d.execute('detach s')
print('무결성:', d.execute('pragma integrity_check').fetchone()[0])
print('글:', d.execute('select count(*) from messages').fetchone()[0], '· 채널:', d.execute('select count(*) from channels').fetchone()[0], '· 파일', len(parts), '개')
