// 전체 채널 찾기 — /api/search (messages_fts). 결과를 누르면 그 채널·스레드로 간다 (#c=&t=)
(() => {
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);
  const when = (ts) => { const d = new Date(parseFloat(ts) * 1000 + 9 * 3600e3); return `${d.getUTCFullYear()}.${d.getUTCMonth() + 1}.${d.getUTCDate()} ${String(d.getUTCHours()).padStart(2, '0')}:${String(d.getUTCMinutes()).padStart(2, '0')}`; };
  let names = null;
  const meta = () => names || (names = fetch('/api/slack').then((r) => r.json()));
  const close = () => { $('res').hidden = true; $('app').hidden = false; };
  $('gs').addEventListener('submit', async (e) => {
    e.preventDefault();
    const q = $('gq').value.trim();
    if (!q) return close();
    const [idx, r] = await Promise.all([meta(), fetch(`/api/search?q=${encodeURIComponent(q)}`).then((x) => x.json())]);
    const ch = Object.fromEntries(idx.channels.map((c) => [c.id, c.name]));
    const re = new RegExp(`(${esc(q).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi');
    const row = (h) => {
      const t = esc((h.text || '').replace(/\s+/g, ' ').slice(0, 220)).replace(re, '<mark>$1</mark>');
      const hash = new URLSearchParams({ c: h.c, ...(h.tt ? { t: h.tt } : {}) });
      return `<a href="#${hash}" data-go><small>#${esc(ch[h.c] || h.c)} · ${esc(idx.users[h.u]?.name || h.u || '앱')} · ${when(h.ts)}</small><div>${t}</div></a>`;
    };
    $('res').innerHTML = `<div class=x><span>「${esc(q)}」 ${r.hits.length}${r.hits.length >= 200 ? '+' : ''}건 · 최근 것부터</span><a href="#" id=rx>닫기 ✕</a></div>${r.hits.map(row).join('') || '<div class=x>찾은 글이 없어요</div>'}`;
    $('res').hidden = false; $('app').hidden = true;
    $('rx').addEventListener('click', (ev) => { ev.preventDefault(); close(); });
    $('res').querySelectorAll('[data-go]').forEach((a) => a.addEventListener('click', close));
  });
})();
