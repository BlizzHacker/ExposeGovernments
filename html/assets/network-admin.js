(() => {
  'use strict';

  let token = '';
  let model = {chapters: [], items: [], errors: []};
  const $ = (id) => document.getElementById(id);

  function headers(json = false) {
    const value = {'Authorization': `Bearer ${token}`};
    if (json) value['Content-Type'] = 'application/json';
    return value;
  }

  async function api(path, options = {}) {
    const response = await fetch(path, {...options, headers: {...headers(Boolean(options.body)), ...(options.headers || {})}});
    let data;
    try { data = await response.json(); } catch (_) { data = {ok: false, error: `HTTP ${response.status}`}; }
    if (response.status === 401) lock('Your session is no longer authorized.');
    if (!response.ok) throw Object.assign(new Error(data.error || `HTTP ${response.status}`), {status: response.status});
    return data;
  }

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  }

  function statusValue(value) {
    return typeof value === 'string' ? value : value?.status || 'unknown';
  }

  function detailValue(value) {
    return typeof value === 'string' ? value : value?.detail || '';
  }

  function dateLabel(value) {
    if (!value) return 'Unknown time';
    const date = new Date(value);
    return Number.isNaN(date.valueOf()) ? String(value) : date.toLocaleString();
  }

  function ageDays(value) {
    const timestamp = new Date(value).valueOf();
    if (!Number.isFinite(timestamp)) return null;
    return Math.max(0, Math.floor((Date.now() - timestamp) / 86400000));
  }

  async function load() {
    $('app').classList.add('loading');
    $('error-banner').classList.add('hidden');
    try {
      model = await api('/api/foia/admin/network?limit=100');
      $('snapshot-time').textContent = model.generated_at ? `Collected ${dateLabel(model.generated_at)}` : 'Live queue; health snapshot pending';
      render();
      if (model.errors?.length) {
        $('error-banner').textContent = `Collector: ${model.errors.join(' ')}`;
        $('error-banner').classList.remove('hidden');
      }
    } catch (error) {
      $('error-banner').textContent = `Dashboard could not load: ${error.message}`;
      $('error-banner').classList.remove('hidden');
    } finally {
      $('app').classList.remove('loading');
    }
  }

  function render() {
    renderMetrics();
    renderChapters();
    fillChapterFilter();
    renderQueue();
  }

  function renderMetrics() {
    const reviews = model.items.map((item) => item.review?.status || 'new');
    const pending = model.items.filter((item) => item.kind === 'foia' && item.status === 'pending_review').length;
    const prepared = model.items.filter((item) => item.kind === 'foia' && item.status === 'prepared_for_delivery').length;
    const unhealthy = model.chapters.filter((chapter) => !['ok', 'healthy'].includes(statusValue(chapter.health))).length;
    const values = [
      [model.items.length, 'Loaded queue items'],
      [reviews.filter((value) => value === 'new').length, 'Unreviewed'],
      [pending, 'Requests awaiting review'],
      [prepared, 'Prepared, needs delivery'],
      [unhealthy, 'Sites needing attention'],
    ];
    $('metrics').replaceChildren(...values.map(([number, label]) => {
      const card = el('article', 'metric');
      card.append(el('strong', '', number), el('span', '', label));
      return card;
    }));
  }

  function renderChapters() {
    const cards = model.chapters.map((chapter) => {
      const card = el('article', 'chapter');
      const top = el('div', 'chapter-top');
      const title = el('h3');
      const link = el('a', '', chapter.label);
      link.href = `https://${chapter.host}`;
      link.target = '_blank';
      link.rel = 'noopener';
      title.append(link);
      const health = statusValue(chapter.health);
      top.append(title, el('span', `status ${health}`, health));
      const requestInfo = chapter.requests || {};
      const detail = [detailValue(chapter.health), `${requestInfo.pending || 0} pending of ${requestInfo.total || 0} requests`].filter(Boolean).join(' | ');
      card.append(top, el('p', '', detail));
      return card;
    });
    $('chapters').replaceChildren(...cards);
  }

  function fillChapterFilter() {
    const select = $('chapter-filter');
    if (select.options.length > 1) return;
    for (const chapter of model.chapters) {
      const option = el('option', '', chapter.label);
      option.value = chapter.key;
      select.append(option);
    }
  }

  function matchesFilters(item) {
    return (!$('chapter-filter').value || item.chapter === $('chapter-filter').value)
      && (!$('kind-filter').value || item.kind === $('kind-filter').value)
      && (!$('review-filter').value || (item.review?.status || 'new') === $('review-filter').value);
  }

  function renderQueue() {
    const items = model.items.filter(matchesFilters);
    $('queue-empty').classList.toggle('hidden', items.length !== 0);
    $('queue').replaceChildren(...items.map(renderItem));
  }

  function renderItem(item) {
    const card = el('article', 'queue-item');
    const content = el('div');
    const meta = el('div', 'item-meta');
    meta.append(el('b', '', item.chapter), el('span', '', item.kind), el('span', '', item.status), el('span', '', dateLabel(item.created_at)));
    const days = ageDays(item.created_at);
    if (days !== null) meta.append(el('span', '', `${days} day${days === 1 ? '' : 's'} old`));
    content.append(meta, el('h3', '', item.title || 'Untitled item'), el('p', 'description', item.description || 'No description supplied.'));

    const actions = el('div', 'pdf-actions');
    if (item.pdf_url) {
      const pdf = el('a', '', 'Open prepared PDF');
      pdf.href = item.pdf_url;
      pdf.target = '_blank';
      actions.append(pdf);
    }
    if (item.kind === 'foia' && item.status === 'pending_review') {
      const prepare = el('button', 'secondary', 'Approve and prepare PDF');
      prepare.type = 'button';
      prepare.addEventListener('click', () => prepareRequest(item, prepare));
      actions.append(prepare);
    }
    if (item.kind === 'foia' && item.status === 'prepared_for_delivery') {
      const delivered = el('button', 'secondary', 'Record delivery');
      delivered.type = 'button';
      delivered.addEventListener('click', () => recordDelivery(item, delivered));
      actions.append(delivered);
    }
    if (actions.childNodes.length) content.append(actions);

    const review = el('form', 'review');
    const status = el('select');
    for (const value of ['new', 'in_review', 'needs_records', 'ready', 'closed']) {
      const option = el('option', '', value.replaceAll('_', ' '));
      option.value = value;
      option.selected = value === (item.review?.status || 'new');
      status.append(option);
    }
    const statusLabel = el('label', '', 'Review state');
    statusLabel.append(status);
    const notes = el('textarea');
    notes.maxLength = 4000;
    notes.placeholder = 'Private sourcing notes, next records needed, or disposition';
    notes.value = item.review?.notes || '';
    const notesLabel = el('label', '', 'Private notes');
    notesLabel.append(notes);
    const reviewActions = el('div', 'review-actions');
    const save = el('button', '', 'Save review');
    save.type = 'submit';
    const state = el('span', 'save-state', item.review?.updated_at ? `Saved ${dateLabel(item.review.updated_at)}` : 'Not reviewed');
    reviewActions.append(save, state);
    review.append(statusLabel, notesLabel, reviewActions);
    review.addEventListener('submit', (event) => saveReview(event, item, status, notes, save, state));
    card.append(content, review);
    return card;
  }

  async function saveReview(event, item, status, notes, button, state) {
    event.preventDefault();
    button.disabled = true;
    state.textContent = 'Saving...';
    try {
      const data = await api(`/api/foia/admin/review/${encodeURIComponent(item.id)}`, {
        method: 'POST',
        body: JSON.stringify({status: status.value, notes: notes.value, expected_version: item.review?.version || 0}),
      });
      item.review = data.review;
      state.textContent = `Saved ${dateLabel(data.review.updated_at)}`;
      renderMetrics();
    } catch (error) {
      state.textContent = error.status === 409 ? 'Changed elsewhere. Refresh before saving.' : `Save failed: ${error.message}`;
    } finally { button.disabled = false; }
  }

  async function prepareRequest(item, button) {
    if (!window.confirm('Approve this request and generate its delivery PDF? This does not record delivery.')) return;
    button.disabled = true;
    try {
      await api(`/api/foia/admin/approve/${encodeURIComponent(item.source_id)}`, {method: 'POST', body: '{}'});
      await load();
    } catch (error) { window.alert(`Could not prepare request: ${error.message}`); }
    finally { button.disabled = false; }
  }

  async function recordDelivery(item, button) {
    const note = window.prompt('How and when was this delivered? Include enough detail to audit the status.');
    if (!note) return;
    button.disabled = true;
    try {
      await api(`/api/foia/admin/mark-delivered/${encodeURIComponent(item.source_id)}`, {method: 'POST', body: JSON.stringify({delivery_note: note})});
      await load();
    } catch (error) { window.alert(`Could not record delivery: ${error.message}`); }
    finally { button.disabled = false; }
  }

  function lock(message = '') {
    token = '';
    model = {chapters: [], items: [], errors: []};
    $('app').classList.add('hidden');
    $('login').classList.remove('hidden');
    $('token').value = '';
    $('queue').replaceChildren();
    $('chapters').replaceChildren();
    $('metrics').replaceChildren();
    $('login-error').textContent = message;
  }

  $('login-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    $('login-error').textContent = '';
    token = $('token').value.trim();
    try {
      await api('/api/foia/admin/pending');
      $('token').value = '';
      $('login').classList.add('hidden');
      $('app').classList.remove('hidden');
      await load();
    } catch (error) {
      token = '';
      $('login-error').textContent = error.status === 401 ? 'That token was not accepted.' : `Login failed: ${error.message}`;
    }
  });
  $('logout').addEventListener('click', () => lock());
  $('refresh').addEventListener('click', load);
  for (const id of ['chapter-filter', 'kind-filter', 'review-filter']) $(id).addEventListener('change', renderQueue);
})();
