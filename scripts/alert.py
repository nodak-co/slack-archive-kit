#!/usr/bin/env python3
# 경보 채널에 한 줄 (선택). ALERT_SLACK_CHANNEL 이 비어 있으면 아무것도 안 하고 끝낸다.
# 사용: alert.py <제목> <내용> [<스크립트 경로>]   (봇에 chat:write 권한 + 그 채널에 들어가 있어야 함)
import json, os, sys, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import env  # noqa: E402

ch, tok = env('ALERT_SLACK_CHANNEL'), env('ALERT_SLACK_TOKEN') or env('SLACK_BOT_TOKEN')
if not ch or not tok:
    print('경보 채널 설정 없음 — 건너뜀'); sys.exit(0)
title, body = sys.argv[1], sys.argv[2]
where = sys.argv[3] if len(sys.argv) > 3 else ''
text = f'{title}\n```{body[-500:]}```' + (f'\n스크립트: {where}' if where else '')
req = urllib.request.Request('https://slack.com/api/chat.postMessage', data=json.dumps({'channel': ch, 'text': text}).encode(),
                             headers={'Authorization': f'Bearer {tok}', 'Content-Type': 'application/json; charset=utf-8'})
print('경보:', json.load(urllib.request.urlopen(req, timeout=20)).get('ok'))
