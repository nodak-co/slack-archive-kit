// 슬랙 보관함 보기 화면 — 왼쪽 채널 | 가운데 채널 글 | 오른쪽 스레드. 데이터 /api/slack (server.py가 로그인·채널 멤버 확인 뒤 내줌)
// 주소 #c=<채널ID>&t=<스레드ts>&q=<찾기>
(() => {
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);
  const KST = (ts) => new Date(parseFloat(ts) * 1000 + 9 * 3600e3);
  const WD = '일월화수목금토';
  const day = (ts) => { const d = KST(ts); return `${d.getUTCFullYear()}년 ${d.getUTCMonth() + 1}월 ${d.getUTCDate()}일 (${WD[d.getUTCDay()]})`; };
  const dkey = (ts) => KST(ts).toISOString().slice(0, 10);
  const time = (ts) => { const d = KST(ts); const h = d.getUTCHours(); return `${h < 12 ? '오전' : '오후'} ${h % 12 || 12}:${String(d.getUTCMinutes()).padStart(2, '0')}`; };
  const EMO = { '+1': '👍', thumbsup: '👍', heart: '❤️', joy: '😂', smile: '😄', pray: '🙏', clap: '👏', fire: '🔥', eyes: '👀', white_check_mark: '✅', heavy_check_mark: '✔️', tada: '🎉', raised_hands: '🙌', ok_hand: '👌', 100: '💯', sob: '😭', thinking_face: '🤔', rocket: '🚀', house_with_garden: '🏡', clapper: '🎬', up: '🆙', x: '❌', warning: '⚠️', star: '⭐', sparkles: '✨', bulb: '💡', memo: '📝', pushpin: '📌', laughing: '😆', grinning: '😀', blush: '😊', hugging_face: '🤗', muscle: '💪', cat: '🐱', seedling: '🌱', chestnut: '🌰', rotating_light: '🚨', exclamation: '❗', question: '❓', wave: '👋', slightly_smiling_face: '🙂', smiling_face_with_3_hearts: '🥰', heart_eyes: '😍', cry: '😢', sweat_smile: '😅', rolling_on_the_floor_laughing: '🤣', partying_face: '🥳', point_up: '☝️', point_right: '👉', point_down: '👇', point_left: '👈', arrow_right: '➡️', arrow_down: '⬇️', heavy_plus_sign: '➕', no_entry: '⛔', no_entry_sign: '🚫', construction: '🚧', package: '📦', gift: '🎁', trophy: '🏆', camera: '📷', art: '🎨', books: '📚', book: '📖', mag: '🔍', wrench: '🔧', hammer_and_wrench: '🛠️', gear: '⚙️', phone: '📞', iphone: '📱', computer: '💻', speech_balloon: '💬', loudspeaker: '📢', mega: '📣', calendar_spiral: '🗓️', date: '📅', clock3: '🕒', alarm_clock: '⏰', money_with_wings: '💸', receipt: '🧾', bar_chart: '📊', chart_with_upwards_trend: '📈', dart: '🎯', triangular_flag_on_post: '🚩', ok: '🆗', new: '🆕', sunglasses: '😎', scream: '😱', disappointed: '😞', confused: '😕', relieved: '😌', upside_down_face: '🙃', wink: '😉', yum: '😋', thumbsdown: '👎', '-1': '👎', raised_hand: '✋', handshake: '🤝', bow: '🙇', cat2: '🐈', black_cat: '🐈‍⬛', paw_prints: '🐾', blue_heart: '💙', green_heart: '💚', yellow_heart: '💛', purple_heart: '💜', two_hearts: '💕', sparkling_heart: '💖', boom: '💥', dizzy: '💫', star2: '🌟', crescent_moon: '🌙', sunny: '☀️', coffee: '☕', beer: '🍺', cake: '🍰', '1': '1️⃣', one: '1️⃣', two: '2️⃣', three: '3️⃣', four: '4️⃣', five: '5️⃣', calendar: '📅', moneybag: '💰', lock: '🔒', key: '🔑', link: '🔗', paperclip: '📎', inbox_tray: '📥', email: '📧', bell: '🔔', zap: '⚡', hourglass_flowing_sand: '⏳', ballot_box_with_check: '☑️', large_green_circle: '🟢', red_circle: '🔴', large_yellow_circle: '🟡' };
  // 커스텀(워크스페이스) → 표준(emoji-map.js) → 옛 짧은 표 순. alias:xxx 는 따라간다
  let custom = {};
  const emo = (n) => {
    let k = n.split('::')[0];
    for (let i = 0; i < 3 && (custom[k] || '').startsWith('alias:'); i++) k = custom[k].slice(6);
    if (custom[k] && !custom[k].startsWith('alias:')) return `<img class="sk-emo" src="${esc(custom[k])}" alt=":${esc(k)}:" title=":${esc(k)}:">`;
    const tone = (n.match(/::skin-tone-(\d)/) || [])[1];
    const f = (window.EMOJI_MAP || {})[k];
    if (f) return `<img class="sk-emo" src="https://cdn.jsdelivr.net/npm/emoji-datasource-apple@15.1.2/img/apple/64/${f}${tone ? '-' + ['', '', '1f3fb', '1f3fc', '1f3fd', '1f3fe', '1f3ff'][tone] : ''}.png" onerror="this.onerror=null;this.src=this.src.replace(/-1f3f[b-f]\.png$/, '.png')" alt=":${esc(k)}:" title=":${esc(k)}:">`;
    return EMO[k] || `:${esc(n)}:`;
  };

  // 슬랙처럼 선 자물쇠
  const LOCK = '<svg viewBox="0 0 16 16" width="13" height="13" fill="none" stroke="currentColor" stroke-width="1.6"><rect x="3" y="7" width="10" height="7.5" rx="1.6"/><path d="M5.2 7V5a2.8 2.8 0 0 1 5.6 0v2"/></svg>';
  let idx = null, users = {}, chans = [], cache = {}, show = 300;

  const who = (m) => {
    if (m.u && users[m.u]) return { name: users[m.u].name, img: users[m.u].img, bot: users[m.u].bot };
    if (m.bot) return { name: m.bot.name || '앱', img: m.bot.img, bot: true };
    return { name: m.u || '알 수 없음', bot: false };
  };
  const face = (w, cls = 'sk-av') => w.img ? `<img class="${cls}" src="${esc(w.img)}" alt="" loading="lazy">` : `<span class="${cls} sk-av-b">${esc((w.name || '?').slice(0, 1))}</span>`;

  // 슬랙 mrkdwn → HTML: <@U>·<#C|이름>·<주소|글>·코드·*굵게*·_기울임_·~취소~·인용·:이모지:
  function md(t, q) {
    const blocks = [];
    const keep = (h) => `\u0000${blocks.push(h) - 1}\u0000`;
    // 슬랙 원문은 < > & 를 &lt; &gt; &amp; 로 보낸다 → esc 뒤 두 번 이스케이프된 것만 한 번으로 (코드블록·인용 > 가 &gt; 로 보이던 것)
    let s = esc(t).replace(/&amp;(lt|gt|amp);/g, '&$1;')
      .replace(/```([\s\S]*?)```/g, (_, c) => keep(`<pre>${c.replace(/^\n/, '')}</pre>`))
      .replace(/`([^`\n]+)`/g, (_, c) => keep(`<code>${c}</code>`))
      .replace(/&lt;@([UW][A-Z0-9]+)(?:\|[^&]*)?&gt;/g, (_, id) => keep(`<span class="sk-at">@${esc(users[id]?.name || id)}</span>`))
      .replace(/&lt;#(C[A-Z0-9]+)(?:\|([^&]*))?&gt;/g, (_, id, n) => keep(`<span class="sk-at">#${esc(n || chans.find((c) => c.id === id)?.name || id)}</span>`))
      .replace(/&lt;!(here|channel|everyone)[^&]*&gt;/g, (_, n) => keep(`<span class="sk-at">@${n}</span>`))
      .replace(/&lt;!subteam\^[A-Z0-9]+(?:\|([^&]*))?&gt;/g, (_, n) => keep(`<span class="sk-at">${n || '@그룹'}</span>`))
      .replace(/&lt;((?:https?|mailto):[^|&]+?)(?:\|(.*?))?&gt;/g, (_, u, l) => keep(`<a href="${u}" target="_blank" rel="noopener">${l || u}</a>`))
      .replace(/(^|[\s(])(https?:\/\/[^\s<]+)/g, (_, a, u) => a + keep(`<a href="${u}" target="_blank" rel="noopener">${u}</a>`));
    s = s.replace(/(^|[\s(])\*([^*\n]+)\*(?=$|[\s).,!?:;]|[가-힣])/g, '$1<b>$2</b>')
      .replace(/(^|[\s(])_([^_\n]+)_(?=$|[\s).,!?:;])/g, '$1<i>$2</i>')
      .replace(/(^|\s)~([^~\n]+)~(?=$|\s)/g, '$1<s>$2</s>')
      .replace(/:([\p{L}\p{N}_+\-]+(?:::[a-z0-9-]+)?):/gu, (a, n) => emo(n))
      .replace(/^&gt; ?(.*)$/gm, '<q>$1</q>')
      .replace(/\n/g, '<br>');
    if (q) { const re = new RegExp(`(${q.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi'); s = s.replace(/(^|>)([^<]*)/g, (_, a, b) => a + b.replace(re, '<mark>$1</mark>')); }
    return s.replace(/\u0000(\d+)\u0000/g, (_, i) => blocks[i]);
  }

  function msg(m, prev, extra = '', q = '') {
    const w = who(m);
    const cls = m.ts === hl ? ' hl' : '';
    const same = prev && !prev.sub && !m.sub && (prev.u || prev.bot?.name) === (m.u || m.bot?.name) && m.ts - prev.ts < 300 && dkey(m.ts) === dkey(prev.ts);
    const files = (m.files || []).map((f) => `<span class="sk-file">📎 ${esc(f)}</span>`).join('');
    const re = m.re ? `<div class="sk-re">${m.re.map(([n, c]) => `<span>${emo(n)} ${c}</span>`).join('')}</div>` : '';
    const from = m.from ? `<div class="sk-from">↪ #${esc(m.from)}에서 옮김${m.note ? ` · ${esc(m.note)}` : ''}</div>` : '';
    const body = `${from}<div class="sk-body">${md(m.text, q)}${m.ed ? ' <span class="sk-ed">(편집됨)</span>' : ''}${files ? `<div>${files}</div>` : ''}${re}</div>${extra}`;
    if (same && !m.from) return `<div class="sk-msg sk-cont${cls}" data-ts="${m.ts}"><span class="sk-t2">${time(m.ts).replace(/^오[전후] /, '')}</span><div>${body}</div></div>`;
    return `<div class="sk-msg${cls}" data-ts="${m.ts}"><button class="sk-cp" data-cp="m" data-ts="${m.ts}" title="링크 복사">🔗</button>${face(w)}<div><div class="sk-who"><b>${esc(w.name)}</b>${w.bot ? '<span class="sk-tag">앱</span>' : ''}<span class="sk-t">${time(m.ts)}</span></div>${body}</div></div>`;
  }

  const go = (p) => `#${new URLSearchParams(Object.entries(p).filter(([, v]) => v))}`;
  // 딥링크: /c/<채널ID>/t/<스레드ts>(?m=<답글ts>) · /c/<채널ID>/m/<ts>. 주소 뒤 #… 가 있으면 그게 우선(화면 안 이동)
  const state = () => {
    const q = new URLSearchParams(location.hash.slice(1));
    if (location.hash.length > 1) return { c: q.get('c') || '', t: q.get('t') || '', q: q.get('q') || '', m: '' };
    const p = location.pathname.match(/^\/c\/([A-Z0-9]+)\/([tm])\/([0-9.]+)\/?$/);
    if (!p) return { c: '', t: '', q: '', m: '' };
    const m = p[2] === 'm' ? p[3] : new URLSearchParams(location.search).get('m') || '';
    return { c: p[1], t: p[2] === 't' ? p[3] : '', q: '', m };
  };
  let hl = '';  // 강조할 글 ts
  const load = (id) => cache[id] || (cache[id] = fetch(`/api/slack?f=${id}&v=${idx.exported}`).then((r) => r.json()));

  function renderSide(c) {
    const row = (x) => `<a class="sk-cn${x.id === c ? ' on' : ''}" href="${go({ c: x.id })}"><i class="sk-ic">${x.private ? LOCK : '#'}</i><span>${esc(x.name)}</span></a>`;
    $('side').innerHTML = `<div class="sk-ws">${esc(idx.team)}</div><div class="sk-sg">채널</div>${chans.map(row).join('')}`;
  }

  const hit = (m, q) => m.text.toLowerCase().includes(q) || (m.files || []).some((f) => f.toLowerCase().includes(q));

  async function renderChan(c, t, q) {
    const ch = chans.find((x) => x.id === c);
    const msgs = await load(c);
    const ql = q.toLowerCase();
    let list = msgs;
    if (ql) list = msgs.filter((m) => hit(m, ql) || (m.replies || []).some((r) => hit(r, ql)));
    const from = Math.max(0, list.length - show);
    let prev = null, html = '', last = '';
    for (const m of list.slice(from)) {
      if (dkey(m.ts) !== last) { last = dkey(m.ts); html += `<div class="sk-day"><span>${day(m.ts)}</span></div>`; prev = null; }
      let extra = '';
      if (m.replies?.length) {
        const fs = [...new Map(m.replies.map((r) => { const w = who(r); return [w.name, w]; })).values()].slice(0, 4);
        const lr = m.replies[m.replies.length - 1];
        const nq = ql ? m.replies.filter((r) => hit(r, ql)).length : 0;
        extra = `<a class="sk-rep" href="${go({ c, t: m.ts, q })}">${fs.map((w) => face(w)).join('')}<b>답글 ${m.replies.length}개</b><span>${nq ? `찾은 답글 ${nq}개 · ` : ''}마지막 ${day(lr.ts).replace(/^\d+년 /, '')} ${time(lr.ts)}</span></a>`;
      }
      html += msg(m, prev, extra, ql).replace('class="sk-msg', `class="sk-msg${m.ts === t ? ' on' : ''}`);
      prev = m;
    }
    // 좁은 화면: 왼쪽 ☰ 버튼 → 채널 목록 서랍
    const menu = `<button class="sk-menu" id="menu" aria-label="채널 목록">☰</button>`;
    $('chan').innerHTML = `<div class="sk-bar">${menu}<div class="sk-ttl"><b><i class="sk-ic">${ch.private ? LOCK : '#'}</i>${esc(ch.name)}</b><span>${ql ? `「${esc(q)}」 ${list.length}개` : esc(ch.topic || `글 ${ch.count}개`)}</span></div><input class="sk-find" id="find" type="search" placeholder="이 채널에서 찾기" value="${esc(q)}"></div>
      <div class="sk-scroll" id="chanScroll">${from ? `<button class="sk-more" id="more">이전 글 ${from}개 더 보기</button>` : ''}${html || '<p class="sk-pick">글이 없어</p>'}</div>`;
    const sc = $('chanScroll');
    const on = sc.querySelector('.sk-msg.hl') || sc.querySelector('.sk-msg.on');
    if (on) on.scrollIntoView({ block: 'center' }); else sc.scrollTop = sc.scrollHeight;
    $('more')?.addEventListener('click', () => { const h = sc.scrollHeight; show += 300; renderChan(c, t, q).then(() => { $('chanScroll').scrollTop = $('chanScroll').scrollHeight - h; }); });
    $('menu').addEventListener('click', () => $('app').classList.toggle('side-open'));
    const f = $('find');
    f.addEventListener('keydown', (e) => { if (e.key === 'Enter') { show = 300; location.hash = go({ c, q: f.value.trim() }); } });
    f.addEventListener('search', () => { if (!f.value) location.hash = go({ c }); });
  }

  async function renderThread(c, t, q) {
    const m = t && (await load(c)).find((x) => x.ts === t);
    $('app').classList.toggle('has-t', !!m);
    if (!m) { $('thread').innerHTML = ''; return; }
    const ch = chans.find((x) => x.id === c);
    let prev = null;
    const body = (m.replies || []).map((r) => { const h = msg(r, prev, '', q.toLowerCase()); prev = r; return h; }).join('');
    $('thread').innerHTML = `<div class="sk-bar"><a class="sk-back" href="${go({ c, q })}">←</a><div><b>스레드</b><span># ${esc(ch.name)}</span></div><button class="sk-cp sk-cpt" data-cp="t" data-ts="${t}">링크 복사</button><a class="sk-x" href="${go({ c, q })}" aria-label="닫기">✕</a></div>
      <div class="sk-scroll">${msg(m, null)}<div class="sk-sep"><span>답글 ${(m.replies || []).length}개</span></div>${body}</div>`;
    $('thread').querySelector('.sk-msg.hl')?.scrollIntoView({ block: 'center' });
  }

  async function route() {
    let { c, t, q, m } = state();
    if (!chans.some((x) => x.id === c)) { c = chans[0].id; t = m = ''; }
    hl = m || '';
    if (m) {  // 글 하나 링크: 스레드 답글이면 부모 스레드를 펼치고, 오래된 글이면 그 글이 보이게 더 불러옴
      const all = await load(c);
      const top = all.findIndex((x) => x.ts === m);
      const par = top < 0 ? all.find((x) => (x.replies || []).some((r) => r.ts === m)) : null;
      if (par) { t = par.ts; hl = m; }
      const at = top >= 0 ? top : par ? all.indexOf(par) : -1;
      if (at >= 0 && all.length - at > show) show = all.length - at + 20;
    }
    renderSide(c);
    await renderChan(c, t, q);
    await renderThread(c, t, q);
  }

  // 링크 복사 (글 하나 /c/<채널>/m/<ts> · 스레드 /c/<채널>/t/<ts>)
  document.addEventListener('click', (e) => {
    const b = e.target.closest('[data-cp]'); if (!b) return;
    const url = `${location.origin}/c/${state().c}/${b.dataset.cp}/${b.dataset.ts}`;
    const done = () => { const o = b.textContent; b.textContent = '복사됨 ✓'; setTimeout(() => { b.textContent = o; }, 1200); };
    (navigator.clipboard ? navigator.clipboard.writeText(url) : Promise.reject()).then(done, () => { prompt('주소를 복사하세요', url); });
  });
  // 서랍 밖(어두운 곳)을 누르면 닫힘
  $('app').addEventListener('click', (e) => { if ($('app').classList.contains('side-open') && !e.target.closest('.sk-side, #menu')) $('app').classList.remove('side-open'); });
  let lastC = '';
  window.addEventListener('hashchange', () => { $('app').classList.remove('side-open'); const { c } = state(); if (c !== lastC) show = 300; lastC = c; route(); });
  fetch('/api/slack').then((r) => { if (r.status === 401) { location.href = '/login'; throw new Error('로그인이 필요해요'); } return r.json(); }).then((j) => {
    idx = j; users = j.users; custom = j.emoji || {};
    chans = j.channels.filter((x) => x.count).sort((a, b) => a.name.localeCompare(b.name, 'ko'));
    const d = new Date(j.exported * 1000 + 9 * 3600e3);
    $('ttl').textContent = `${idx.team} 슬랙 보관함`; document.title = `${idx.team} 슬랙 보관함`; if (j.auth === 'slack' || j.auth === 'google') $('lo').hidden = false;
    $('sum').textContent = `${idx.team} 슬랙 채널 ${chans.length}개 · 글 ${chans.reduce((a, x) => a + x.count, 0).toLocaleString()}개 · ${d.getUTCMonth() + 1}/${d.getUTCDate()} ${String(d.getUTCHours()).padStart(2, '0')}:${String(d.getUTCMinutes()).padStart(2, '0')} 기준`;
    if (!chans.length) { $('sum').textContent = j.mapped ? '볼 수 있는 채널이 없어요' : `로그인(${j.login || '?'})한 계정이 이 보관함의 채널 멤버가 아니에요 — 관리자에게 말해주세요`; $('app').hidden = true; return; }
    lastC = state().c;
    route();
  }).catch((e) => { $('sum').textContent = `불러오기 실패: ${e}`; });
})();
