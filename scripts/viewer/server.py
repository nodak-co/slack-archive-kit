#!/usr/bin/env python3
# 슬랙 보관함 보기 화면 서버 — 127.0.0.1 에만 붙는다. 밖에서는 Cloudflare Tunnel(공개 모드) 또는 tailscale serve(테일넷 모드)를 거쳐서만 들어온다.
#
# 접근 방식(AUTH_MODE = slack | google | tailnet):
#   slack      (기본) Sign in with Slack(OpenID Connect) → 서명된 세션 쿠키 → 그 사람이 멤버인 채널만 (DB channel_members 기준)
#              워크스페이스(team id)가 SLACK_TEAM_ID 와 다르면 거절. 로그인 안 한 사람은 0채널.
#   google     Google Workspace 회사계정 로그인(hd 파라미터 + id_token 의 hd·email_verified 검사) → 이메일 → 슬랙 users 표 email 로 슬랙 ID 매칭
#              → 그 사람이 멤버인 채널만. 매칭 안 되면 0채널
#   tailnet    Tailscale-User-Login 헤더 + 매핑 파일(SLACK_VIEWER_ACCESS = {"로그인": "슬랙ID"}) → 그 사람이 멤버인 채널만
#   DEV_USER=U…  개발·시험용: 로그인 없이 그 슬랙 ID 로 본다. 기본 꺼짐. PUBLIC_URL 이 있으면(=공개 배포) 서버가 시작을 거부한다.
#
# 데이터: 채널 글 DATA_DIR/<채널>.json · access.json · index.json (slack-export.py 가 만듦) · 검색 DB messages_fts
import base64, hashlib, hmac, json, os, re, secrets, sqlite3, sys, time, urllib.parse, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from common import DB, DATA_DIR as DATA, env, path  # noqa: E402

PORT = int(env('PORT', '43140'))
MODE = (env('AUTH_MODE') or env('AUTH') or 'slack').lower()
if MODE == 'tailscale':
    MODE = 'tailnet'  # 옛 이름
GOOGLE_ID, GOOGLE_SECRET, GOOGLE_HD = env('GOOGLE_CLIENT_ID'), env('GOOGLE_CLIENT_SECRET'), env('GOOGLE_HD').lower()
PUBLIC_URL = env('PUBLIC_URL').rstrip('/')
TEAM_ID = env('SLACK_TEAM_ID')
CLIENT_ID, CLIENT_SECRET = env('SLACK_CLIENT_ID'), env('SLACK_CLIENT_SECRET')
SECRET = env('SESSION_SECRET').encode()
SESSION_DAYS = int(env('SESSION_DAYS', '7'))
SCOPE = env('SLACK_LOGIN_SCOPE', 'openid profile email')
ACCESS = path('SLACK_VIEWER_ACCESS', 'viewer-access.json')
DEV_USER = env('DEV_USER')
SECURE = PUBLIC_URL.startswith('https://')
STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
TYPES = {'.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8', '.svg': 'image/svg+xml'}
OPEN_STATIC = {'/slack.css', '/slack.js', '/emoji-map.js', '/search.js'}  # 데이터 없는 화면 부품은 로그인 전에도 내준다

LOGIN_PAGE = '''<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1"><meta name=robots content=noindex><title>슬랙 보관함</title>
<body style="font-family:-apple-system,'Apple SD Gothic Neo',sans-serif;background:#f6f5f2;display:grid;place-items:center;height:100vh;margin:0">
<div style="background:#fff;border:1px solid #e5e5e5;border-radius:14px;padding:32px 36px;text-align:center;max-width:340px">
<h2 style="margin:0 0 8px">슬랙 보관함</h2><p style="color:#6b6b6b;font-size:14px;margin:0 0 20px">{msg}</p>
<a href="/login" style="display:inline-block;background:#4a154b;color:#fff;text-decoration:none;padding:10px 18px;border-radius:8px;font-weight:600">Sign in with Slack</a></div>'''


# ── 세션 쿠키: base64(json).서명 (HMAC-SHA256) ──
def sign(payload):
    b = base64.urlsafe_b64encode(json.dumps(payload, separators=(',', ':')).encode()).decode().rstrip('=')
    return b + '.' + hmac.new(SECRET, b.encode(), hashlib.sha256).hexdigest()


def unsign(tok):
    try:
        b, sig = tok.rsplit('.', 1)
        if not hmac.compare_digest(sig, hmac.new(SECRET, b.encode(), hashlib.sha256).hexdigest()):
            return None
        p = json.loads(base64.urlsafe_b64decode(b + '=' * (-len(b) % 4)))
        return p if p.get('exp', 0) > time.time() else None
    except Exception:
        return None


def rd(f):
    with open(os.path.join(DATA, f), encoding='utf-8') as fp:
        return json.load(fp)


def channels_of(slack_id):
    """슬랙 ID → 그 사람이 멤버인 채널 집합 (access.json 의 channel_members 기준)"""
    if not slack_id:
        return set()
    return {c for c, mem in rd('access.json')['channels'].items() if slack_id in mem}


def slack_id_by_email(email):
    """슬랙 users 표(이어 받을 때 채워짐, 봇에 users:read.email 필요)의 email 로 슬랙 user id 찾기. 없거나 둘 이상이면 None"""
    try:
        c = sqlite3.connect(f'file:{DB}?mode=ro', uri=True)
        rows = c.execute("select id from users where bot=0 and lower(json_extract(raw,'$.profile.email'))=? and coalesce(json_extract(raw,'$.deleted'),0)=0", (email,)).fetchall()
        return rows[0][0] if len(rows) == 1 else None
    except Exception:
        return None


def slack_post(method, data=None, token=None):
    h = {'Authorization': f'Bearer {token}'} if token else {}
    req = urllib.request.Request(f'https://slack.com/api/{method}', data=urllib.parse.urlencode(data).encode() if data is not None else None, headers=h)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


class H(BaseHTTPRequestHandler):
    def log_message(self, fmt, *a):
        sys.stderr.write(f'{time.strftime("%F %T")} {fmt % a}\n')  # 쿠키·토큰은 찍지 않는다

    def send(self, code, body, ctype='application/json; charset=utf-8', headers=()):
        b = body if isinstance(body, bytes) else (body if isinstance(body, str) else json.dumps(body, ensure_ascii=False)).encode()
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Cache-Control', 'private, no-store')
        self.send_header('X-Robots-Tag', 'noindex')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'same-origin')
        self.send_header('Content-Length', str(len(b)))
        for k, v in headers:
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(b)

    def redirect(self, to, headers=()):
        self.send(302, b'', 'text/plain', [('Location', to), *headers])

    def cookie(self, name):
        for part in (self.headers.get('Cookie') or '').split(';'):
            k, _, v = part.strip().partition('=')
            if k == name:
                return v
        return ''

    def set_cookie(self, name, val, max_age):
        return ('Set-Cookie', f'{name}={val}; Path=/; Max-Age={max_age}; HttpOnly; SameSite=Lax' + ('; Secure' if SECURE else ''))

    def who(self):
        """→ (표시용 이름, 슬랙 ID 또는 None). 슬랙 ID 가 없으면 0채널"""
        if DEV_USER:
            return 'dev:' + DEV_USER, DEV_USER
        if MODE == 'tailnet':
            login = (self.headers.get('Tailscale-User-Login') or '').lower()
            if not login:
                return None, None
            try:
                return login, json.load(open(ACCESS)).get(login)
            except FileNotFoundError:
                return login, None
        s = unsign(self.cookie('sk_session'))
        return (s.get('n') or s['u'], s['u']) if s else (None, None)

    # ── 로그인 (Sign in with Slack) ──
    def login(self):
        if MODE not in ('slack', 'google'):
            return self.send(404, '없어요', 'text/plain; charset=utf-8')
        state, nonce = secrets.token_urlsafe(24), secrets.token_urlsafe(16)
        if MODE == 'google':
            q = urllib.parse.urlencode({'response_type': 'code', 'scope': 'openid email', 'client_id': GOOGLE_ID, 'state': state, 'nonce': nonce, 'hd': GOOGLE_HD,
                                        'redirect_uri': PUBLIC_URL + '/auth/callback', 'prompt': 'select_account'})
            return self.redirect('https://accounts.google.com/o/oauth2/v2/auth?' + q, [self.set_cookie('sk_state', sign({'s': state, 'n': nonce, 'exp': time.time() + 600}), 600)])
        q = urllib.parse.urlencode({'response_type': 'code', 'scope': SCOPE, 'client_id': CLIENT_ID, 'state': state, 'nonce': nonce,
                                    'redirect_uri': PUBLIC_URL + '/auth/callback', 'team': TEAM_ID})
        self.redirect('https://slack.com/openid/connect/authorize?' + q, [self.set_cookie('sk_state', sign({'s': state, 'exp': time.time() + 600}), 600)])

    def callback(self, q):
        st = unsign(self.cookie('sk_state'))
        if not st or not hmac.compare_digest(st['s'], (q.get('state') or [''])[0]):
            return self.send(400, LOGIN_PAGE.format(msg='로그인 확인이 어긋났어요. 다시 시도해 주세요.'), 'text/html; charset=utf-8')
        if q.get('error') or not q.get('code'):
            return self.send(400, LOGIN_PAGE.format(msg='슬랙 로그인이 취소됐어요.'), 'text/html; charset=utf-8')
        if MODE == 'google':
            return self.google_callback(q, st)
        try:
            t = slack_post('openid.connect.token', {'client_id': CLIENT_ID, 'client_secret': CLIENT_SECRET, 'code': q['code'][0], 'redirect_uri': PUBLIC_URL + '/auth/callback'})
            if not t.get('ok'):
                raise RuntimeError(t.get('error'))
            info = slack_post('openid.connect.userInfo', None, t['access_token'])
            if not info.get('ok'):
                raise RuntimeError(info.get('error'))
        except Exception as e:
            sys.stderr.write(f'로그인 실패: {e}\n')
            return self.send(502, LOGIN_PAGE.format(msg='슬랙과 이야기하다 실패했어요. 잠시 뒤 다시 시도해 주세요.'), 'text/html; charset=utf-8')
        uid, team = info.get('https://slack.com/user_id'), info.get('https://slack.com/team_id')
        if not uid or not TEAM_ID or team != TEAM_ID:  # 다른 워크스페이스는 거부
            sys.stderr.write(f'다른 워크스페이스 로그인 거부: team={team}\n')
            return self.send(403, LOGIN_PAGE.format(msg='이 워크스페이스 멤버만 볼 수 있어요.'), 'text/html; charset=utf-8')
        sess = sign({'u': uid, 'n': info.get('name') or info.get('given_name') or uid, 't': team, 'exp': time.time() + SESSION_DAYS * 86400})
        self.redirect(self.next_path(), [self.set_cookie('sk_session', sess, SESSION_DAYS * 86400), self.set_cookie('sk_state', '', 0), self.set_cookie('sk_next', '', 0)])

    def next_path(self):
        p = urllib.parse.unquote(self.cookie('sk_next'))
        return p if re.match(r'^/c/[A-Z0-9]+/[tm]/[0-9.]+/?(\?m=[0-9.]+)?$', p) else '/'  # 우리 딥링크 모양만 (오픈 리다이렉트 방지)

    def google_callback(self, q, st):
        try:
            req = urllib.request.Request('https://oauth2.googleapis.com/token', data=urllib.parse.urlencode({
                'code': q['code'][0], 'client_id': GOOGLE_ID, 'client_secret': GOOGLE_SECRET, 'redirect_uri': PUBLIC_URL + '/auth/callback', 'grant_type': 'authorization_code'}).encode())
            with urllib.request.urlopen(req, timeout=20) as r:
                tok = json.load(r)
            # id_token 은 구글 토큰 주소에서 TLS 로 직접 받은 것이라 서명 검증 없이 내용만 검사해도 된다(구글 문서). aud·iss·exp·nonce·hd·email_verified 확인
            b = tok['id_token'].split('.')[1]
            c = json.loads(base64.urlsafe_b64decode(b + '=' * (-len(b) % 4)))
        except Exception as e:
            sys.stderr.write(f'구글 로그인 실패: {e}\n')
            return self.send(502, LOGIN_PAGE.format(msg='구글과 이야기하다 실패했어요. 잠시 뒤 다시 시도해 주세요.'), 'text/html; charset=utf-8')
        email = (c.get('email') or '').lower()
        good = (c.get('aud') == GOOGLE_ID and c.get('iss') in ('https://accounts.google.com', 'accounts.google.com') and c.get('exp', 0) > time.time()
                and hmac.compare_digest(str(c.get('nonce', '')), st.get('n', '')) and c.get('email_verified') in (True, 'true')
                and (c.get('hd') or '').lower() == GOOGLE_HD and email.endswith('@' + GOOGLE_HD))
        if not good:
            sys.stderr.write(f'회사 도메인이 아닌 구글 로그인 거부: hd={c.get("hd")}\n')
            return self.send(403, LOGIN_PAGE.format(msg='회사 구글 계정(' + GOOGLE_HD + ')만 들어올 수 있어요.'), 'text/html; charset=utf-8')
        uid = slack_id_by_email(email)  # 매칭 안 되면 빈 값 → 0채널
        sess = sign({'u': uid or '', 'n': email, 't': 'google', 'exp': time.time() + SESSION_DAYS * 86400})
        self.redirect(self.next_path(), [self.set_cookie('sk_session', sess, SESSION_DAYS * 86400), self.set_cookie('sk_state', '', 0), self.set_cookie('sk_next', '', 0)])

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(u.query)
        if u.path == '/healthz':
            return self.send(200, 'ok', 'text/plain')
        if u.path == '/login':
            return self.login()
        if u.path == '/auth/callback' and MODE == 'slack':
            return self.callback(q)
        if u.path == '/logout':
            return self.redirect('/', [self.set_cookie('sk_session', '', 0)])
        name, sid = self.who()
        if u.path == '/api/slack':
            if not name:
                return self.send(401, {'error': '로그인이 필요해요'})
            ok = channels_of(sid)
            f = (q.get('f') or ['index'])[0]
            if f == 'index':
                i = rd('index.json')
                if MODE != 'tailnet' and not DEV_USER and i.get('team_id') and TEAM_ID and i['team_id'] != TEAM_ID:
                    ok = set()  # 보관함 워크스페이스와 설정이 다르면 아무것도 안 보여줌
                i['channels'] = [c for c in i['channels'] if c['id'] in ok]
                i.pop('team_id', None)
                i['mapped'] = bool(sid)
                i['login'] = name
                i['auth'] = 'dev' if DEV_USER else MODE
                i['login'] = name
                ep = os.path.join(DATA, 'emoji.json')
                i['emoji'] = json.load(open(ep)) if os.path.exists(ep) else {}
                return self.send(200, i)
            if f not in ok or not f.isalnum():
                return self.send(403, {'error': '이 채널은 볼 수 없어요'})
            with open(os.path.join(DATA, f + '.json'), 'rb') as fp:
                return self.send(200, fp.read())
        if u.path == '/api/search':
            ok = channels_of(sid) if name else set()
            s = (q.get('q') or [''])[0].strip()
            if not ok or not s:
                return self.send(200, {'q': s, 'hits': []})
            c = sqlite3.connect(f'file:{DB}?mode=ro', uri=True)
            marks = ','.join('?' * len(ok))
            if len(s) >= 3:  # trigram 색인은 세 글자부터
                sql = f'select m.channel, m.ts, m.thread_ts, m.user, m.text from messages_fts f join messages m on m.rowid = f.rowid where messages_fts match ? and m.channel in ({marks})'
                p = ['"' + s.replace('"', '""') + '"', *ok]
            else:
                sql = f'select channel, ts, thread_ts, user, text from messages m where text like ? and channel in ({marks})'
                p = [f'%{s}%', *ok]
            rows = c.execute(sql + ' order by cast(m.ts as real) desc limit 200', p).fetchall()
            return self.send(200, {'q': s, 'hits': [{'c': r[0], 'ts': r[1], 'tt': r[2], 'u': r[3], 'text': r[4]} for r in rows]})
        dl = re.match(r'^/c/([A-Z0-9]+)/[tm]/[0-9.]+/?$', u.path)
        if dl:  # 딥링크: 화면은 index.html 그대로, 권한은 여기서 먼저 검사 (멤버 아니면 거부, 로그인 전이면 로그인 뒤 이 주소로 돌아옴)
            if not name:
                body = LOGIN_PAGE.format(msg='워크스페이스 멤버만 볼 수 있어요.') if MODE != 'tailnet' else '테일넷으로 들어와야 해요'
                return self.send(401 if MODE == 'tailnet' else 200, body, 'text/html; charset=utf-8', [self.set_cookie('sk_next', urllib.parse.quote(u.path + (('?' + u.query) if u.query else '')), 600)])
            if dl.group(1) not in channels_of(sid):
                return self.send(403, '<meta charset=utf-8><body style="font-family:sans-serif;padding:40px">이 채널은 볼 수 없어요. 슬랙에서 이 채널 멤버여야 해요.', 'text/html; charset=utf-8')
            with open(os.path.join(STATIC, 'index.html'), 'rb') as f:
                return self.send(200, f.read(), 'text/html; charset=utf-8')
        if u.path in ('/', '', '/index.html') and not name:  # 로그인 전: 로그인 안내만
            return self.send(401 if MODE == 'tailnet' else 200, LOGIN_PAGE.format(msg='워크스페이스 멤버만 볼 수 있어요.') if MODE != 'tailnet' else '테일넷으로 들어와야 해요', 'text/html; charset=utf-8')
        if u.path not in OPEN_STATIC and u.path not in ('/', '', '/index.html') and not name:
            return self.send(401, '로그인이 필요해요', 'text/plain; charset=utf-8')
        fp = os.path.normpath(os.path.join(STATIC, ('/index.html' if u.path in ('/', '') else u.path).lstrip('/')))
        if not fp.startswith(STATIC + os.sep) or not os.path.isfile(fp):
            return self.send(404, '없어요', 'text/plain; charset=utf-8')
        with open(fp, 'rb') as f:
            return self.send(200, f.read(), TYPES.get(os.path.splitext(fp)[1], 'application/octet-stream'))


def check():
    if DEV_USER and PUBLIC_URL:
        sys.exit('DEV_USER 는 시험용이에요 — PUBLIC_URL(공개 배포)이 있으면 켤 수 없어요')
    if DEV_USER:
        sys.stderr.write(f'⚠️ DEV_USER={DEV_USER} 개발 모드: 로그인 없이 그 사람으로 봅니다 (이 컴퓨터 안에서만)\n')
        return
    if MODE in ('slack', 'google'):
        need = {'SLACK_TEAM_ID': TEAM_ID, 'PUBLIC_URL': PUBLIC_URL}
        need.update({'SLACK_CLIENT_ID': CLIENT_ID, 'SLACK_CLIENT_SECRET': CLIENT_SECRET} if MODE == 'slack' else {'GOOGLE_CLIENT_ID': GOOGLE_ID, 'GOOGLE_CLIENT_SECRET': GOOGLE_SECRET, 'GOOGLE_HD': GOOGLE_HD})
        miss = [k for k, v in need.items() if not v]
        if miss:
            sys.exit(f'{MODE} 모드에 필요한 설정이 없어요: ' + ', '.join(miss))
        if len(SECRET) < 32:
            sys.exit('SESSION_SECRET 은 32자 이상 무작위 문자열이어야 해요 (python3 -c "import secrets;print(secrets.token_urlsafe(48))")')
        if not SECURE:
            sys.stderr.write('⚠️ PUBLIC_URL 이 https 가 아니라 쿠키에 Secure 가 안 붙어요 (공개 배포는 https 필수)\n')
    elif MODE != 'tailnet':
        sys.exit('AUTH_MODE 는 slack · google · tailnet 중 하나')


if __name__ == '__main__':
    check()
    print(f'슬랙 보관함 보기 화면: http://127.0.0.1:{PORT} (모드 {"dev" if DEV_USER else MODE})', flush=True)
    ThreadingHTTPServer(('127.0.0.1', PORT), H).serve_forever()
