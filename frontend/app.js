const API = "";
let chatId = localStorage.getItem("chatId") || "";
let products = [];
let modalProductId = null;
let modalChart = null;

// ── Bootstrap ────────────────────────────────────────────────────────────────

function init() {
  if (!chatId) {
    show("setup-screen");
  } else {
    show("app-screen");
    loadProducts();
  }
  bindEvents();
}

function bindEvents() {
  document.getElementById("setup-form").addEventListener("submit", onSetupSubmit);
  document.getElementById("add-form").addEventListener("submit", addProduct);
  document.getElementById("refresh-btn").addEventListener("click", refreshAll);
  document.getElementById("settings-btn").addEventListener("click", openSettings);
  document.getElementById("modal-overlay").addEventListener("click", (e) => {
    if (e.target === e.currentTarget) closeModal();
  });
  document.getElementById("settings-overlay").addEventListener("click", (e) => {
    if (e.target === e.currentTarget) closeSettings();
  });
}

function show(id) {
  ["setup-screen", "app-screen"].forEach((s) => {
    document.getElementById(s).classList.toggle("hidden", s !== id);
  });
}

// ── Setup ─────────────────────────────────────────────────────────────────────

function onSetupSubmit(e) {
  e.preventDefault();
  const val = document.getElementById("chat-id-input").value.trim();
  if (!val) return;
  chatId = val;
  localStorage.setItem("chatId", chatId);
  show("app-screen");
  loadProducts();
}

// ── API Helpers ───────────────────────────────────────────────────────────────

function headers(extra = {}) {
  return { "Content-Type": "application/json", "x-chat-id": chatId, ...extra };
}

async function apiFetch(path, opts = {}) {
  const res = await fetch(API + path, {
    headers: headers(),
    ...opts,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || res.statusText);
  }
  if (res.status === 204) return null;
  return res.json();
}

// ── Load Products ─────────────────────────────────────────────────────────────

async function loadProducts() {
  setLoading(true);
  try {
    products = await apiFetch("/products");
    renderProducts();
  } catch (e) {
    showToast("Ошибка загрузки: " + e.message, "error");
  } finally {
    setLoading(false);
  }
}

function setLoading(on) {
  document.getElementById("loading-state").classList.toggle("hidden", !on);
  if (on) {
    document.getElementById("products-grid").innerHTML = "";
    document.getElementById("empty-state").classList.add("hidden");
    document.getElementById("stats-bar").classList.add("hidden");
  }
}

// ── Render ────────────────────────────────────────────────────────────────────

function renderProducts() {
  const grid = document.getElementById("products-grid");
  const empty = document.getElementById("empty-state");
  const statsBar = document.getElementById("stats-bar");

  grid.innerHTML = "";

  if (!products.length) {
    empty.classList.remove("hidden");
    statsBar.classList.add("hidden");
    return;
  }

  empty.classList.add("hidden");
  statsBar.classList.remove("hidden");

  const active = products.filter((p) => p.is_active).length;
  const dropped = products.filter((p) => {
    if (!p.history || p.history.length < 2) return false;
    return p.current_price < p.history[0].price;
  }).length;

  document.getElementById("stat-total").innerHTML =
    `Всего: <b>${products.length}</b>`;
  document.getElementById("stat-active").innerHTML =
    `Активных: <b>${active}</b>`;
  document.getElementById("stat-dropped").innerHTML =
    `Подешевело: <b>${dropped}</b>`;

  products.forEach((p) => grid.appendChild(renderProduct(p)));
}

function renderProduct(p) {
  const history = p.history || [];
  const firstPrice = history.length ? parseFloat(history[0].price) : null;
  const current = parseFloat(p.current_price);

  const card = document.createElement("div");
  card.className = "product-card" + (p.is_active ? "" : " inactive");
  card.dataset.id = p.id;

  // Image
  const imgWrap = document.createElement("div");
  imgWrap.className = "card-img-wrap";

  if (p.image_url) {
    const img = document.createElement("img");
    img.className = "card-img";
    img.src = p.image_url;
    img.alt = p.title;
    img.onerror = () => { imgWrap.style.background = "var(--bg3)"; img.remove(); };
    imgWrap.appendChild(img);
  }

  const badge = document.createElement("span");
  badge.className = `card-badge badge-${p.marketplace}`;
  badge.textContent = marketplaceLabel(p.marketplace);
  imgWrap.appendChild(badge);

  if (!p.is_active) {
    const inact = document.createElement("span");
    inact.className = "inactive-badge";
    inact.textContent = "Пауза";
    imgWrap.appendChild(inact);
  }

  // Body
  const body = document.createElement("div");
  body.className = "card-body";

  const title = document.createElement("div");
  title.className = "card-title";
  title.textContent = p.title;
  body.appendChild(title);

  const priceRow = document.createElement("div");
  priceRow.className = "card-price-row";

  const priceEl = document.createElement("span");
  priceEl.className = "card-price";
  priceEl.textContent = formatPrice(current);
  priceRow.appendChild(priceEl);

  if (firstPrice !== null && history.length > 1) {
    const diff = current - firstPrice;
    const pct = (diff / firstPrice) * 100;
    const chg = document.createElement("span");
    chg.className = "price-change " + (diff < 0 ? "down" : diff > 0 ? "up" : "same");
    chg.textContent =
      (diff < 0 ? "↓" : diff > 0 ? "↑" : "→") +
      " " + Math.abs(pct).toFixed(1) + "%";
    priceRow.appendChild(chg);
  }
  body.appendChild(priceRow);

  // Sparkline
  const sparkWrap = document.createElement("div");
  sparkWrap.className = "card-sparkline";
  const canvas = document.createElement("canvas");
  sparkWrap.appendChild(canvas);
  body.appendChild(sparkWrap);

  // Footer
  const footer = document.createElement("div");
  footer.className = "card-footer";

  const thresh = document.createElement("span");
  thresh.className = "card-threshold";
  thresh.textContent = `Порог: ${p.threshold_percent}%`;
  footer.appendChild(thresh);

  const actions = document.createElement("div");
  actions.className = "card-actions";

  const histBtn = document.createElement("button");
  histBtn.className = "card-btn";
  histBtn.textContent = "График";
  histBtn.addEventListener("click", (e) => { e.stopPropagation(); showChart(p.id); });
  actions.appendChild(histBtn);

  const toggleBtn = document.createElement("button");
  toggleBtn.className = "card-btn";
  toggleBtn.textContent = p.is_active ? "Пауза" : "Запустить";
  toggleBtn.addEventListener("click", (e) => { e.stopPropagation(); toggleActive(p.id, !p.is_active); });
  actions.appendChild(toggleBtn);

  const delBtn = document.createElement("button");
  delBtn.className = "card-btn danger";
  delBtn.textContent = "✕";
  delBtn.title = "Удалить";
  delBtn.addEventListener("click", (e) => { e.stopPropagation(); deleteProduct(p.id, p.title); });
  actions.appendChild(delBtn);

  footer.appendChild(actions);

  card.appendChild(imgWrap);
  card.appendChild(body);
  card.appendChild(footer);

  card.addEventListener("click", () => showChart(p.id));

  requestAnimationFrame(() => createSparkline(canvas, history));

  return card;
}

function marketplaceLabel(mp) {
  return { wb: "WB", ozon: "Ozon", ym: "Я.Маркет", ali: "Ali" }[mp] || mp;
}

function formatPrice(n) {
  if (n == null) return "—";
  return n.toLocaleString("ru-RU", { maximumFractionDigits: 2 }) + " ₽";
}

// ── Sparkline ─────────────────────────────────────────────────────────────────

function createSparkline(canvas, history) {
  if (!history || history.length < 2) {
    const ctx = canvas.getContext("2d");
    canvas.width = canvas.offsetWidth || 260;
    canvas.height = 44;
    ctx.strokeStyle = "var(--border)";
    ctx.setLineDash([4, 4]);
    ctx.beginPath();
    ctx.moveTo(0, 22);
    ctx.lineTo(canvas.width, 22);
    ctx.stroke();
    return;
  }

  const prices = history.map((h) => parseFloat(h.price));
  const first = prices[0];
  const last = prices[prices.length - 1];
  const color = last <= first ? "#4caf82" : "#e05c6a";

  new Chart(canvas, {
    type: "line",
    data: {
      labels: prices.map(() => ""),
      datasets: [{ data: prices, borderColor: color, borderWidth: 2,
        pointRadius: 0, tension: 0.3, fill: false }],
    },
    options: {
      responsive: false,
      animation: false,
      plugins: { legend: { display: false }, tooltip: { enabled: false } },
      scales: { x: { display: false }, y: { display: false } },
    },
  });
}

// ── Add Product ───────────────────────────────────────────────────────────────

async function addProduct(e) {
  e.preventDefault();
  const url = document.getElementById("url-input").value.trim();
  const threshold = parseFloat(document.getElementById("threshold-input").value) || 5;
  const errorEl = document.getElementById("add-error");
  const btn = document.getElementById("add-btn");

  errorEl.classList.add("hidden");
  btn.disabled = true;
  btn.textContent = "Добавляю...";

  try {
    const product = await apiFetch("/products", {
      method: "POST",
      body: JSON.stringify({ url, threshold_percent: threshold }),
    });
    products.unshift(product);
    renderProducts();
    document.getElementById("url-input").value = "";
    showToast("Товар добавлен!", "success");
  } catch (err) {
    errorEl.textContent = err.message;
    errorEl.classList.remove("hidden");
  } finally {
    btn.disabled = false;
    btn.textContent = "Добавить";
  }
}

// ── Delete ────────────────────────────────────────────────────────────────────

async function deleteProduct(id, name) {
  if (!confirm(`Удалить «${name || id}»?`)) return;
  try {
    await apiFetch(`/products/${id}`, { method: "DELETE" });
    products = products.filter((p) => p.id !== id);
    renderProducts();
    if (modalProductId === id) closeModal();
    showToast("Товар удалён");
  } catch (err) {
    showToast(err.message, "error");
  }
}

// ── Toggle Active ─────────────────────────────────────────────────────────────

async function toggleActive(id, isActive) {
  try {
    const updated = await apiFetch(`/products/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ is_active: isActive }),
    });
    const idx = products.findIndex((p) => p.id === id);
    if (idx !== -1) products[idx] = { ...products[idx], ...updated };
    renderProducts();
  } catch (err) {
    showToast(err.message, "error");
  }
}

// ── Refresh All ───────────────────────────────────────────────────────────────

async function refreshAll() {
  const btn = document.getElementById("refresh-btn");
  btn.classList.add("spinning");
  btn.disabled = true;
  try {
    await loadProducts();
    showToast("Цены обновлены", "success");
  } finally {
    btn.classList.remove("spinning");
    btn.disabled = false;
  }
}

// ── History Modal ─────────────────────────────────────────────────────────────

async function showChart(id) {
  modalProductId = id;
  let p = products.find((x) => x.id === id);

  // Fetch full detail with history
  try {
    p = await apiFetch(`/products/${id}`);
    const idx = products.findIndex((x) => x.id === id);
    if (idx !== -1) products[idx] = p;
  } catch (e) { /* use cached */ }

  const history = p.history || [];

  document.getElementById("modal-title").textContent = p.title;
  document.getElementById("modal-marketplace").textContent =
    marketplaceLabel(p.marketplace) + " · " + p.url;
  document.getElementById("modal-link").href = p.url;

  // Stats
  const prices = history.map((h) => parseFloat(h.price));
  const cur = parseFloat(p.current_price);
  const min = prices.length ? Math.min(...prices) : cur;
  const max = prices.length ? Math.max(...prices) : cur;
  const first = prices.length ? prices[0] : cur;
  const diff = cur - first;
  const pct = first ? (diff / first) * 100 : 0;

  document.getElementById("modal-stats").innerHTML = `
    <div class="stat-card">
      <div class="stat-label">Текущая</div>
      <div class="stat-value">${formatPrice(cur)}</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Минимум</div>
      <div class="stat-value green">${formatPrice(min)}</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Максимум</div>
      <div class="stat-value red">${formatPrice(max)}</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">За всё время</div>
      <div class="stat-value ${diff < 0 ? "green" : diff > 0 ? "red" : ""}">
        ${diff < 0 ? "↓" : diff > 0 ? "↑" : "→"} ${Math.abs(pct).toFixed(1)}%
      </div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Замеров</div>
      <div class="stat-value">${prices.length}</div>
    </div>
  `;

  // Chart
  if (modalChart) modalChart.destroy();
  const canvas = document.getElementById("modal-chart");
  const labels = history.map((h) =>
    new Date(h.checked_at).toLocaleDateString("ru-RU", { day: "2-digit", month: "2-digit" })
  );

  const gradient = canvas.getContext("2d").createLinearGradient(0, 0, 0, 220);
  gradient.addColorStop(0, "rgba(108,99,255,0.25)");
  gradient.addColorStop(1, "rgba(108,99,255,0)");

  modalChart = new Chart(canvas, {
    type: "line",
    data: {
      labels,
      datasets: [{
        label: "Цена",
        data: prices,
        borderColor: "#6c63ff",
        backgroundColor: gradient,
        borderWidth: 2,
        pointRadius: prices.length < 30 ? 4 : 1,
        pointBackgroundColor: "#6c63ff",
        tension: 0.3,
        fill: true,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (ctx) => formatPrice(ctx.parsed.y),
          },
        },
      },
      scales: {
        x: {
          ticks: { color: "#8b8fa8", maxTicksLimit: 8 },
          grid: { color: "rgba(255,255,255,0.05)" },
        },
        y: {
          ticks: {
            color: "#8b8fa8",
            callback: (v) => v.toLocaleString("ru-RU") + " ₽",
          },
          grid: { color: "rgba(255,255,255,0.05)" },
        },
      },
    },
  });

  // Footer buttons
  document.getElementById("modal-check-btn").onclick = async () => {
    const btn = document.getElementById("modal-check-btn");
    btn.disabled = true;
    btn.textContent = "Проверяю...";
    try {
      const updated = await apiFetch(`/products/${id}/check`, { method: "POST" });
      const idx = products.findIndex((x) => x.id === id);
      if (idx !== -1) products[idx] = updated;
      closeModal();
      renderProducts();
      showToast("Цена обновлена!", "success");
    } catch (err) {
      showToast(err.message, "error");
    } finally {
      btn.disabled = false;
      btn.textContent = "Проверить сейчас";
    }
  };

  document.getElementById("modal-delete-btn").onclick = () => {
    closeModal();
    deleteProduct(id, p.title);
  };

  document.getElementById("modal-overlay").classList.remove("hidden");
}

function closeModal() {
  document.getElementById("modal-overlay").classList.add("hidden");
  modalProductId = null;
}

// ── Settings ──────────────────────────────────────────────────────────────────

function openSettings() {
  document.getElementById("settings-chat-id").value = chatId;
  document.getElementById("settings-overlay").classList.remove("hidden");
}

function closeSettings() {
  document.getElementById("settings-overlay").classList.add("hidden");
}

function saveChatId() {
  const val = document.getElementById("settings-chat-id").value.trim();
  if (!val) return;
  chatId = val;
  localStorage.setItem("chatId", chatId);
  closeSettings();
  loadProducts();
  showToast("Chat ID сохранён", "success");
}

// ── Toast ─────────────────────────────────────────────────────────────────────

let toastTimer;
function showToast(msg, type = "") {
  const toast = document.getElementById("toast");
  toast.textContent = msg;
  toast.className = "toast" + (type ? " " + type : "");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.add("hidden"), 3000);
}

// ── Start ─────────────────────────────────────────────────────────────────────

init();
