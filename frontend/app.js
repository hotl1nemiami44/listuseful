/* ==========================================================================
   Price Tracker — app.js
   Vanilla JS frontend for the FastAPI price tracking backend.
   ========================================================================== */

const API = '';  // same-origin; change to 'http://localhost:8000' for dev

const MP_LABELS = {
  wildberries:  'Wildberries',
  ozon:         'Ozon',
  yandex_market:'Яндекс Маркет',
  aliexpress:   'AliExpress',
};

// Currency symbol per marketplace
const CURRENCY = {
  wildberries:   '₽',
  ozon:          '₽',
  yandex_market: '₽',
  aliexpress:    '$',
};

// Chart.js grid/tick colour for dark theme
const GRID_COLOR  = '#2a2f45';
const TICK_COLOR  = '#555e7a';

let products  = [];   // in-memory product list
let modalChart = null; // Chart.js instance in the modal

// ── Bootstrap ──────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  loadProducts();
});

// ── Keyboard shortcut: Escape closes modal ─────────────────────────────────
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') closeModal();
});

// ── API helper ─────────────────────────────────────────────────────────────
async function apiFetch(path, opts = {}) {
  const res = await fetch(API + path, {
    headers: { 'Content-Type': 'application/json' },
    ...opts,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

// ── loadProducts ───────────────────────────────────────────────────────────
// Fetches the full product list from the API and re-renders the grid.
async function loadProducts() {
  const loadingEl = document.getElementById('loadingState');
  const gridEl    = document.getElementById('productsGrid');

  loadingEl.style.display = 'flex';
  gridEl.innerHTML = '';

  try {
    products = await apiFetch('/api/products');
    renderProducts();
    updateTimestamp();
  } catch (err) {
    showToast('Ошибка загрузки: ' + err.message, 'error');
  } finally {
    loadingEl.style.display = 'none';
  }
}

// Update the "last updated" label in the header
function updateTimestamp() {
  const el = document.getElementById('lastUpdated');
  if (el) {
    el.textContent = 'Обновлено в ' +
      new Date().toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
  }
}

// ── renderProducts ─────────────────────────────────────────────────────────
// Clears and re-populates the products grid from the in-memory `products` array.
function renderProducts() {
  const grid  = document.getElementById('productsGrid');
  const empty = document.getElementById('emptyState');
  const count = document.getElementById('productCount');

  grid.innerHTML = '';
  count.textContent = plural(products.length, 'товар', 'товара', 'товаров');

  if (products.length === 0) {
    empty.style.display = 'flex';
    return;
  }

  empty.style.display = 'none';
  products.forEach(p => grid.appendChild(renderProduct(p)));
}

// ── renderProduct ──────────────────────────────────────────────────────────
// Builds and returns a single product card DOM element.
function renderProduct(p) {
  const cur     = CURRENCY[p.marketplace] || '₽';
  const history = p.price_history || [];

  // Price change is calculated from the FIRST recorded price vs. current
  const firstPrice = history.length > 0 ? history[0].price : null;
  const change     = (firstPrice != null && p.current_price != null)
    ? p.current_price - firstPrice
    : null;
  const changePct  = (change !== null && firstPrice)
    ? (change / firstPrice) * 100
    : null;

  // ── Card root ────────────────────────────────────────────────────────────
  const card = document.createElement('div');
  card.className  = 'product-card';
  card.dataset.id = p.id;

  // ── Image area ───────────────────────────────────────────────────────────
  const imgWrap = document.createElement('div');
  imgWrap.className = 'product-img-wrap';
  imgWrap.title     = 'Нажмите, чтобы просмотреть историю цен';
  imgWrap.addEventListener('click', () => showChart(p.id));

  // Marketplace badge (overlaid on image)
  const badge = document.createElement('span');
  badge.className   = `marketplace-badge badge-${p.marketplace}`;
  badge.textContent = MP_LABELS[p.marketplace] || p.marketplace;
  imgWrap.appendChild(badge);

  if (p.image_url) {
    const img = document.createElement('img');
    img.className = 'product-img';
    img.src       = p.image_url;
    img.alt       = p.name || '';
    img.loading   = 'lazy';
    img.onerror   = () => {
      imgWrap.innerHTML = '';
      imgWrap.appendChild(badge);
      imgWrap.appendChild(makePlaceholderImage());
    };
    imgWrap.appendChild(img);
  } else {
    imgWrap.appendChild(makePlaceholderImage());
  }

  // ── Card body ────────────────────────────────────────────────────────────
  const body = document.createElement('div');
  body.className = 'product-body';

  // Product name (optionally linked)
  const nameEl = document.createElement('p');
  nameEl.className = 'product-name';
  const displayName = esc(p.name || 'Артикул ' + p.article);
  if (p.product_url) {
    nameEl.innerHTML = `<a href="${p.product_url}" target="_blank" rel="noopener noreferrer">${displayName}</a>`;
  } else {
    nameEl.innerHTML = displayName;
  }

  // Price row: current price + change badge
  const priceRow = document.createElement('div');
  priceRow.className = 'price-row';

  const priceEl = document.createElement('span');
  priceEl.className = 'price-current';
  priceEl.textContent = p.current_price != null ? formatPrice(p.current_price, cur) : '—';

  const changeEl = buildPriceChangeBadge(change, changePct, cur, history.length);

  priceRow.appendChild(priceEl);
  priceRow.appendChild(changeEl);

  // Sparkline (inline mini chart)
  const sparkWrap = document.createElement('div');
  sparkWrap.className = 'sparkline-wrap';
  sparkWrap.title     = 'Нажмите для полного графика';
  sparkWrap.addEventListener('click', () => showChart(p.id));

  const sparkCanvas = document.createElement('canvas');
  sparkWrap.appendChild(sparkCanvas);

  // Meta row: article + alert threshold input
  const meta = document.createElement('div');
  meta.className = 'product-meta';

  const artSpan = document.createElement('span');
  artSpan.textContent = 'Арт. ' + p.article;

  const threshWrap = document.createElement('span');
  threshWrap.className = 'threshold-inline';

  const bellIcon = document.createTextNode('🔔 ');
  const threshInput = document.createElement('input');
  threshInput.type      = 'number';
  threshInput.className = 'threshold-input';
  threshInput.value     = p.alert_threshold;
  threshInput.min       = 0.1;
  threshInput.step      = 0.1;
  threshInput.title     = 'Порог уведомления (%)';
  threshInput.addEventListener('change', () => {
    const val = parseFloat(threshInput.value);
    if (!isNaN(val) && val > 0) updateThreshold(p.id, val);
  });

  threshWrap.appendChild(bellIcon);
  threshWrap.appendChild(threshInput);
  threshWrap.appendChild(document.createTextNode('%'));

  meta.appendChild(artSpan);
  meta.appendChild(threshWrap);

  body.appendChild(nameEl);
  body.appendChild(priceRow);
  body.appendChild(sparkWrap);
  body.appendChild(meta);

  // ── Card footer ──────────────────────────────────────────────────────────
  const footer = document.createElement('div');
  footer.className = 'product-footer';

  const histBtn = document.createElement('button');
  histBtn.className = 'btn-history';
  histBtn.innerHTML = `
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
      <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>
    </svg>
    История цен`;
  histBtn.addEventListener('click', () => showChart(p.id));

  const delBtn = document.createElement('button');
  delBtn.className = 'btn btn-danger';
  delBtn.title     = 'Удалить товар';
  delBtn.innerHTML = `
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
      <polyline points="3 6 5 6 21 6"/>
      <path d="M19 6l-1 14H6L5 6"/>
      <path d="M10 11v6M14 11v6M9 6V4h6v2"/>
    </svg>
    Удалить`;
  delBtn.addEventListener('click', () => deleteProduct(p.id, p.name || p.article));

  footer.appendChild(histBtn);
  footer.appendChild(delBtn);

  card.appendChild(imgWrap);
  card.appendChild(body);
  card.appendChild(footer);

  // Render sparkline asynchronously after the element is in the DOM
  requestAnimationFrame(() => createSparkline(sparkCanvas, history));

  return card;
}

// Helper: build the coloured price-change badge element
function buildPriceChangeBadge(change, changePct, cur, historyLen) {
  const el = document.createElement('span');

  if (change !== null && changePct !== null) {
    const dir  = change < 0 ? 'down' : change > 0 ? 'up' : 'flat';
    const sign = change > 0 ? '+' : '';
    el.className = `price-change ${dir}`;

    // Show absolute change + percentage
    const absStr = formatPrice(Math.abs(change), cur);
    const pctStr = Math.abs(changePct).toFixed(1) + '%';

    if (change < 0) {
      el.textContent = `↓ −${pctStr} (−${absStr})`;
    } else if (change > 0) {
      el.textContent = `↑ +${pctStr} (+${absStr})`;
    } else {
      el.textContent = '= без изменений';
    }
  } else {
    el.className  = 'price-change flat';
    el.textContent = historyLen <= 1 ? 'только добавлен' : '';
  }

  return el;
}

// Helper: placeholder image when there is no product image
function makePlaceholderImage() {
  const div = document.createElement('div');
  div.className = 'product-img-placeholder';
  div.innerHTML = `
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="42" height="42">
      <rect x="3" y="3" width="18" height="18" rx="2"/>
      <path d="M3 9h18M9 21V9"/>
    </svg>`;
  return div;
}

// ── createSparkline ────────────────────────────────────────────────────────
// Draws an inline sparkline chart using Chart.js onto the given canvas.
function createSparkline(canvas, history) {
  // Destroy a previous chart instance if one exists on this canvas
  if (canvas._sparkChart) {
    canvas._sparkChart.destroy();
    canvas._sparkChart = null;
  }

  if (!history || history.length < 2) {
    // Draw a "no data" placeholder manually
    const w = canvas.offsetWidth || 280;
    const h = 50;
    canvas.width  = w;
    canvas.height = h;
    const ctx = canvas.getContext('2d');
    ctx.fillStyle = 'rgba(92,110,245,0.07)';
    ctx.fillRect(0, 0, w, h);
    ctx.font      = '11px sans-serif';
    ctx.fillStyle = '#555e7a';
    ctx.textAlign = 'center';
    ctx.fillText('Недостаточно данных', w / 2, h / 2 + 4);
    return;
  }

  const prices = history.map(h => h.price);
  const labels = history.map(h =>
    new Date(h.recorded_at).toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit' })
  );
  const latest = prices[prices.length - 1];
  const first  = prices[0];
  const color  = latest <= first ? '#22c55e' : '#ef4444';

  canvas._sparkChart = new Chart(canvas, {
    type: 'line',
    data: {
      labels,
      datasets: [{
        data: prices,
        borderColor: color,
        borderWidth: 1.8,
        pointRadius: 0,
        fill: true,
        backgroundColor: color + '22',
        tension: 0.4,
      }],
    },
    options: {
      responsive: true,
      animation: false,
      plugins: {
        legend:  { display: false },
        tooltip: { enabled: false },
      },
      scales: {
        x: { display: false },
        y: { display: false },
      },
    },
  });
}

// ── addProduct ─────────────────────────────────────────────────────────────
// Handles the "Add product" form submission.
async function addProduct(e) {
  e.preventDefault();

  const btn        = document.getElementById('addBtn');
  const errEl      = document.getElementById('formError');
  const marketplace = document.getElementById('marketplace').value;
  const article    = document.getElementById('article').value.trim();
  const threshold  = parseFloat(document.getElementById('threshold').value) || 5;

  // Clear previous error
  errEl.textContent = '';
  errEl.classList.remove('visible');

  if (!marketplace || !article) {
    errEl.textContent = 'Выберите маркетплейс и введите артикул.';
    errEl.classList.add('visible');
    return;
  }

  btn.disabled = true;
  btn.textContent = 'Загрузка...';

  try {
    const product = await apiFetch('/api/products', {
      method: 'POST',
      body: JSON.stringify({ marketplace, article, alert_threshold: threshold }),
    });

    // Prepend to local list and re-render
    products.unshift(product);
    renderProducts();
    document.getElementById('addForm').reset();
    showToast('Добавлен: ' + (product.name || article), 'success');
  } catch (err) {
    errEl.textContent = err.message;
    errEl.classList.add('visible');
  } finally {
    btn.disabled = false;
    btn.innerHTML = `
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" width="16" height="16">
        <line x1="12" y1="5" x2="12" y2="19"/>
        <line x1="5" y1="12" x2="19" y2="12"/>
      </svg>
      Добавить`;
  }
}

// ── deleteProduct ──────────────────────────────────────────────────────────
// Asks for confirmation, then deletes the product via the API.
async function deleteProduct(id, name) {
  if (!confirm(`Удалить «${name}» из отслеживания?`)) return;

  try {
    await apiFetch(`/api/products/${id}`, { method: 'DELETE' });
    products = products.filter(p => p.id !== id);
    renderProducts();
    showToast('Товар удалён', 'success');
  } catch (err) {
    showToast('Ошибка удаления: ' + err.message, 'error');
  }
}

// ── updateThreshold ────────────────────────────────────────────────────────
// PATCHes the alert threshold for a product.
async function updateThreshold(id, value) {
  try {
    const updated = await apiFetch(`/api/products/${id}`, {
      method: 'PATCH',
      body: JSON.stringify({ alert_threshold: value }),
    });
    const idx = products.findIndex(p => p.id === id);
    if (idx !== -1) products[idx] = updated;
    showToast('Порог уведомления обновлён', 'success');
  } catch (err) {
    showToast('Ошибка: ' + err.message, 'error');
  }
}

// ── manualRefresh ──────────────────────────────────────────────────────────
// Triggers a background price-check on the server, then reloads.
async function manualRefresh() {
  const btn = document.getElementById('refreshBtn');
  btn.disabled = true;
  btn.classList.add('loading');
  btn.querySelector('span') && (btn.querySelector('span').textContent = 'Обновление...');

  try {
    await apiFetch('/api/refresh', { method: 'POST' });
    showToast('Обновление цен запущено — данные появятся через несколько секунд', 'info');
    // Give the server time to fetch prices, then reload
    setTimeout(loadProducts, 6000);
  } catch (err) {
    showToast('Ошибка запуска обновления: ' + err.message, 'error');
    btn.disabled = false;
    btn.classList.remove('loading');
  }
  // Button re-enabled after reload
}

// ── showChart ──────────────────────────────────────────────────────────────
// Opens the modal and renders a full price-history Chart.js chart.
function showChart(productId) {
  const p = products.find(pr => pr.id === productId);
  if (!p) return;

  const cur     = CURRENCY[p.marketplace] || '₽';
  const history = p.price_history || [];

  // Modal title / subtitle
  document.getElementById('modalTitle').textContent =
    p.name || 'Артикул ' + p.article;
  document.getElementById('modalSubtitle').textContent =
    (MP_LABELS[p.marketplace] || p.marketplace) +
    ' · ' + p.article +
    ' · ' + history.length + ' ' + plural(history.length, 'запись', 'записи', 'записей');

  // Stats strip
  const statsEl = document.getElementById('modalStats');
  statsEl.innerHTML = '';

  if (history.length > 0) {
    const prices  = history.map(h => h.price);
    const minP    = Math.min(...prices);
    const maxP    = Math.max(...prices);
    const first   = prices[0];
    const last    = prices[prices.length - 1];
    const diff    = last - first;
    const diffPct = first ? ((diff / first) * 100) : 0;
    const sign    = diff > 0 ? '+' : '';
    const diffColor = diff <= 0 ? 'var(--green)' : 'var(--red)';

    const stats = [
      { label: 'Текущая',   value: formatPrice(last, cur),  color: '' },
      { label: 'Минимум',   value: formatPrice(minP, cur),  color: 'var(--green)' },
      { label: 'Максимум',  value: formatPrice(maxP, cur),  color: 'var(--red)' },
      { label: 'Изменение', value: `${sign}${diffPct.toFixed(1)}%`, color: diffColor },
      { label: 'Записей',   value: String(history.length),  color: '' },
    ];

    stats.forEach(({ label, value, color }) => {
      const item = document.createElement('div');
      item.className = 'stat-item';
      item.innerHTML = `
        <span class="stat-label">${label}</span>
        <span class="stat-value" style="color:${color || 'var(--text)'}">${value}</span>`;
      statsEl.appendChild(item);
    });
  }

  // Destroy previous chart instance
  const canvas = document.getElementById('modalChart');
  if (modalChart) {
    modalChart.destroy();
    modalChart = null;
  }

  if (history.length >= 2) {
    const labels = history.map(h =>
      new Date(h.recorded_at).toLocaleString('ru-RU', {
        day: '2-digit', month: '2-digit',
        hour: '2-digit', minute: '2-digit',
      })
    );
    const prices  = history.map(h => h.price);
    const latest  = prices[prices.length - 1];
    const color   = latest <= prices[0] ? '#22c55e' : '#ef4444';

    modalChart = new Chart(canvas, {
      type: 'line',
      data: {
        labels,
        datasets: [{
          label: 'Цена',
          data: prices,
          borderColor: color,
          borderWidth: 2.5,
          pointRadius: prices.length <= 30 ? 4 : 2,
          pointHoverRadius: 6,
          pointBackgroundColor: color,
          fill: true,
          backgroundColor: color + '18',
          tension: 0.35,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: '#1e2235',
            borderColor: '#2a2f45',
            borderWidth: 1,
            titleColor: '#8892aa',
            bodyColor: '#e8ecf4',
            padding: 10,
            callbacks: {
              label: ctx => '  ' + formatPrice(ctx.raw, cur),
            },
          },
        },
        scales: {
          x: {
            grid: { color: GRID_COLOR },
            ticks: {
              color: TICK_COLOR,
              maxTicksLimit: 8,
              maxRotation: 30,
              font: { size: 11 },
            },
          },
          y: {
            grid: { color: GRID_COLOR },
            ticks: {
              color: TICK_COLOR,
              callback: v => formatPrice(v, cur),
              font: { size: 11 },
            },
          },
        },
      },
    });
  } else {
    // Not enough data: show a message on the canvas
    const w = canvas.offsetWidth || 640;
    const h = 260;
    canvas.width  = w;
    canvas.height = h;
    const ctx = canvas.getContext('2d');
    ctx.fillStyle = '#1e2235';
    ctx.fillRect(0, 0, w, h);
    ctx.font      = '15px sans-serif';
    ctx.fillStyle = '#555e7a';
    ctx.textAlign = 'center';
    ctx.fillText('Недостаточно данных для построения графика', w / 2, h / 2 + 5);
    ctx.font      = '12px sans-serif';
    ctx.fillStyle = '#3a3f5a';
    ctx.fillText('Добавьте хотя бы 2 записи о цене', w / 2, h / 2 + 26);
  }

  document.getElementById('modalOverlay').classList.add('open');
}

// ── closeModal ─────────────────────────────────────────────────────────────
function closeModal(e) {
  // If called from the overlay click handler, only close when clicking the backdrop
  if (e && e.type === 'click' && e.target !== document.getElementById('modalOverlay')) return;

  document.getElementById('modalOverlay').classList.remove('open');

  if (modalChart) {
    modalChart.destroy();
    modalChart = null;
  }
}

// ── showToast ──────────────────────────────────────────────────────────────
function showToast(message, type = 'success') {
  const icons = { success: '✓', error: '✕', info: 'ℹ' };
  const t = document.createElement('div');
  t.className   = `toast toast-${type}`;
  t.textContent = (icons[type] ? icons[type] + '  ' : '') + message;
  document.body.appendChild(t);

  // Auto-remove after 3.8 s
  setTimeout(() => {
    t.style.animation = 'none';
    t.style.opacity   = '0';
    t.style.transform = 'translateX(16px)';
    t.style.transition = 'opacity 0.2s, transform 0.2s';
    setTimeout(() => t.remove(), 200);
  }, 3800);
}

// ── Utility helpers ────────────────────────────────────────────────────────

/**
 * Format a price value with thousands separator + currency symbol.
 */
function formatPrice(val, cur = '₽') {
  if (val == null || isNaN(val)) return '—';
  return new Intl.NumberFormat('ru-RU', {
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
  }).format(val) + ' ' + cur;
}

/**
 * HTML-escape a string to prevent XSS when injecting into innerHTML.
 */
function esc(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/**
 * Russian plural helper.
 *   plural(1, 'товар', 'товара', 'товаров')  → '1 товар'
 *   plural(3, ...)  → '3 товара'
 *   plural(11, ...) → '11 товаров'
 */
function plural(n, one, few, many) {
  const mod10  = n % 10;
  const mod100 = n % 100;
  let word;
  if (mod10 === 1 && mod100 !== 11)                          word = one;
  else if ([2,3,4].includes(mod10) && ![12,13,14].includes(mod100)) word = few;
  else                                                        word = many;
  return n + ' ' + word;
}
