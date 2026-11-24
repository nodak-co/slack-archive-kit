#!/usr/bin/env python3
# backup.sh 가 부른다: 정본 DB 에서 그달(KST) 글만 뽑아 새 SQLite 한 벌. 채널·사람·멤버·옮김·실행기록 표는 통째로
# 사용: month-extract.py <정본.db> <새.db> <YYYY-MM | upto-YYYY-MM>   → 뽑은 글 수를 찍는다
import datetime as dt, sqlite3, sys

src, out, tag = sys.argv[1:4]
upto = tag.startswith('upto-')
y, m = map(int, tag.replace('upto-', '').split('-'))
kst = dt.timezone(dt.timedelta(hours=9))
start = 0 if upto else dt.datetime(y, m, 1, tzinfo=kst).timestamp()
end = dt.datetime(y + (m == 12), m % 12 + 1, 1, tzinfo=kst).timestamp()

d = sqlite3.connect(out)
d.execute('attach ? as s', (f'file:{src}?mode=ro',))
for t in ('channels', 'users', 'channel_members', 'moves', 'runs', 'meta'):
    d.execute(f'create table {t} as select * from s.{t}')
d.execute('create table messages as select * from s.messages where cast(ts as real) >= ? and cast(ts as real) < ?', (start, end))
d.commit()
n = d.execute('select count(*) from messages').fetchone()[0]
if n == 0:
    sys.exit(f'{tag}: 그달 글이 0개')
print(n)
