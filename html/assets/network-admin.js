(() => {
  'use strict';
  let token = sessionStorage.getItem('expose_admin_token') || '';
  let model = null;
  let activeTab = 'overview';
  const $ = (id) => document.getElementById(id);

  function esc(s) {
    return String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }
  function fmtDate(s) {
    if (!s) return '—';
    const d = new Date(s);
    return Number.isNaN(d.valueOf()) ? String(s) : d.toLocaleString();
  }
  function toast(msg, isErr = false) {
    const el = isErr ? $('error-banner') : $('toast-banner');
    el.textContent = msg;
    el.classList.remove('hidden');
    if (!isErr) setTimeout(() => el.classList.add('hidden'), 5000);
  }
  async function api(path, opts = {}) {
    const hdrs = { 'Authorization': 'Bearer ' + token, ...(opts.headers || {}) };
    if (opts.body && !hdrs['Content-Type']) hdrs['Content-Type'] = 'application/json';
    const r = await fetch(path, { ...opts, headers: hdrs });
    const d = await r.json().catch(() => ({ ok: false, error: 'HTTP ' + r.status }));
    if (r.status === 401) {
      lock('Unauthorized token.');
      throw new Error('Unauthorized');
    }
    if (!r.ok || d.ok === false) throw new Error(d.error || ('HTTP ' + r.status));
    return d;
  }

  function lock(msg = '') {
    token = '';
    sessionStorage.removeItem('expose_admin_token');
    $('app').classList.add('hidden');
    $('login-view').classList.remove('hidden');
    if (msg) { $('login-error').textContent = msg; $('login-error').classList.remove('hidden'); }
  }

  function openCompose({ to = '', subject = '', body = '', reqId = '' } = {}) {
    $('cmp-to').value = to;
    $('cmp-subj').value = subject;
    $('cmp-body').value = body;
    $('cmp-reqid').value = reqId;
    $('cmp-status').textContent = '';
    $('compose-modal').classList.remove('hidden');
  }

  function switchTab(tab) {
    activeTab = tab;
    document.querySelectorAll('.tab').forEach(b => b.classList.toggle('active', b.dataset.tab === tab));
    ['overview', 'records', 'mailboxes', 'triage'].forEach(p => $('panel-' + p).classList.toggle('hidden', p !== tab));
  }

  function pillClass(st) {
    if (['ok', 'fulfilled', 'received', 'ready'].includes(st)) return 'pill-ok';
    if (['sent', 'partial_response', 'pending_review', 'queued', 'prepared_for_delivery', 'in_review'].includes(st)) return 'pill-warn';
    if (['error', 'down', 'denied', 'rejected'].includes(st)) return 'pill-err';
    return 'pill-info';
  }

  function render() {
    if (!model) return;
    $('snapshot-time').textContent = model.generated_at ? ('Network snapshot: ' + fmtDate(model.generated_at)) : 'Live';
    const chs = model.chapters || [];
    const reqs = model.requests || [];
    const netRec = model.network_records || {};
    const okCh = chs.filter(c => c.health?.status === 'ok' && c.automation?.status === 'ok').length;
    const pendingN = reqs.filter(r => ['pending_review', 'queued', 'prepared_for_delivery'].includes(r.status)).length;
    const sentN = reqs.filter(r => r.status === 'sent').length;
    const recN = netRec.received_count ?? reqs.filter(r => ['fulfilled', 'partial_response'].includes(r.status)).length;
    const mailObj = model.emails || { threads: {}, unmatched: [] };
    const mailCount = Object.keys(mailObj.threads || {}).length + (mailObj.unmatched || []).length;

    $('cnt-records').textContent = reqs.length;
    $('cnt-mail').textContent = mailCount;
    $('cnt-triage').textContent = (model.items || []).length;

    $('kpi-bar').innerHTML = [
      [okCh + ' / ' + chs.length, 'Chapters Healthy'],
      [recN, 'Received Records Published'],
      [sentN, 'Overdue / Awaiting Agency'],
      [pendingN, 'Private Pending Queue'],
      [Object.keys(mailObj.threads || {}).length, 'Matched Email Threads'],
      [(mailObj.unmatched || []).length, 'Inbox / Volunteer / Tips'],
    ].map(([v, l]) => `<div class="kpi"><div class="val">${esc(v)}</div><div class="lbl">${esc(l)}</div></div>`).join('');

    $('hub-links').innerHTML = [
      ['ExposeOklahoma', 'https://exposeoklahoma.com/'],
      ['ExposeTexas', 'https://exposetexas.org/'],
      ['ExposeMississippi', 'https://exposemississippi.com/'],
      ['Move Weight Foundation', 'https://foundation.moveweight.com/'],
      ['ExposeMiamiOK Public FOIA', '/foia/'],
      ['ExposeMiamiOK Review', '/foia/review.html'],
    ].map(([lbl, href]) => `<a class="pill pill-info" href="${href}" target="_blank" rel="noopener">${esc(lbl)} &rarr;</a>`).join('');

    const mh = model.mailbox_health || {};
    $('mailbox-health').innerHTML =
      `<div><div class="muted">IMAP Poll (foia@moveweight.com)</div><strong>${esc(fmtDate(mh.imap_last_checked))}</strong></div>` +
      `<div><div class="muted">Outbound SMTP Relay</div><strong>${esc(mh.smtp_relay || '—')}</strong></div>` +
      `<div><div class="muted">CT 170 Postfix Queue</div><strong>${esc(mh.postfix_queue || '—')}</strong></div>` +
      `<div><div class="muted">Indexed Mailboxes</div><strong>${esc(mh.thread_count || 0)} threads &middot; ${esc(mh.unmatched_count || 0)} inbox items</strong></div>`;

    $('chapters-grid').innerHTML = chs.map(c => `
      <div class="card">
        <div class="pill-row" style="justify-content:space-between">
          <strong>${esc(c.label)}</strong>
          <span class="pill ${pillClass(c.health?.status)}">${esc(c.health?.detail || c.health?.status)}</span>
        </div>
        <div class="muted" style="margin:.35rem 0">
          <a href="https://${esc(c.host)}/" target="_blank" rel="noopener">${esc(c.host)}</a>
        </div>
        <div class="pill-row">
          <span class="pill ${pillClass(c.automation?.status)}">Auto: ${esc(c.automation?.status)}</span>
          <span class="muted" style="font-size:.78rem">${esc(fmtDate(c.automation?.last_success_at))}</span>
        </div>
      </div>`).join('');

    renderRecords();
    renderMail();
    renderTriage();
  }

  function renderRecords() {
    const sf = $('rec-status-filter').value;
    const q = $('rec-search').value.trim().toLowerCase();
    const rows = (model.requests || []).slice().reverse().filter(r => {
      if (sf && !(sf === 'queued' ? ['queued', 'prepared_for_delivery'].includes(r.status) : r.status === sf)) return false;
      if (q && !(r.id + ' ' + r.description + ' ' + (r.recipient_name || r.agency || '')).toLowerCase().includes(q)) return false;
      return true;
    });
    $('records-list').innerHTML = rows.map(r => {
      const pubVis = ['fulfilled', 'partial_response', 'sent'].includes(r.status) ? 'PUBLIC' : 'PRIVATE (Admin only)';
      const files = (r.response_files || []).map(f => `<a class="pill pill-ok" href="${esc(f.url)}" target="_blank" rel="noopener">${esc(f.label)}</a>`).join(' ');
      const pdf = r.pdf_url ? `<a class="pill pill-info" href="${esc(r.pdf_url)}" target="_blank" rel="noopener">Request ORR PDF</a>` : '';
      const lastUpd = (r.updates || []).slice(-1)[0];
      return `<div class="card" data-req="${esc(r.id)}">
        <div class="pill-row" style="justify-content:space-between">
          <div class="pill-row">
            <code>${esc(r.id)}</code>
            <span class="pill ${pillClass(r.status)}">${esc(r.status)}</span>
            <span class="pill">${pubVis}</span>
          </div>
          <span class="muted">${esc(fmtDate(r.created_at))}</span>
        </div>
        <h3>${esc(r.recipient_name || r.agency || 'Agency')}</h3>
        <div class="body-pre">${esc(r.description)}</div>
        ${lastUpd ? `<p class="muted"><strong>Latest update (${esc(fmtDate(lastUpd.date))}):</strong> ${esc(lastUpd.note)}</p>` : ''}
        <div class="pill-row">${pdf} ${files}</div>
        <div class="action-row">
          ${r.status === 'pending_review' ? `<button class="btn btn-ok btn-sm" data-act="approve" data-id="${esc(r.id)}">Approve &amp; Generate ORR PDF</button>` : ''}
          <button class="btn btn-sm" data-act="status" data-st="sent" data-id="${esc(r.id)}">Mark Sent</button>
          <button class="btn btn-ok btn-sm" data-act="status" data-st="fulfilled" data-id="${esc(r.id)}">Mark Fulfilled</button>
          <button class="btn btn-sm" data-act="status" data-st="partial_response" data-id="${esc(r.id)}">Mark Partial</button>
          <button class="btn btn-danger btn-sm" data-act="status" data-st="rejected" data-id="${esc(r.id)}">Reject</button>
          <button class="btn btn-sm" data-act="reply-req" data-to="${esc(r.recipient_email || '')}" data-id="${esc(r.id)}">Email Agency</button>
        </div>
      </div>`;
    }).join('') || '<p class="muted">No matching records requests.</p>';
  }

  function renderMail() {
    const mf = $('mail-filter').value;
    const q = $('mail-search').value.trim().toLowerCase();
    const em = model.emails || { threads: {}, unmatched: [] };
    const entries = [];
    if (!mf || mf === 'unmatched') {
      for (const m of (em.unmatched || [])) {
        const subj = String(m.subject || '');
        if (/timing |post-tune|reliability |probe-|fullaudit|audit-1785|verify-run|pdfcheck|mail delivery failed|delay in message|receive test|test receiving|post-maintenance|deploy-test|submission pipeline test|vps-inbound|inbound delivery probe|undelivered mail/i.test(subj)) continue;
        entries.push({ ...m, group: 'unmatched' });
      }
    }
    if (!mf || mf === 'threads') {
      for (const [tid, msgs] of Object.entries(em.threads || {})) {
        for (const m of msgs) entries.push({ ...m, group: 'threads', thread_id: tid });
      }
    }
    entries.sort((a, b) => new Date(b.date || b.fetched_at || 0) - new Date(a.date || a.fetched_at || 0));
    const filtered = entries.filter(m => !q || (m.subject + ' ' + m.from + ' ' + m.to + ' ' + m.body).toLowerCase().includes(q));
    $('mail-list').innerHTML = filtered.slice(0, 60).map(m => {
      const fromMatch = String(m.from || '').match(/<([^>]+)>/);
      const replyAddr = fromMatch ? fromMatch[1] : (String(m.from || '').includes('@') ? String(m.from).trim() : '');
      return `<div class="card">
        <div class="pill-row" style="justify-content:space-between">
          <div class="pill-row">
            <span class="pill ${m.group === 'threads' ? 'pill-info' : 'pill-warn'}">${m.thread_id ? ('Req #' + esc(m.thread_id)) : esc(m.folder || 'INBOX')}</span>
            <strong>${esc(m.subject || '(no subject)')}</strong>
          </div>
          <span class="muted">${esc(m.date || fmtDate(m.fetched_at))}</span>
        </div>
        <p class="muted" style="margin:.35rem 0"><strong>From:</strong> ${esc(m.from)} &nbsp;&middot;&nbsp; <strong>To:</strong> ${esc(m.to || 'foia@moveweight.com')}</p>
        <div class="body-pre">${esc((m.body || '').slice(0, 1500))}</div>
        <div class="action-row">
          <button class="btn btn-primary btn-sm" data-act="reply-mail" data-to="${esc(replyAddr)}" data-subj="Re: ${esc(m.subject || '')}" data-id="${esc(m.thread_id || '')}">Reply via foia@moveweight.com</button>
        </div>
      </div>`;
    }).join('') || '<p class="muted">No matching emails.</p>';
  }

  function renderTriage() {
    const kf = $('kind-filter').value;
    const rf = $('review-filter').value;
    const rows = (model.items || []).filter(it => (!kf || it.kind === kf) && (!rf || it.review?.status === rf));
    $('triage-list').innerHTML = rows.slice(0, 60).map(it => `
      <div class="card">
        <div class="pill-row" style="justify-content:space-between">
          <div class="pill-row">
            <span class="pill pill-info">${esc(it.kind)}</span>
            <span class="pill">${esc(it.chapter)}</span>
            <span class="pill ${pillClass(it.review?.status)}">${esc(it.review?.status || 'new')}</span>
          </div>
          <span class="muted">${esc(fmtDate(it.created_at))}</span>
        </div>
        <h3>${esc(it.title)}</h3>
        <div class="body-pre">${esc((it.description || '').slice(0, 1000))}</div>
        <div class="action-row">
          <select class="triage-st" style="width:auto" data-id="${esc(it.id)}" data-ver="${esc(it.review?.version || 0)}">
            ${['new','in_review','needs_records','ready','closed'].map(s => `<option value="${s}" ${it.review?.status===s?'selected':''}>${s}</option>`).join('')}
          </select>
          <input class="triage-note" style="flex:1;min-width:220px" value="${esc(it.review?.notes || '')}" placeholder="Operator note&hellip;">
          <button class="btn btn-sm btn-ok" data-act="save-triage" data-id="${esc(it.id)}">Save</button>
        </div>
      </div>`).join('') || '<p class="muted">No items in triage filter.</p>';
  }

  async function load() {
    $('error-banner').classList.add('hidden');
    try {
      model = await api('/api/foia/admin/network?limit=120');
      $('login-view').classList.add('hidden');
      $('app').classList.remove('hidden');
      render();
    } catch (e) {
      if (e.message !== 'Unauthorized') toast(e.message, true);
    }
  }

  $('login-btn').addEventListener('click', () => {
    token = $('token-input').value.trim();
    if (!token) return;
    sessionStorage.setItem('expose_admin_token', token);
    $('login-error').classList.add('hidden');
    load();
  });
  $('logout-btn').addEventListener('click', () => lock());
  $('refresh-btn').addEventListener('click', load);
  $('compose-btn').addEventListener('click', () => openCompose());
  $('compose-close').addEventListener('click', () => $('compose-modal').classList.add('hidden'));
  $('sync-inbox-btn').addEventListener('click', async () => {
    try {
      const r = await api('/api/foia/admin/inbox/sync', { method: 'POST' });
      toast('Mailbox sync: ' + (r.output || 'done'));
      await load();
    } catch (e) { toast(e.message, true); }
  });
  $('cmp-send').addEventListener('click', async () => {
    const to = $('cmp-to').value.trim(), subject = $('cmp-subj').value.trim(), body = $('cmp-body').value.trim(), request_id = $('cmp-reqid').value.trim();
    if (!to || !body) { $('cmp-status').textContent = 'Recipient and message required.'; return; }
    $('cmp-status').textContent = 'Sending via foia@moveweight.com...';
    try {
      const r = await api('/api/foia/admin/inbox/reply', { method: 'POST', body: JSON.stringify({ to, subject, body, request_id }) });
      $('compose-modal').classList.add('hidden');
      toast('Email sent: ' + (r.output || to));
      await load();
    } catch (e) { $('cmp-status').textContent = 'Error: ' + e.message; }
  });

  document.querySelectorAll('.tab').forEach(b => b.addEventListener('click', () => switchTab(b.dataset.tab)));
  ['rec-status-filter', 'rec-search'].forEach(id => $(id).addEventListener('input', renderRecords));
  ['mail-filter', 'mail-search'].forEach(id => $(id).addEventListener('input', renderMail));
  ['kind-filter', 'review-filter'].forEach(id => $(id).addEventListener('change', renderTriage));

  document.addEventListener('click', async (ev) => {
    const btn = ev.target.closest('[data-act]');
    if (!btn) return;
    const act = btn.dataset.act, id = btn.dataset.id;
    try {
      if (act === 'approve') {
        const r = await api('/api/foia/admin/approve/' + encodeURIComponent(id), { method: 'POST' });
        toast('Approved ' + id + ' — ORR PDF ready: ' + (r.pdf_url || ''));
        await load();
      } else if (act === 'status') {
        const st = btn.dataset.st;
        const note = prompt('Update note for ' + id + ' -> ' + st + ':', 'Status updated to ' + st + ' via Command Center.');
        if (note === null) return;
        await api('/api/foia/admin/update-status/' + encodeURIComponent(id), { method: 'POST', body: JSON.stringify({ status: st, note }) });
        toast('Updated ' + id + ' -> ' + st);
        await load();
      } else if (act === 'reply-mail') {
        openCompose({ to: btn.dataset.to, subject: btn.dataset.subj, reqId: id });
      } else if (act === 'reply-req') {
        openCompose({ to: btn.dataset.to, subject: 'Open Records Request Follow-Up — ' + id, reqId: id });
      } else if (act === 'save-triage') {
        const card = btn.closest('.card');
        const sel = card.querySelector('.triage-st');
        const note = card.querySelector('.triage-note').value;
        await api('/api/foia/admin/review/' + encodeURIComponent(id), {
          method: 'POST',
          body: JSON.stringify({ status: sel.value, notes: note, expected_version: Number(sel.dataset.ver || 0) })
        });
        toast('Saved triage for ' + id);
        await load();
      }
    } catch (e) { toast(e.message, true); }
  });

  if (token) load();
})();
