const API = '';
const MP_LABELS = {
  wildberries: 'Wildberries',
  ozon: 'Ozon',
  yandex_market: 'Яндекс Маркет',
  aliexpress: 'AliExpress',
};
const CURRENCY = { aliexpress: '$', wildberries: '₽', ozon: '₽', yandex_market: '₽' };

let products = [];
let modalChart = null;

// ── Startup ────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', loadProducts);

// ── API helpers ────────────────────────────────────────────────────────────
async function apiFetch(path, opts = {}) {
  const res = await fetch(API + path, {
    headers: { 'Content-Type': 'application/json' },
    ...opts,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

// ── Load products ──────────────────────────────────────────────────────────
async function loadProducts() {
  document.getElementById('loadingState').style.display = 'flex';
  document.getElementById('productsGrid').innerHTML = '';
  try {
    products = await apiFetch('/api/products');
    renderProducts();
    updateLastUpdated();
  } catch (e) {
    showToast('Ошибка загрузки: ' + e.message, 'error');
  } finally {
    document.getElementById('loadingState').style.display = 'none';
  }
}

function updateLastUpdated() {
  document.getElementById('lastUpdated').textContent =
    'Обновлено ' + new Date().toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
}

// ── Render ─────────────────────────────────────────────────────────────────
function renderProducts() {
  const grid = document.getElementById('productsGrid');
  const empty = document.getElementById('emptyState');
  const count = document.getElementById('productCount');

  grid.innerHTML = '';
  count.textContent = products.length + ' ' + plural(products.length, 'товар', 'товара', 'товаров');

  if (products.length === 0) {
    empty.style.display = 'flex';
    return;
  }
  empty.style.display = 'none';
  products.forEach(p => grid.appendChild(createCard(p)));
}

function createCard(p) {
  const cur = CURRENCY[p.marketplace] || '₽';
  const history = p.price_history || [];
  const firstPrice = history.length > 1 ? history[0].price : null;
  const change = firstPrice && p.current_price ? p.current_price - firstPrice : null;
  const changePct = change !== null ? (change / firstPrice) * 100 : null;

  const card = document.createElement('div');
  card.className = 'product-card';
  card.dataset.id = p.id;

  // image
  const imgWrap = document.createElement('div');
  imgWrap.className = 'product-img-wrap';
  imgWrap.onclick = () => showChart(p.id);

  const badge = document.createElement('span');
  badge.className = `marketplace-badge badge-${p.marketplace}`;
  badge.textContent = MP_LABELS[p.marketplace] || p.marketplace;
  imgWrap.appendChild(badge);

  if (p.image_url) {
    const img = document.createElement('img');
    img.className = 'product-img';
    img.src = p.image_url;
    img.alt = p.name || '';
    img.onerror = () => { imgWrap.innerHTML = ''; imgWrap.appendChild(badge); imgWrap.appendChild(placeholder()); };
    imgWrap.appendChild(img);
  } else {
    imgWrap.appendChild(placeholder());
  }

  // body
  const body = document.createElement('div');
  body.className = 'product-body';

  // name
  const nameEl = document.createElement('p');
  nameEl.className = 'product-name';
  if (p.product_url) {
    nameEl.innerHTML = `<a href="${p.product_url}" target="_blank" rel="noopener">${esc(p.name || 'Артикул ' + p.article)}</a>`;
  } else {
    nameEl.textContent = p.name || 'Артикул ' + p.article;
  }

  // price row
  const priceRow = document.createElement('div');
  priceRow.className = 'price-row';

  const priceEl = document.createElement('span');
  priceEl.className = 'price-current';
  priceEl.textContent = p.current_price ? formatPrice(p.current_price, cur) : '—';

  const changeEl = document.createElement('span');
  if (change !== null) {
    changeEl.className = 'price-change ' + (change < 0 ? 'down' : change > 0 ? 'up' : 'flat');
    const sign = change > 0 ? '+' : '';
    changeEl.textContent = `${sign}${changePct.toFixed(1)}% (${sign}${formatPrice(change, cur)})`;
  } else {
    changeEl.className = 'price-change flat';
    changeEl.textContent = history.length <= 1 ? 'только добавлен' : '';
  }

  priceRow.appendChild(priceEl);
  priceRow.appendChild(changeEl);

  // sparkline
  const sparkWrap = document.createElement('div');
  sparkWrap.className = 'sparkline-wrap';
  sparkWrap.onclick = () => showChart(p.id);
  const sparkCanvas = document.createElement('canvas');
  sparkWrap.appendChild(sparkCanvas);

  // meta
  const meta = document.createElement('div');
  meta.className = 'product-meta';

  const artSpan = document.createElement('span');
  artSpan.textContent = 'Арт. ' + p.article;

  const threshWrap = document.createElement('span');
  threshWrap.className = 'threshold-inline';
  threshWrap.innerHTML = '🔔 ';
  const threshInput = document.createElement('input');
  threshInput.type = 'number';
  threshInput.className = 'threshold-input';
  threshInput.value = p.alert_threshold;
  threshInput.min = 0.1;
  threshInput.step = 0.1;
  threshInput.title = 'Порог уведомления %';
  threshInput.onchange = () => updateThreshold(p.id, parseFloat(threshInput.value));
  threshWrap.appendChild(threshInput);
  threshWrap.appendChild(document.createTextNode('%'));

  meta.appendChild(artSpan);
  meta.appendChild(threshWrap);

  // footer
  const footer = document.createElement('div');
  footer.className = 'product-footer';

  const histBtn = document.createElement('button');
  histBtn.className = 'btn-history';
  histBtn.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg> История цен`;
  histBtn.onclick = () => showChart(p.id);

  const delBtn = document.createElement('button');
  delBtn.className = 'btn btn-danger';
  delBtn.title = 'Удалить';
  delBtn.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14H6L5 6"/><path d="M10 11v6M14 11v6"/><path d="M9 6V4h6v2"/></svg>`;
  delBtn.onclick = () => deleteProduct(p.id, p.name || p.article);

  footer.appendChild(histBtn);
  footer.appendChild(delBtn);

  body.appendChild(nameEl);
  body.appendChild(priceRow);
  body.appendChild(sparkWrap);
  body.appendChild(meta);

  card.appendChild(imgWrap);
  card.appendChild(body);
  card.appendChild(footer);

  // draw sparkline after DOM insert
  requestAnimationFrame(() => drawSparkline(sparkCanvas, history));

  return card;
}

function placeholder() {
  const div = document.createElement('div');
  div.className = 'product-img-placeholder';
  div.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="40" height="40"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18M9 21V9"/></svg>`;
  return div;
}

// ── Sparkline ──────────────────────────────────────────────────────────────
function drawSparkline(canvas, history) {
  if (!history || history.length < 2) {
    const ctx = canvas.getContext('2d');
    canvas.width = canvas.offsetWidth || 260;
    canvas.height = 48;
    ctx.fillStyle = 'rgba(108,99,255,0.08)';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.font = '11px sans-serif';
    ctx.fillStyle = '#7b82a0';
    ctx.textAlign = 'center';
    ctx.fillText('Недостаточно данных', canvas.width / 2, 28);
    return;
  }

  const prices = history.map(h => h.price);
  const labels = history.map(h => new Date(h.recorded_at).toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit' }));
  const color = prices[prices.length - 1] <= prices[0] ? '#22c55e' : '#ef4444';

  if (canvas._chart) canvas._chart.destroy();
  canvas._chart = new Chart(canvas, {
    type: 'line',
    data: {
      labels,
      datasets: [{
        data: prices,
        borderColor: color,
        borderWidth: 2,
        pointRadius: 0,
        fill: true,
        backgroundColor: color + '20',
        tension: 0.35,
      }],
    },
    options: {
      responsive: false,
      animation: false,
      plugins: { legend: { display: false }, tooltip: { enabled: false } },
      scales: { x: { display: false }, y: { display: false } },
    },
  });
}

// ── Add product ────────────────────────────────────────────────────────────
async function addProduct(e) {
  e.preventDefault();
  const btn = document.getElementById('addBtn');
  const errEl = document.getElementById('formError');
  const marketplace = document.getElementById('marketplace').value;
  const article = document.getElementById('article').value.trim();
  const threshold = parseFloat(document.getElementById('threshold').value) || 5;

  errEl.textContent = '';
  btn.disabled = true;
  btn.textContent = 'Загрузка...';

  try {
    const product = await apiFetch('/api/products', {
      method: 'POST',
      body: JSON.stringify({ marketplace, article, alert_threshold: threshold }),
    });
    products.unshift(product);
    renderProducts();
    document.getElementById('addForm').reset();
    showToast('Товар добавлен: ' + (product.name || article), 'success');
  } catch (err) {
    errEl.textContent = err.message;
  } finally {
    btn.disabled = false;
    btn.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" width="16" height="16"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg> Добавить`;
  }
}

// ── Delete product ─────────────────────────────────────────────────────────
async function deleteProduct(id, name) {
  if (!confirm(`Удалить «${name}»?`)) return;
  try {
    await apiFetch(`/api/products/${id}`, { method: 'DELETE' });
    products = products.filter(p => p.id !== id);
    renderProducts();
    showToast('Товар удалён', 'success');
  } catch (err) {
    showToast('Ошибка удаления: ' + err.message, 'error');
  }
}

// ── Update threshold ───────────────────────────────────────────────────────
async function updateThreshold(id, value) {
  try {
    const updated = await apiFetch(`/api/products/${id}`, {
      method: 'PATCH',
      body: JSON.stringify({ alert_threshold: value }),
    });
    const idx = products.findIndex(p => p.id === id);
    if (idx !== -1) products[idx] = updated;
    showToast('Порог обновлён', 'success');
  } catch (err) {
    showToast('Ошибка: ' + err.message, 'error');
  }
}

// ── Manual refresh ─────────────────────────────────────────────────────────
async function manualRefresh() {
  const btn = document.getElementById('refreshBtn');
  btn.disabled = true;
  btn.textContent = 'Обновление...';
  try {
    await apiFetch('/api/refresh', { method: 'POST' });
    showToast('Обновление запущено, подождите...', 'success');
    setTimeout(loadProducts, 5000);
  } catch (err) {
    showToast('Ошибка: ' + err.message, 'error');
  } finally {
    btn.disabled = false;
    btn.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg> Обновить цены`;
  }
}

// ── Chart modal ────────────────────────────────────────────────────────────
function showChart(id) {
  const p = products.find(pr => pr.id === id);
  if (!p) return;
  const cur = CURRENCY[p.marketplace] || '₽';
  const history = p.price_history || [];

  document.getElementById('modalTitle').textContent = p.name || ('Артикул ' + p.article);
  document.getElementById('modalSubtitle').textContent = MP_LABELS[p.marketplace] + ' · ' + history.length + ' точек';

  // stats
  const statsEl = document.getElementById('modalStats');
  if (history.length > 0) {
    const prices = history.map(h => h.price);
    const min = Math.min(...prices);
    const max = Math.max(...prices);
    const first = prices[0];
    const last = prices[prices.length - 1];
    const diff = last - first;
    const diffPct = first ? ((diff / first) * 100).toFixed(1) : '0';
    const sign = diff > 0 ? '+' : '';
    statsEl.innerHTML = `
      <div class="stat-item"><span class="stat-label">Текущая</span><span class="stat-value">${formatPrice(last, cur)}</span></div>
      <div class="stat-item"><span class="stat-label">Минимум</span><span class="stat-value" style="color:var(--green)">${formatPrice(min, cur)}</span></div>
      <div class="stat-item"><span class="stat-label">Максимум</span><span class="stat-value" style="color:var(--red)">${formatPrice(max, cur)}</span></div>
      <div class="stat-item"><span class="stat-label">Изменение</span><span class="stat-value" style="color:${diff <= 0 ? 'var(--green)' : 'var(--red)'}">${sign}${diffPct}%</span></div>
    `;
  } else {
    statsEl.innerHTML = '';
  }

  // chart
  const canvas = document.getElementById('modalChart');
  if (modalChart) { modalChart.destroy(); modalChart = null; }

  if (history.length >= 2) {
    const labels = history.map(h => new Date(h.recorded_at).toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }));
    const prices = history.map(h => h.price);
    const color = prices[prices.length - 1] <= prices[0] ? '#22c55e' : '#ef4444';

    modalChart = new Chart(canvas, {
      type: 'line',
      data: {
        labels,
        datasets: [{
          label: 'Цена',
          data: prices,
          borderColor: color,
          borderWidth: 2.5,
          pointRadius: 4,
          pointBackgroundColor: color,
          fill: true,
          backgroundColor: color + '18',
          tension: 0.3,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: ctx => ' ' + formatPrice(ctx.raw, cur),
            },
          },
        },
        scales: {
          x: {
            grid: { color: '#2e3148' },
            ticks: { color: '#7b82a0', maxTicksLimit: 8, font: { size: 11 } },
          },
          y: {
            grid: { color: '#2e3148' },
            ticks: { color: '#7b82a0', callback: v => formatPrice(v, cur), font: { size: 11 } },
          },
        },
      },
    });
  } else {
    const ctx = canvas.getContext('2d');
    canvas.width = canvas.offsetWidth;
    canvas.height = 260;
    ctx.fillStyle = '#1a1d27';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.font = '14px sans-serif';
    ctx.fillStyle = '#7b82a0';
    ctx.textAlign = 'center';
    ctx.fillText('Недостаточно данных для графика', canvas.width / 2, 140);
  }

  document.getElementById('modalOverlay').classList.add('open');
}

function closeModal(e) {
  if (e && e.target !== document.getElementById('modalOverlay') && e.type === 'click') return;
  document.getElementById('modalOverlay').classList.remove('open');
  if (modalChart) { modalChart.destroy(); modalChart = null; }
}

document.addEventListener('keydown', e => { if (e.key === 'Escape') closeModal(); });

// ── Toast ──────────────────────────────────────────────────────────────────
function showToast(msg, type = 'success') {
  const t = document.createElement('div');
  t.className = `toast toast-${type}`;
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 3500);
}

// ── Helpers ────────────────────────────────────────────────────────────────
function formatPrice(val, cur = '₽') {
  return new Intl.NumberFormat('ru-RU', { minimumFractionDigits: 0, maximumFractionDigits: 2 }).format(val) + ' ' + cur;
}

function esc(str) {
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function plural(n, one, few, many) {
  const mod10 = n % 10, mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return n + ' ' + one;
  if ([2, 3, 4].includes(mod10) && ![12, 13, 14].includes(mod100)) return n + ' ' + few;
  return n + ' ' + many;
}
