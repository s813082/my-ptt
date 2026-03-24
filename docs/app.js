/* ============================================================
   PTT 情緒雷達 — app.js
   ============================================================ */

const DATA_INDEX = './data/index.json';
const DATA_DIR   = './data/';

// ── Chart instances ──────────────────────────────────────────
let donutChart = null;
let hourlyChart = null;
let trendChart  = null;

// ── DOM refs ─────────────────────────────────────────────────
const $ = id => document.getElementById(id);
const loadingState = $('loadingState');
const errorState   = $('errorState');
const mainContent  = $('mainContent');
const datePicker   = $('datePicker');

// ── State ────────────────────────────────────────────────────
let availableDates = [];
let currentDate    = null;
let tickerComments = [];   // full shuffled pool
let tickerTimer    = null; // setInterval handle

/* ══════════════════════════════════════════════════════════════
   Initialise
══════════════════════════════════════════════════════════════ */
async function init() {
    showLoading();
    try {
        const res = await fetch(DATA_INDEX);
        if (!res.ok) throw new Error('Cannot load index.json');
        const index = await res.json();

        availableDates = (index.dates || []).sort();

        if (availableDates.length === 0) {
            showError('目前尚無分析資料', '系統將於每個交易日 14:00 自動更新。');
            return;
        }

        // Default to latest available date
        currentDate = availableDates[availableDates.length - 1];
        datePicker.value = currentDate;
        datePicker.min   = availableDates[0];
        datePicker.max   = currentDate;

        await loadDate(currentDate, index);
    } catch (e) {
        console.error(e);
        showError('讀取失敗', e.message);
    }
}

/* ══════════════════════════════════════════════════════════════
   Load & render a specific date
══════════════════════════════════════════════════════════════ */
async function loadDate(dateStr, cachedIndex) {
    showLoading();
    try {
        const res = await fetch(`${DATA_DIR}${dateStr}.json`);
        if (!res.ok) throw new Error(`找不到 ${dateStr} 的資料`);
        const data = await res.json();

        // Fetch all dates for the trend chart if we have them
        let allData = null;
        if (availableDates.length > 1) {
            allData = await loadAllForTrend();
        }

        renderDashboard(data, allData);
        showMain();
    } catch (e) {
        console.error(e);
        showError('無資料', `${dateStr} 無可用的分析資料`);
    }
}

async function loadAllForTrend() {
    const promises = availableDates.map(d =>
        fetch(`${DATA_DIR}${d}.json`).then(r => r.ok ? r.json() : null).catch(() => null)
    );
    const results = await Promise.all(promises);
    return results.filter(Boolean);
}

/* ══════════════════════════════════════════════════════════════
   Render
══════════════════════════════════════════════════════════════ */
function renderDashboard(data, allData) {
    renderKPI(data);
    renderGauge(data);
    renderDonut(data);
    renderHourly(data);
    renderTrend(allData);
    renderWordCloud(data);
    renderCommentFeed(data);
    renderFooter(data);
}

/* ── KPI Strip ────────────────────────────────────────────── */
function renderKPI(data) {
    const ms = data.market_summary;
    if (ms && ms.taiex_close) {
        const pct = ms.change_percent;
        $('taiexValue').textContent = ms.taiex_close.toLocaleString('zh-TW', { minimumFractionDigits: 2 });
        const changeEl = $('changeValue');
        changeEl.textContent = (pct > 0 ? '+' : '') + pct.toFixed(2) + '%';
        changeEl.className   = 'kpi-value ' + (pct >= 0 ? 'up' : 'down');
    } else {
        $('taiexValue').textContent = '—';
        $('changeValue').textContent = '—';
    }

    $('commentCount').textContent = (data.total_comments_analyzed || 0).toLocaleString();
    const src = $('sourceLink');
    src.href = data.article_url || '#';
    src.textContent = data.article_title ? data.article_title.slice(0, 20) + '…' : 'PTT Stock 板';
}

/* ── Gauge ────────────────────────────────────────────────── */
function renderGauge(data) {
    const r = data.sentiment_ratio || {};
    const bull = r.bullish_pct  || 0;
    const bear = r.bearish_pct  || 0;
    const neut = r.neutral_pct  || 0;
    const c    = data.sentiment || {};

    $('heroDate').textContent = data.date || '';

    // Ring: circumference = 2π×80 ≈ 502
    const CIRC = 502;
    const bullOffset = CIRC * (1 - bull / 100);
    const bearTotal  = (bull + bear) / 100;
    const bearOffset = CIRC * (1 - bearTotal);

    const gaugeBull = $('gaugeBull');
    const gaugeBear = $('gaugeBear');
    // rotate so bear starts where bull ends
    gaugeBull.style.strokeDashoffset = bullOffset;
    gaugeBear.style.strokeDashoffset = bearOffset;
    // Shift bear arc to start after bull arc
    gaugeBear.style.transform = `rotate(${(bull / 100) * 360}deg)`;
    gaugeBear.style.transformOrigin = 'center';

    // Emoji / label
    const bullShare = bull / (bull + bear + 0.001);
    let emoji, label;
    if (bull > bear + 15) { emoji = '🚀'; label = '強烈看多'; }
    else if (bull > bear + 5) { emoji = '📈'; label = '偏多'; }
    else if (bear > bull + 15) { emoji = '💀'; label = '極度看空'; }
    else if (bear > bull + 5) { emoji = '📉'; label = '偏空'; }
    else { emoji = '⚖️'; label = '多空拉鋸'; }

    $('gaugeEmoji').textContent = emoji;
    $('gaugeLabel').textContent = label;

    // Progress bars & percentages
    $('bullPct').textContent  = bull.toFixed(1) + '%';
    $('bearPct').textContent  = bear.toFixed(1) + '%';
    $('neutPct').textContent  = neut.toFixed(1) + '%';
    $('bullCount').textContent = (c.bullish || 0) + ' 則';
    $('bearCount').textContent = (c.bearish || 0) + ' 則';
    $('neutCount').textContent = (c.neutral || 0) + ' 則';

    // Animate progress bars
    setTimeout(() => {
        $('glBullBar').style.width = bull + '%';
        $('glBearBar').style.width = bear + '%';
        $('glNeutBar').style.width = neut + '%';
    }, 100);
}

/* ── Donut Chart ──────────────────────────────────────────── */
function renderDonut(data) {
    const s = data.sentiment || {};
    const values = [s.bullish || 0, s.bearish || 0, s.neutral || 0];

    const ctx = $('donutChart').getContext('2d');
    if (donutChart) donutChart.destroy();

    donutChart = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: ['看多 Bullish', '看空 Bearish', '中立 Neutral'],
            datasets: [{
                data: values,
                backgroundColor: ['rgba(34,211,238,0.85)', 'rgba(244,63,94,0.85)', 'rgba(124,58,237,0.75)'],
                borderColor:     ['#22d3ee', '#f43f5e', '#7c3aed'],
                borderWidth: 2,
                hoverOffset: 6,
            }]
        },
        options: {
            cutout: '72%',
            responsive: true,
            maintainAspectRatio: false,
            animation: { animateRotate: true, duration: 900 },
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: { color: '#94a3b8', padding: 14, font: { size: 12 }, boxWidth: 12, boxHeight: 12 }
                },
                tooltip: {
                    backgroundColor: 'rgba(13,17,23,0.95)',
                    borderColor: 'rgba(255,255,255,0.08)',
                    borderWidth: 1,
                    titleColor: '#f1f5f9',
                    bodyColor: '#94a3b8',
                    callbacks: {
                        label: ctx => ` ${ctx.label}: ${ctx.parsed} 則 (${((ctx.parsed / values.reduce((a,b)=>a+b,0))*100).toFixed(1)}%)`
                    }
                }
            }
        }
    });
}

/* ── Hourly (30-min) Battle Line Chart ────────────────────── */
function renderHourly(data) {
    // Support both old (hourly_sentiment) and new (intraday_sentiment) field names
    const raw = (data.intraday_sentiment || data.hourly_sentiment || [])
        .sort((a, b) => (a.slot || a.hour || '').localeCompare(b.slot || b.hour || ''));

    const labels = raw.map(d => d.slot || (d.hour + ':00'));
    const bulls  = raw.map(d => d.bullish);
    const bears  = raw.map(d => d.bearish);
    const neuts  = raw.map(d => d.neutral);

    const ctx = $('hourlyChart').getContext('2d');
    if (hourlyChart) hourlyChart.destroy();

    // Gradient fills for battle effect
    const gradBull = ctx.createLinearGradient(0, 0, 0, 280);
    gradBull.addColorStop(0, 'rgba(34,211,238,0.28)');
    gradBull.addColorStop(1, 'rgba(34,211,238,0.01)');

    const gradBear = ctx.createLinearGradient(0, 0, 0, 280);
    gradBear.addColorStop(0, 'rgba(244,63,94,0.28)');
    gradBear.addColorStop(1, 'rgba(244,63,94,0.01)');

    const gradNeut = ctx.createLinearGradient(0, 0, 0, 280);
    gradNeut.addColorStop(0, 'rgba(124,58,237,0.18)');
    gradNeut.addColorStop(1, 'rgba(124,58,237,0.01)');

    hourlyChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels,
            datasets: [
                {
                    label: '看多',
                    data: bulls,
                    borderColor: '#22d3ee',
                    backgroundColor: gradBull,
                    borderWidth: 2.5,
                    pointRadius: 4,
                    pointBackgroundColor: '#22d3ee',
                    pointBorderColor: '#0d1117',
                    pointBorderWidth: 2,
                    fill: true,
                    tension: 0.45,
                    order: 1,
                },
                {
                    label: '看空',
                    data: bears,
                    borderColor: '#f43f5e',
                    backgroundColor: gradBear,
                    borderWidth: 2.5,
                    pointRadius: 4,
                    pointBackgroundColor: '#f43f5e',
                    pointBorderColor: '#0d1117',
                    pointBorderWidth: 2,
                    fill: true,
                    tension: 0.45,
                    order: 2,
                },
                {
                    label: '中立',
                    data: neuts,
                    borderColor: '#7c3aed',
                    backgroundColor: gradNeut,
                    borderWidth: 1.5,
                    pointRadius: 3,
                    pointBackgroundColor: '#7c3aed',
                    pointBorderColor: '#0d1117',
                    pointBorderWidth: 2,
                    fill: true,
                    tension: 0.45,
                    borderDash: [4, 3],
                    order: 3,
                },
            ]
        },
        options: {
            ...chartBaseOptions('line'),
            interaction: { mode: 'index', intersect: false },
            plugins: {
                ...chartBaseOptions('line').plugins,
                tooltip: {
                    backgroundColor: 'rgba(13,17,23,0.95)',
                    borderColor: 'rgba(255,255,255,0.1)',
                    borderWidth: 1,
                    titleColor: '#f1f5f9',
                    bodyColor: '#94a3b8',
                    padding: 12,
                    callbacks: {
                        title: items => `⏱ ${items[0].label}`,
                        label: ctx => ` ${ctx.dataset.label}：${ctx.parsed.y} 則`,
                    }
                }
            }
        }
    });
}

/* ── Trend Chart ──────────────────────────────────────────── */
function renderTrend(allData) {
    const section = $('trendSection');
    if (!allData || allData.length < 2) {
        if (section) section.style.display = 'none';
        return;
    }
    if (section) section.style.display = '';

    const sorted = allData.sort((a, b) => a.date.localeCompare(b.date));
    const labels = sorted.map(d => d.date);
    const bulls  = sorted.map(d => d.sentiment_ratio?.bullish_pct || 0);
    const bears  = sorted.map(d => d.sentiment_ratio?.bearish_pct || 0);

    const ctx = $('trendChart').getContext('2d');
    if (trendChart) trendChart.destroy();

    trendChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels,
            datasets: [
                {
                    label: '看多 %', data: bulls,
                    borderColor: '#22d3ee', backgroundColor: 'rgba(34,211,238,0.08)',
                    borderWidth: 2, pointRadius: 4, pointBackgroundColor: '#22d3ee',
                    fill: true, tension: 0.4
                },
                {
                    label: '看空 %', data: bears,
                    borderColor: '#f43f5e', backgroundColor: 'rgba(244,63,94,0.08)',
                    borderWidth: 2, pointRadius: 4, pointBackgroundColor: '#f43f5e',
                    fill: true, tension: 0.4
                }
            ]
        },
        options: chartBaseOptions('line', { yMax: 100, unit: '%' })
    });
}

/* ── Word Cloud ─────────────────────────────────────────────── */
function renderWordCloud(data) {
    const section = $('wordCloudSection');
    const canvas = $('wordCloudCanvas');
    const wrapper = section.querySelector('.wordcloud-wrap');
    const words = data.word_cloud || [];

    if (!words || words.length === 0) {
        if (section) section.style.display = 'none';
        return;
    }
    if (section) section.style.display = '';

    // Fix High-DPI canvas blurriness
    const dpr = window.devicePixelRatio || 1;
    // Ensure the wrapper is visible so we can get its dimensions
    const rect = wrapper.getBoundingClientRect();
    const width = rect.width || wrapper.offsetWidth || 800;
    const height = rect.height || wrapper.offsetHeight || 320;

    canvas.width = width * dpr;
    canvas.height = height * dpr;
    canvas.style.width = '100%';
    canvas.style.height = '100%';

    // Convert to wordcloud2.js format: [word, weight]
    const maxCount = Math.max(...words.map(w => w.count), 1);
    const list = words.map(w => {
        // scale to sensible font size then multiply by dpr
        // Increased max size to 120 to make words much larger and take up more space
        const baseSize = Math.max(16, (w.count / maxCount) * 120);
        return [w.word, baseSize * dpr];
    });

    // Theme colors for words (cyan, purple, pink, etc.)
    const colors = ['#22d3ee', '#7c3aed', '#f43f5e', '#a78bfa', '#38bdf8', '#fb7185'];

    WordCloud(canvas, {
        list: list,
        fontFamily: "'Inter', 'Noto Sans TC', sans-serif",
        weightFactor: 1, // Already calculated absolute sizes
        color: () => colors[Math.floor(Math.random() * colors.length)],
        backgroundColor: 'transparent',
        rotateRatio: 0.2, // occasionally rotate words for density
        rotationSteps: 2,
        shape: 'circle',
        drawOutOfBound: false,
        shrinkToFit: true,
        wait: 10,
    });
}


/* ── Live Comment Ticker ─────────────────────────────────── */
const TICKER_MAX     = 8;      // max rows visible
const TICKER_INTERVAL_MIN = 1600; // ms
const TICKER_INTERVAL_MAX = 3800; // ms

const LABELS = { bullish: '看多', bearish: '看空', neutral: '中立' };

function buildCommentEl(c) {
    const typeClass = `type-${c.type || '→'}`;
    const badgeCls  = c.sentiment || 'neutral';
    const label     = LABELS[c.sentiment] || '中立';
    const author    = escapeHtml(c.author  || 'anonymous');
    const content   = escapeHtml(c.content || '');
    const el = document.createElement('div');
    el.className = 'comment-item ticker-new';
    if (c.id) el.dataset.id = String(c.id); // store ID to check uniqueness
    el.innerHTML = `
        <span class="ci-type ${typeClass}">${escapeHtml(c.type || '→')}</span>
        <span class="ci-author">${author}</span>
        <span class="ci-content">${content}</span>
        <span class="ci-badge ${badgeCls}">${label}</span>`;
    return el;
}

function stopTicker() {
    if (tickerTimer) { clearTimeout(tickerTimer); tickerTimer = null; }
}

function startTicker(feed) {
    stopTicker();
    let idx = 0;

    function tick() {
        if (!tickerComments.length) return;

        const delay = TICKER_INTERVAL_MIN + Math.random() * (TICKER_INTERVAL_MAX - TICKER_INTERVAL_MIN);

        // Ensure no duplicates on screen
        const currentIds = new Set(Array.from(feed.children).map(el => el.dataset.id).filter(Boolean));
        if (currentIds.size >= tickerComments.length) {
            // All available comments are currently on screen, wait for next tick
            tickerTimer = setTimeout(tick, delay);
            return;
        }

        let c = null;
        for (let tries = 0; tries < tickerComments.length; tries++) {
            const candidate = tickerComments[idx % tickerComments.length];
            idx++;
            if (candidate.id && !currentIds.has(String(candidate.id))) {
                c = candidate;
                break;
            }
        }

        if (!c) {
            tickerTimer = setTimeout(tick, delay);
            return;
        }

        const el = buildCommentEl(c);
        // Insert at top
        feed.insertBefore(el, feed.firstChild);
        // Trigger slide-in animation
        requestAnimationFrame(() => el.classList.add('ticker-visible'));

        // Remove oldest if over limit
        while (feed.children.length > TICKER_MAX) {
            const last = feed.lastChild;
            if (last) {
                last.classList.add('ticker-out');
                setTimeout(() => last.remove(), 350);
            }
            break;
        }

        tickerTimer = setTimeout(tick, delay);
    }

    // Kick off after a short initial delay
    tickerTimer = setTimeout(tick, 600);
}

function renderCommentFeed(data) {
    const feed = $('commentFeed');
    stopTicker();
    feed.innerHTML = '';

    const allComments = data.comments || [];
    if (allComments.length === 0) {
        feed.innerHTML = '<div class="feed-empty">此次資料無留言記錄</div>';
        return;
    }

    // Shuffle a copy for variety
    tickerComments = [...allComments].sort(() => Math.random() - 0.5);

    // Show initial stubs (max 3, or less if not enough comments)
    const initialCount = Math.min(3, tickerComments.length);
    tickerComments.slice(0, initialCount).forEach(c => {
        const el = buildCommentEl(c);
        el.classList.add('ticker-visible'); // already visible
        feed.appendChild(el);
    });

    startTicker(feed);
}

/* ── Footer ───────────────────────────────────────────────── */
function renderFooter(data) {
    if (data.analyzed_at) {
        const dt = new Date(data.analyzed_at);
        $('lastUpdate').textContent = dt.toLocaleString('zh-TW', { timeZone: 'Asia/Taipei' });
    }
}

/* ══════════════════════════════════════════════════════════════
   Shared Chart Options
══════════════════════════════════════════════════════════════ */
function chartBaseOptions(type, extra = {}) {
    const isBar  = type === 'bar';
    const isLine = type === 'line';
    return {
        responsive: true,
        maintainAspectRatio: false,
        animation: { duration: 800 },
        plugins: {
            legend: {
                position: 'top',
                align: 'end',
                labels: {
                    color: '#94a3b8', padding: 16,
                    font: { size: 11.5 },
                    boxWidth: 12, boxHeight: 12
                }
            },
            tooltip: {
                backgroundColor: 'rgba(13,17,23,0.95)',
                borderColor: 'rgba(255,255,255,0.08)',
                borderWidth: 1,
                titleColor: '#f1f5f9',
                bodyColor: '#94a3b8',
            }
        },
        scales: {
            x: {
                stacked: isBar,
                grid: { color: 'rgba(255,255,255,0.05)' },
                ticks: { color: '#64748b', font: { size: 11 } }
            },
            y: {
                stacked: isBar,
                grid: { color: 'rgba(255,255,255,0.05)' },
                ticks: {
                    color: '#64748b', font: { size: 11 },
                    callback: v => extra.unit ? v + extra.unit : v
                },
                max: extra.yMax || undefined,
                min: 0
            }
        }
    };
}

/* ══════════════════════════════════════════════════════════════
   UI Helpers
══════════════════════════════════════════════════════════════ */
function showLoading() {
    loadingState.classList.remove('hidden');
    errorState.classList.add('hidden');
    mainContent.classList.add('hidden');
}
function showMain() {
    loadingState.classList.add('hidden');
    errorState.classList.add('hidden');
    mainContent.classList.remove('hidden');
}
function showError(title, msg) {
    loadingState.classList.add('hidden');
    mainContent.classList.add('hidden');
    $('errorTitle').textContent  = title;
    $('errorMessage').textContent = msg;
    errorState.classList.remove('hidden');
}
function escapeHtml(s) {
    return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

/* ══════════════════════════════════════════════════════════════
   Event Listeners
══════════════════════════════════════════════════════════════ */
datePicker.addEventListener('change', async () => {
    currentDate = datePicker.value;
    await loadDate(currentDate);
});

$('prevDay').addEventListener('click', async () => {
    const idx = availableDates.indexOf(currentDate);
    if (idx > 0) {
        currentDate = availableDates[idx - 1];
        datePicker.value = currentDate;
        await loadDate(currentDate);
    }
});

$('nextDay').addEventListener('click', async () => {
    const idx = availableDates.indexOf(currentDate);
    if (idx < availableDates.length - 1) {
        currentDate = availableDates[idx + 1];
        datePicker.value = currentDate;
        await loadDate(currentDate);
    }
});

/* ══════════════════════════════════════════════════════════════
   Boot
══════════════════════════════════════════════════════════════ */
init();
