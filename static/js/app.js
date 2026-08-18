/* ============================================================
 * 量化交易分析系统 - 前端交互逻辑
 * ============================================================ */

const API = {
    market: '/api/market/overview',
    quotes: '/api/market/quotes',
    recommendations: '/api/recommendations',
    fullScan: '/api/scan/full',
    stockAnalysis: (code, name) => `/api/stock/${code}/analysis?name=${encodeURIComponent(name)}`,
    stockNews: (code) => `/api/stock/${code}/news`,
    marketNews: '/api/market/news',
    stockHistory: (code) => `/api/stock/${code}/history`,
    // AI相关
    aiStatus: '/api/ai/status',
    aiConfig: '/api/ai/config',
    aiProviders: '/api/ai/providers',
    aiMarkets: '/api/ai/markets',
    aiBoards: '/api/ai/boards',
    aiModels: (baseUrl) => `/api/ai/models?base_url=${encodeURIComponent(baseUrl)}`,
    aiRecommendations: (max, ai, market) => `/api/ai/recommendations?max=${max}&ai=${ai}&market=${market}`,
    aiRecommendStream: (params) => {
        const p = new URLSearchParams();
        Object.entries(params).forEach(([k, v]) => { if (v !== undefined && v !== null && v !== '') p.set(k, v); });
        p.set('stream', '1');
        return `/api/ai/recommendations?${p.toString()}`;
    },
    aiStockAnalysis: (code, name, ai, market) => `/api/ai/stock/${code}/analysis?name=${encodeURIComponent(name)}&ai=${ai}&market=${market}`,
    aiStream: (code, name, market) => `/api/ai/stream/${code}?name=${encodeURIComponent(name)}&market=${market}`,
    aiBacktest: (code, name) => `/api/ai/backtest?code=${code}&name=${encodeURIComponent(name)}`
};

// ========== 工具函数 ==========
function fmtPct(v) {
    if (v == null || isNaN(v)) return '--';
    const sign = v >= 0 ? '+' : '';
    return `${sign}${v.toFixed(2)}%`;
}

function fmtColor(v) {
    if (v == null || isNaN(v)) return '';
    return v >= 0 ? 'up' : 'down';
}

function fmtAmount(v) {
    if (v == null || isNaN(v)) return '--';
    if (v >= 1e8) return (v / 1e8).toFixed(2) + '亿';
    if (v >= 1e4) return (v / 1e4).toFixed(2) + '万';
    return v.toFixed(0);
}

async function fetchJSON(url) {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
}

// ========== 导航切换 ==========
document.querySelectorAll('.nav-tab').forEach(tab => {
    tab.addEventListener('click', (e) => {
        e.preventDefault();
        document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));
        document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
        tab.classList.add('active');
        const view = tab.dataset.view;
        document.getElementById(`view-${view}`).classList.add('active');

        if (view === 'market' && !window._marketLoaded) loadMarketQuotes(1);
        if (view === 'news' && !window._newsLoaded) loadMarketNews();
        if (view === 'ai') initAIView();
    });
});

// ========== 市场概览 ==========
async function loadMarketOverview() {
    try {
        const data = await fetchJSON(API.market);
        if (!data.success) return;

        // 指数
        const indexBar = document.getElementById('indexBar');
        indexBar.innerHTML = (data.indices || []).map(idx => `
            <div class="index-card">
                <span class="idx-name">${idx.name}</span>
                <span class="idx-price ${fmtColor(idx.pct_change)}">${idx.price ? idx.price.toFixed(2) : '--'}</span>
                <span class="idx-pct ${fmtColor(idx.pct_change)}">${fmtPct(idx.pct_change)}</span>
            </div>
        `).join('');

        // 涨幅榜
        renderRankList('topGainers', data.top_gainers);
        // 成交额榜
        renderRankList('topVolume', data.top_volume, true);
        // 板块
        renderSectors(data.sectors || []);

        // 更新市场状态
        const statusEl = document.querySelector('.status-text');
        const now = new Date();
        const hour = now.getHours();
        const isWeekday = now.getDay() >= 1 && now.getDay() <= 5;
        const isTradeTime = isWeekday && ((hour >= 9 && hour < 12) || (hour >= 13 && hour < 15));
        statusEl.textContent = isTradeTime ? '交易中' : '已收盘/休市';
    } catch (e) {
        console.error('市场概览加载失败:', e);
    }
}

function renderRankList(elId, list, byVolume = false) {
    const el = document.getElementById(elId);
    if (!list || list.length === 0) {
        el.innerHTML = '<div class="loading">暂无数据</div>';
        return;
    }
    el.innerHTML = `<ul class="rank-list">${list.map((s, i) => {
        const numClass = i === 0 ? 'top1' : i === 1 ? 'top2' : i === 2 ? 'top3' : '';
        return `<li class="rank-item" onclick="openStockDetail('${s.code}', '${s.name}')">
            <span class="rank-num ${numClass}">${i + 1}</span>
            <span class="rank-name">${s.name}</span>
            <span class="rank-price">${s.price}</span>
            <span class="rank-pct ${fmtColor(s.pct_change)}">${fmtPct(s.pct_change)}</span>
        </li>`;
    }).join('')}</ul>`;
}

function renderSectors(sectors) {
    const el = document.getElementById('sectorList');
    if (!sectors || sectors.length === 0) {
        el.innerHTML = '<div class="loading">暂无数据</div>';
        return;
    }
    el.innerHTML = sectors.slice(0, 10).map(s => `
        <div class="sector-item">
            <div>
                <div class="sector-name">${s.name}</div>
                <div class="sector-lead">领涨: ${s.lead_stock} (${fmtPct(s.lead_pct)})</div>
            </div>
            <span class="sector-pct ${fmtColor(s.pct_change)}">${fmtPct(s.pct_change)}</span>
        </div>
    `).join('');
}

// ========== 推荐列表 ==========
async function loadRecommendations() {
    const el = document.getElementById('recommendList');
    el.innerHTML = '<div class="loading">正在扫描市场，生成推荐...</div>';
    try {
        const data = await fetchJSON(API.recommendations);
        if (!data.success) {
            el.innerHTML = '<div class="loading">获取推荐失败</div>';
            return;
        }
        renderRecommendList(el, data.data || []);
    } catch (e) {
        el.innerHTML = '<div class="loading">加载失败，请稍后重试</div>';
        console.error(e);
    }
}

function renderRecommendList(el, list) {
    if (!list || list.length === 0) {
        el.innerHTML = '<div class="loading">暂无推荐，请尝试全市场扫描</div>';
        return;
    }
    el.innerHTML = list.map(r => {
        const scoreClass = r.score >= 60 ? 'score-high' : r.score >= 40 ? 'score-mid' : 'score-low';
        const signalClass = r.signal_type === 'buy' ? 'signal-buy' : r.signal_type === 'sell' ? 'signal-sell' : 'signal-hold';
        const topReason = (r.reasons_bull && r.reasons_bull.length > 0) ? r.reasons_bull[0] : '查看详情';
        return `<div class="recommend-item" onclick="openStockDetail('${r.code}', '${r.name}')">
            <div class="rec-score ${scoreClass}">${r.score}</div>
            <div class="rec-info">
                <div class="rec-name">${r.name} <span class="rec-code">${r.code}</span></div>
                <div class="rec-reason">${topReason}</div>
            </div>
            <div class="rec-signal ${signalClass}">${r.signal}</div>
        </div>`;
    }).join('');
}

// ========== 全市场扫描 ==========
async function loadFullScan() {
    const el = document.getElementById('fullRecommendList');
    el.innerHTML = '<div class="loading">正在全市场扫描，请稍候（约30-60秒）...</div>';
    try {
        const data = await fetchJSON(`${API.fullScan}?max=30`);
        if (!data.success) {
            el.innerHTML = '<div class="loading">扫描失败</div>';
            return;
        }
        renderRecommendList(el, data.data || []);
    } catch (e) {
        el.innerHTML = '<div class="loading">扫描失败，请稍后重试</div>';
        console.error(e);
    }
}

// ========== 行情表格 ==========
let currentPage = 1;

async function loadMarketQuotes(page) {
    currentPage = page;
    const tbody = document.getElementById('stockTableBody');
    tbody.innerHTML = '<tr><td colspan="7" class="loading">加载中...</td></tr>';
    try {
        const search = document.getElementById('marketSearch').value;
        let url = `${API.quotes}?page=${page}&per_page=50`;
        if (search) url += `&search=${encodeURIComponent(search)}`;
        const data = await fetchJSON(url);
        if (!data.success) return;

        window._marketLoaded = true;
        tbody.innerHTML = data.data.map(s => `
            <tr onclick="openStockDetail('${s.code}', '${s.name}')">
                <td>${s.code}</td>
                <td>${s.name}</td>
                <td>${s.price}</td>
                <td class="${fmtColor(s.pct_change)}">${fmtPct(s.pct_change)}</td>
                <td>${fmtAmount(s.amount)}</td>
                <td>${s.turnover_rate ? s.turnover_rate.toFixed(2) + '%' : '--'}</td>
                <td><button class="btn-action" style="padding:2px 8px;font-size:12px;" onclick="event.stopPropagation();openStockDetail('${s.code}', '${s.name}')">分析</button></td>
            </tr>
        `).join('');

        // 分页
        renderPagination(data.total, data.page, data.per_page);
    } catch (e) {
        tbody.innerHTML = '<tr><td colspan="7">加载失败</td></tr>';
        console.error(e);
    }
}

function renderPagination(total, page, perPage) {
    const el = document.getElementById('pagination');
    const totalPages = Math.ceil(total / perPage);
    if (totalPages <= 1) { el.innerHTML = ''; return; }

    let html = '';
    html += `<button ${page <= 1 ? 'disabled' : ''} onclick="loadMarketQuotes(${page - 1})">上一页</button>`;
    const start = Math.max(1, page - 2);
    const end = Math.min(totalPages, page + 2);
    for (let i = start; i <= end; i++) {
        html += `<button class="${i === page ? 'active' : ''}" onclick="loadMarketQuotes(${i})">${i}</button>`;
    }
    html += `<button ${page >= totalPages ? 'disabled' : ''} onclick="loadMarketQuotes(${page + 1})">下一页</button>`;
    html += `<span style="color:var(--text-secondary);font-size:12px;align-self:center;">共${total}只</span>`;
    el.innerHTML = html;
}

// 搜索
document.getElementById('marketSearch').addEventListener('input', () => {
    clearTimeout(window._searchTimer);
    window._searchTimer = setTimeout(() => loadMarketQuotes(1), 500);
});

// ========== 新闻 ==========
async function loadMarketNews() {
    const el = document.getElementById('newsList');
    el.innerHTML = '<div class="loading">加载中...</div>';
    try {
        const data = await fetchJSON(API.marketNews);
        if (!data.success || !data.data || data.data.length === 0) {
            el.innerHTML = '<div class="loading">暂无新闻数据</div>';
            return;
        }
        window._newsLoaded = true;
        el.innerHTML = data.data.map(n => `
            <div class="news-item">
                <div class="news-title">${n.title}</div>
                <div class="news-meta">
                    <span>${n.source || ''}</span>
                    <span>${n.date || ''}</span>
                </div>
                <div class="news-content">${n.content || ''}</div>
            </div>
        `).join('');
    } catch (e) {
        el.innerHTML = '<div class="loading">加载失败</div>';
        console.error(e);
    }
}

// ========== 个股详情弹窗 ==========
let klineChart = null;

async function openStockDetail(code, name) {
    const modal = document.getElementById('stockModal');
    const body = document.getElementById('modalBody');
    const title = document.getElementById('modalTitle');

    title.textContent = `${name} (${code}) - 技术分析`;
    modal.classList.add('active');
    body.innerHTML = '<div class="loading">正在获取数据并分析...</div>';

    if (klineChart) { klineChart.dispose(); klineChart = null; }

    try {
        const [analysisData, newsData] = await Promise.all([
            fetchJSON(API.stockAnalysis(code, name)),
            fetchJSON(API.stockNews(code)).catch(() => ({ success: false, data: [] }))
        ]);

        if (!analysisData.success) {
            body.innerHTML = '<div class="loading">分析数据获取失败</div>';
            return;
        }

        const r = analysisData.data;
        const a = r.analysis;
        const points = r.points;
        const scoreClass = r.score >= 60 ? 'score-high' : r.score >= 40 ? 'score-mid' : 'score-low';
        const signalClass = r.signal_type === 'buy' ? 'signal-buy' : r.signal_type === 'sell' ? 'signal-sell' : 'signal-hold';
        const barColor = r.score >= 60 ? '#3fb950' : r.score >= 40 ? '#d29922' : '#f85149';

        let html = `
        <!-- 综合评分 -->
        <div class="analysis-section">
            <div class="section-title">📊 综合评估</div>
            <div style="display:flex;align-items:center;gap:16px;margin-bottom:8px;">
                <div class="rec-score ${scoreClass}" style="width:56px;height:56px;font-size:20px;">${r.score}</div>
                <div>
                    <div style="font-size:18px;font-weight:700;">${r.name} <span style="font-size:14px;color:var(--text-secondary);">${r.code}</span></div>
                    <div style="font-size:14px;margin-top:2px;">
                        当前价: <span style="font-weight:700;font-size:18px;">${a.close}</span>
                        <span class="${fmtColor(a.pct_change)}" style="margin-left:8px;">${fmtPct(a.pct_change)}</span>
                    </div>
                </div>
                <div class="rec-signal ${signalClass}" style="margin-left:auto;font-size:14px;padding:8px 16px;">${r.signal}</div>
            </div>
            <div class="score-bar-container">
                <div class="score-bar-fill" style="width:${r.score}%;background:${barColor};">${r.score}/100</div>
            </div>
            <div style="font-size:13px;color:var(--text-secondary);">趋势: ${a.trend}</div>
        </div>

        <!-- K线图 -->
        <div class="analysis-section">
            <div class="section-title">📈 K线走势</div>
            <div id="klineChart" class="chart-container"></div>
        </div>

        <!-- 技术指标 -->
        <div class="analysis-section">
            <div class="section-title">🔧 技术指标</div>
            <div class="indicator-grid">
                <div class="indicator-card">
                    <div class="ind-label">MA均线</div>
                    <div class="ind-value" style="font-size:14px;">
                        MA5: ${a.ma5 || '--'} | MA10: ${a.ma10 || '--'}<br>
                        MA20: ${a.ma20 || '--'} | MA60: ${a.ma60 || '--'}
                    </div>
                </div>
                <div class="indicator-card">
                    <div class="ind-label">MACD</div>
                    <div class="ind-value" style="font-size:14px;">DIF: ${a.macd.dif} DEA: ${a.macd.dea}</div>
                    <div class="ind-signal ${a.macd.signal.includes('金叉') || a.macd.signal.includes('多头') ? 'signal-pos' : a.macd.signal.includes('死叉') || a.macd.signal.includes('空头') ? 'signal-neg' : 'signal-neu'}">${a.macd.signal}</div>
                </div>
                <div class="indicator-card">
                    <div class="ind-label">RSI</div>
                    <div class="ind-value" style="font-size:14px;">RSI6: ${a.rsi.rsi6} RSI12: ${a.rsi.rsi12}</div>
                    <div class="ind-signal ${a.rsi.signal.includes('超买') ? 'signal-neg' : a.rsi.signal.includes('超卖') ? 'signal-pos' : 'signal-neu'}">${a.rsi.signal}</div>
                </div>
                <div class="indicator-card">
                    <div class="ind-label">KDJ</div>
                    <div class="ind-value" style="font-size:14px;">K: ${a.kdj.k} D: ${a.kdj.d} J: ${a.kdj.j}</div>
                    <div class="ind-signal ${a.kdj.signal.includes('金叉') ? 'signal-pos' : a.kdj.signal.includes('死叉') ? 'signal-neg' : 'signal-neu'}">${a.kdj.signal}</div>
                </div>
                <div class="indicator-card">
                    <div class="ind-label">布林带</div>
                    <div class="ind-value" style="font-size:14px;">上轨: ${a.boll.upper} 下轨: ${a.boll.lower}</div>
                    <div class="ind-signal signal-neu">${a.boll.position}</div>
                </div>
                <div class="indicator-card">
                    <div class="ind-label">量价分析</div>
                    <div class="ind-value" style="font-size:14px;">量比: ${a.volume.volume_ratio || '--'}</div>
                    <div class="ind-signal signal-neu">${a.volume.pattern || '--'}</div>
                </div>
            </div>
        </div>

        <!-- 支撑压力位 -->
        <div class="analysis-section">
            <div class="section-title">🎯 支撑压力位</div>
            <div class="trade-points">
                <div class="trade-point">
                    <div class="tp-label">当前价</div>
                    <div class="tp-value">${a.support_resistance.current_price}</div>
                </div>
                <div class="trade-point" style="border-color:var(--green);">
                    <div class="tp-label">最近支撑</div>
                    <div class="tp-value up">${a.support_resistance.nearest_support}</div>
                </div>
                <div class="trade-point" style="border-color:var(--red);">
                    <div class="tp-label">最近压力</div>
                    <div class="tp-value down">${a.support_resistance.nearest_resistance}</div>
                </div>
            </div>
        </div>

        <!-- 交易计划 -->
        <div class="analysis-section">
            <div class="section-title">📋 交易计划（T+1模式）</div>
            <div class="trade-plan">${points.strategy || '暂无交易计划'}</div>`;

        if (r.signal_type === 'buy') {
            html += `
            <div class="trade-points">
                <div class="trade-point" style="border-color:var(--accent);">
                    <div class="tp-label">买入价</div>
                    <div class="tp-value" style="color:var(--accent);">${points.entry_price}</div>
                </div>
                <div class="trade-point" style="border-color:var(--green);">
                    <div class="tp-label">止损价</div>
                    <div class="tp-value down">${points.stop_loss}</div>
                </div>
                <div class="trade-point" style="border-color:var(--red);">
                    <div class="tp-label">目标价一</div>
                    <div class="tp-value up">${points.target1}</div>
                </div>
                <div class="trade-point" style="border-color:var(--red);">
                    <div class="tp-label">目标价二</div>
                    <div class="tp-value up">${points.target2}</div>
                </div>
                ${points.risk_reward_ratio ? `<div class="trade-point"><div class="tp-label">盈亏比</div><div class="tp-value" style="color:var(--gold);">1:${points.risk_reward_ratio}</div></div>` : ''}
            </div>`;
        }

        html += `
        </div>

        <!-- 买入/卖出理由 -->
        <div class="analysis-section">
            <div class="section-title">💡 分析理由</div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;">
                <div style="padding:12px;background:var(--bg-secondary);border-radius:8px;border-left:3px solid var(--red);">
                    <div style="font-weight:600;margin-bottom:6px;color:var(--red);">利好因素</div>
                    <ul style="font-size:13px;line-height:1.8;padding-left:16px;">
                        ${r.reasons_bull.map(r => `<li>${r}</li>`).join('') || '<li>暂无</li>'}
                    </ul>
                </div>
                <div style="padding:12px;background:var(--bg-secondary);border-radius:8px;border-left:3px solid var(--green);">
                    <div style="font-weight:600;margin-bottom:6px;color:var(--green);">风险提示</div>
                    <ul style="font-size:13px;line-height:1.8;padding-left:16px;">
                        ${r.reasons_bear.map(r => `<li>${r}</li>`).join('') || '<li>暂无</li>'}
                    </ul>
                </div>
            </div>
        </div>`;

        // 新闻
        if (newsData.success && newsData.data && newsData.data.length > 0) {
            html += `
            <div class="analysis-section">
                <div class="section-title">📰 相关新闻</div>
                ${newsData.data.slice(0, 5).map(n => `
                    <div class="news-item">
                        <div class="news-title">${n.title}</div>
                        <div class="news-meta"><span>${n.source || ''}</span><span>${n.date || ''}</span></div>
                        <div class="news-content">${n.content || ''}</div>
                    </div>
                `).join('')}
            </div>`;
        }

        // 风险提示
        html += `
        <div class="analysis-section">
            <div style="padding:12px;background:rgba(248,81,73,0.08);border-radius:8px;border:1px solid rgba(248,81,73,0.3);font-size:12px;color:var(--text-secondary);">
                ⚠️ 风险提示：以上分析基于技术指标量化模型，仅供参考，不构成投资建议。股市有风险，投资需谨慎。T+1交易模式下，当日买入次日方可卖出，请合理安排仓位。
            </div>
        </div>`;

        body.innerHTML = html;

        // 渲染K线图
        renderKlineChart(a.kline_data || []);

    } catch (e) {
        body.innerHTML = '<div class="loading">分析加载失败，请重试</div>';
        console.error(e);
    }
}

function closeModal() {
    document.getElementById('stockModal').classList.remove('active');
    if (klineChart) { klineChart.dispose(); klineChart = null; }
}

document.getElementById('stockModal').addEventListener('click', (e) => {
    if (e.target === e.currentTarget) closeModal();
});

// ========== K线图渲染 ==========
function renderKlineChart(klineData) {
    const chartEl = document.getElementById('klineChart');
    if (!chartEl || klineData.length === 0) return;

    klineChart = echarts.init(chartEl);

    const dates = klineData.map(d => d.date);
    const ohlc = klineData.map(d => [d.open, d.close, d.low, d.high]);
    const volumes = klineData.map(d => d.volume);

    // 计算MA线
    function calcMA(data, n) {
        const result = [];
        for (let i = 0; i < data.length; i++) {
            if (i < n - 1) { result.push(null); continue; }
            let sum = 0;
            for (let j = 0; j < n; j++) sum += data[i - j].close;
            result.push((sum / n).toFixed(2));
        }
        return result;
    }

    const ma5 = calcMA(klineData, 5);
    const ma10 = calcMA(klineData, 10);
    const ma20 = calcMA(klineData, 20);

    const option = {
        backgroundColor: 'transparent',
        tooltip: {
            trigger: 'axis',
            axisPointer: { type: 'cross' },
            backgroundColor: 'rgba(22,27,34,0.95)',
            borderColor: '#30363d',
            textStyle: { color: '#e6edf3' }
        },
        legend: {
            data: ['K线', 'MA5', 'MA10', 'MA20'],
            textStyle: { color: '#8b949e' },
            top: 0
        },
        grid: [
            { left: '8%', right: '4%', top: '8%', height: '55%' },
            { left: '8%', right: '4%', top: '70%', height: '20%' }
        ],
        xAxis: [
            { type: 'category', data: dates, scale: true, boundaryGap: false,
              axisLine: { lineStyle: { color: '#30363d' } },
              axisLabel: { color: '#8b949e', fontSize: 10 } },
            { type: 'category', gridIndex: 1, data: dates, scale: true,
              axisLabel: { show: false } }
        ],
        yAxis: [
            { scale: true, splitLine: { lineStyle: { color: '#30363d' } },
              axisLabel: { color: '#8b949e' } },
            { gridIndex: 1, splitNumber: 2,
              axisLabel: { color: '#8b949e', fontSize: 10 },
              splitLine: { show: false } }
        ],
        series: [
            { name: 'K线', type: 'candlestick', data: ohlc,
              itemStyle: {
                  color: '#f85149', color0: '#3fb950',
                  borderColor: '#f85149', borderColor0: '#3fb950'
              } },
            { name: 'MA5', type: 'line', data: ma5, smooth: true,
              lineStyle: { width: 1, color: '#e6edf3' }, showSymbol: false },
            { name: 'MA10', type: 'line', data: ma10, smooth: true,
              lineStyle: { width: 1, color: '#58a6ff' }, showSymbol: false },
            { name: 'MA20', type: 'line', data: ma20, smooth: true,
              lineStyle: { width: 1, color: '#d29922' }, showSymbol: false },
            { name: '成交量', type: 'bar', xAxisIndex: 1, yAxisIndex: 1, data: volumes,
              itemStyle: { color: (params) => {
                  const idx = params.dataIndex;
                  return klineData[idx].close >= klineData[idx].open ? '#f85149' : '#3fb950';
              }, opacity: 0.6 } }
        ]
    };

    klineChart.setOption(option);
    window.addEventListener('resize', () => { if (klineChart) klineChart.resize(); });
}

// ========== 搜索功能（代码/名称/拼音首字母） ==========
const SEARCH_API = '/api/search';

document.getElementById('searchBtn').addEventListener('click', searchStock);
document.getElementById('searchInput').addEventListener('input', onSearchInput);
document.getElementById('searchInput').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
        const items = document.querySelectorAll('.search-dropdown-item');
        if (items.length > 0) {
            items[0].click();
        } else {
            searchStock();
        }
    } else if (e.key === 'Escape') {
        hideSearchDropdown();
    }
});
document.addEventListener('click', (e) => {
    if (!e.target.closest('.search-box')) hideSearchDropdown();
});

function onSearchInput() {
    const q = document.getElementById('searchInput').value.trim();
    clearTimeout(window._searchDebounce);
    if (!q) {
        hideSearchDropdown();
        return;
    }
    window._searchDebounce = setTimeout(() => doSearch(q), 200);
}

async function doSearch(q) {
    try {
        const data = await fetchJSON(`${SEARCH_API}?q=${encodeURIComponent(q)}`);
        if (data.success && data.data) {
            renderSearchDropdown(data.data, q);
        }
    } catch (e) {
        console.error('搜索失败:', e);
    }
}

function renderSearchDropdown(results, query) {
    const dropdown = document.getElementById('searchDropdown');
    if (results.length === 0) {
        dropdown.innerHTML = `<div class="search-dropdown-empty">未找到匹配的股票<br><small>试试拼音首字母，如 gzmt=贵州茅台</small></div>`;
        dropdown.style.display = 'block';
        return;
    }
    const matchLabels = { code: '代码', name: '名称', pinyin: '拼音', pinyin_full: '全拼' };
    dropdown.innerHTML = results.map(r => {
        const marketClass = r.market === 'etf' ? 'etf' : r.market === 'hk' ? 'hk' : '';
        return `<div class="search-dropdown-item" onclick="onSearchResultClick('${r.code}', '${r.name}', '${r.market}')">
            <span class="sdd-code">${r.code}</span>
            <span class="sdd-name">${r.name}</span>
            <span class="sdd-market ${marketClass}">${r.market_name}</span>
            <span class="sdd-match">${matchLabels[r.match_type] || ''}</span>
        </div>`;
    }).join('');
    dropdown.style.display = 'block';
}

function onSearchResultClick(code, name, market) {
    hideSearchDropdown();
    document.getElementById('searchInput').value = '';
    // 港股和ETF使用AI分析弹窗，A股用普通分析弹窗
    if (market === 'a') {
        openStockDetail(code, name);
    } else {
        openAIAnalysis(code, name, market);
    }
}

function hideSearchDropdown() {
    document.getElementById('searchDropdown').style.display = 'none';
}

async function searchStock() {
    const query = document.getElementById('searchInput').value.trim();
    if (!query) return;
    try {
        const data = await fetchJSON(`${SEARCH_API}?q=${encodeURIComponent(query)}`);
        if (data.success && data.data && data.data.length > 0) {
            const s = data.data[0];
            onSearchResultClick(s.code, s.name, s.market);
        } else {
            alert('未找到匹配的股票，试试拼音首字母（如 gzmt=贵州茅台）');
        }
    } catch (e) {
        alert('搜索失败');
    }
}

// ========== 初始化 ==========
loadMarketOverview();
loadRecommendations();

/* ============================================================
 * AI 智能选股功能
 * ============================================================ */

let aiScanning = false;
let aiMarket = 'a';           // 当前AI选股市场 a/etf/hk
let aiMarketInfo = null;      // 当前市场信息
let aiBoardList = [];         // 行业板块列表缓存
let aiProgressState = { pct: 0, elapsed: 0 };  // 进度条状态（供时间预估）

// ========== AI状态与初始化 ==========
async function loadAIStatus() {
    try {
        const data = await fetchJSON(API.aiStatus);
        const s = data.data;
        const icon = document.getElementById('aiStatusIcon');
        const text = document.getElementById('aiStatusText');
        if (s.available) {
            icon.textContent = '🤖';
            text.textContent = `AI服务已启用：${s.provider_name} / ${s.model}`;
        } else if (s.enabled && s.has_api_key) {
            icon.textContent = '⚠️';
            text.textContent = `AI配置已保存但连接异常：${s.reason || ''}`;
        } else {
            icon.textContent = '🧠';
            text.textContent = `${s.reason || '未启用AI'} — 当前使用内置规则引擎分析，配置API Key后启用AI深度解读`;
        }
    } catch (e) {
        console.error('AI状态获取失败:', e);
    }
}

// ========== 市场切换 ==========
async function loadAIMarkets() {
    const tabsEl = document.getElementById('aiMarketTabs');
    try {
        const data = await fetchJSON(API.aiMarkets);
        if (!data.success || !data.data || data.data.length === 0) {
            tabsEl.innerHTML = '<div class="loading" style="padding:2px;">暂无市场</div>';
            return;
        }
        window._aiMarkets = data.data;
        const current = window._aiMarkets.find(m => m.key === aiMarket);
        tabsEl.innerHTML = data.data.map(m => `
            <button class="ai-market-tab ${m.key === aiMarket ? 'active' : ''}" data-market="${m.key}" onclick="switchAIMarket('${m.key}')">
                ${m.name}<small>${m.pool_size}只</small>
            </button>
        `).join('');
        updateMarketDesc(current);
    } catch (e) {
        tabsEl.innerHTML = '<div class="loading" style="padding:2px;">市场加载失败</div>';
        console.error('市场列表加载失败:', e);
    }
}

function updateMarketDesc(marketInfo) {
    const info = marketInfo || (window._aiMarkets || []).find(m => m.key === aiMarket);
    const el = document.getElementById('aiMarketDesc');
    if (info) {
        el.textContent = `${info.desc} · 股票池 ${info.pool_size}只`;
    }
}

async function switchAIMarket(market) {
    if (aiMarket === market) return;
    aiMarket = market;
    aiMarketInfo = (window._aiMarkets || []).find(m => m.key === market) || null;

    document.querySelectorAll('.ai-market-tab').forEach(t => {
        t.classList.toggle('active', t.dataset.market === market);
    });
    updateMarketDesc(aiMarketInfo);
    toggleAIBoardVisibility();
    document.getElementById('aiCacheTag').style.display = 'none';

    const el = document.getElementById('aiRecommendList');
    el.innerHTML = `<div class="loading">正在加载${aiMarketInfo ? aiMarketInfo.name : '该市场'}推荐，请稍候...</div>`;
    loadAIRecommendations(false);
}

async function loadAIQuickPool() {
    const el = document.getElementById('aiQuickPool');
    try {
        const data = await fetchJSON(API.quotes + '?page=1&per_page=8');
        if (!data.success || !data.data || data.data.length === 0) {
            el.innerHTML = '<div class="loading">暂无数据</div>';
            return;
        }
        el.innerHTML = data.data.map(s => `
            <div class="ai-pool-item" onclick="openAIAnalysis('${s.code}', '${s.name}', 'a')">
                <div class="ai-pool-name">${s.name}</div>
                <div class="ai-pool-meta">
                    <span>${s.code}</span>
                    <span class="${fmtColor(s.pct_change)}">${fmtPct(s.pct_change)}</span>
                </div>
            </div>
        `).join('');
    } catch (e) {
        el.innerHTML = '<div class="loading">加载失败</div>';
    }
}

function initAIView() {
    if (window._aiInited) return;
    window._aiInited = true;
    loadAIStatus();
    loadAIMarkets();
    loadAIQuickPool();
    loadAIBoards();
    bindAIFilterMutex();
    toggleAIBoardVisibility();
}

// ========== AI推荐列表 ==========
function readAIFilters() {
    const g = id => document.getElementById(id);
    const board = (g('aiBoardInput')?.value || '').trim();
    const codes = (g('aiCodesInput')?.value || '').trim();
    const aiMin = g('aiMinScore')?.value || '';
    return { board, codes, aiMin };
}

async function loadAIRecommendations(force) {
    const filters = readAIFilters();
    const hasFilter = !!(filters.board || filters.codes);
    // 带筛选条件 或 强制重新扫描 → SSE 流式（带进度条）；否则走缓存 JSON
    if (force || hasFilter) {
        return runAIScanStream(filters);
    }
    return loadAICached();
}

// ---------- 缓存模式（无筛选时刷新缓存用） ----------
async function loadAICached() {
    if (aiScanning) return;
    aiScanning = true;
    const btn = document.getElementById('btnAiScan');
    btn.disabled = true;
    btn.textContent = '⏳ 扫描中...';

    const el = document.getElementById('aiRecommendList');
    document.getElementById('aiCacheTag').style.display = 'none';

    try {
        const data = await fetchJSON(API.aiRecommendations(12, 0, aiMarket), 120000);
        if (!data.success) {
            el.innerHTML = '<div class="loading">AI选股失败</div>';
            return;
        }
        if (data.cached) {
            document.getElementById('aiCacheTag').style.display = 'inline';
        }
        renderAIRecommendations(el, data.data || []);
    } catch (e) {
        el.innerHTML = '<div class="loading">扫描失败，请稍后重试</div>';
        console.error(e);
    } finally {
        aiScanning = false;
        btn.disabled = false;
        btn.textContent = '🚀 开始AI选股';
    }
}

// ---------- 流式模式（SSE，带筛选或强制扫描） ----------
async function runAIScanStream(filters) {
    if (aiScanning) return;
    aiScanning = true;
    const btn = document.getElementById('btnAiScan');
    btn.disabled = true;
    btn.textContent = '⏳ 扫描中...';

    const el = document.getElementById('aiRecommendList');
    document.getElementById('aiCacheTag').style.display = 'none';
    el.innerHTML = '<div class="loading" id="aiLoading"></div>';
    showAIProgress();
    setAIProgress(3, '正在准备扫描...', 0);

    const params = { max: 12, ai: 1, market: aiMarket };
    if (filters.codes) params.codes = filters.codes;
    if (filters.board) params.board = filters.board;
    if (filters.aiMin !== '') params.ai_min = filters.aiMin;

    try {
        const doneEv = await streamAIRecommendations(params);
        hideAIProgress();
        renderAIRecommendations(el, doneEv.data || []);
    } catch (e) {
        hideAIProgress();
        el.innerHTML = `<div class="loading">${e.message || '扫描失败，请稍后重试'}</div>`;
        console.error(e);
    } finally {
        aiScanning = false;
        btn.disabled = false;
        btn.textContent = '🚀 开始AI选股';
    }
}

// ---------- SSE 流式请求（解析 progress/done/error 事件） ----------
function streamAIRecommendations(params) {
    return new Promise((resolve, reject) => {
        fetch(API.aiRecommendStream(params)).then(resp => {
            if (!resp.ok || !resp.body) {
                reject(new Error(`HTTP ${resp.status}`));
                return;
            }
            const reader = resp.body.getReader();
            const decoder = new TextDecoder();
            let buf = '';

            const pump = () => reader.read().then(({ done, value }) => {
                if (done) return;
                buf += decoder.decode(value, { stream: true });
                const lines = buf.split('\n');
                buf = lines.pop();
                for (const line of lines) {
                    const t = line.trim();
                    if (!t.startsWith('data:')) continue;
                    let ev;
                    try { ev = JSON.parse(t.slice(5)); } catch (_) { continue; }
                    if (ev.type === 'progress') onScanProgress(ev);
                    else if (ev.type === 'done') { resolve(ev); return; }
                    else if (ev.type === 'error') { reject(new Error(ev.error || '扫描失败')); return; }
                }
                pump();
            }).catch(err => reject(err));
            pump();
        }).catch(err => reject(err));
    });
}

// ---------- 进度条 ----------
const AI_STAGE_LABELS = { quotes: '拉取行情', score: '评分', ai: 'AI深度解读' };

function showAIProgress() {
    document.getElementById('aiProgressWrap').style.display = '';
}
function hideAIProgress() {
    document.getElementById('aiProgressWrap').style.display = 'none';
}

function setAIProgress(pct, message, elapsed) {
    aiProgressState = { pct, elapsed };
    document.getElementById('aiProgressBar').style.width = pct + '%';
    document.getElementById('aiProgressMsg').textContent = message;
    const stats = document.getElementById('aiProgressStats');
    if (elapsed == null) {
        stats.textContent = '';
        return;
    }
    let etaText = '计算中...';
    if (pct >= 3) {
        const total = elapsed / (pct / 100);
        const remain = total - elapsed;
        etaText = remain > 0 ? `约 ${Math.round(remain)}s` : '即将完成';
    }
    stats.textContent = `已用 ${Math.round(elapsed)}s · 预估剩余 ${etaText}`;
}

function onScanProgress(ev) {
    let pct = 5;
    if (ev.stage === 'quotes') {
        pct = 5;
    } else if (ev.stage === 'score') {
        pct = ev.total > 0 ? (ev.done / ev.total) * 55 + 5 : 5;
    } else if (ev.stage === 'ai') {
        pct = ev.total > 0 ? (ev.done / ev.total) * 35 + 60 : 60;
    }
    const label = AI_STAGE_LABELS[ev.stage] || ev.stage || '处理';
    setAIProgress(pct, `${label}：${ev.message || ''}`, ev.elapsed);
}

// ---------- 行业板块 ----------
async function loadAIBoards() {
    const tip = document.getElementById('aiFilterTip');
    try {
        const data = await fetchJSON(API.aiBoards);
        if (!data.success || !data.data) throw new Error('load failed');
        aiBoardList = data.data;
        const dl = document.getElementById('aiBoardList');
        dl.innerHTML = aiBoardList.map(b => `<option value="${b}"></option>`).join('');
        if (tip) tip.textContent = `已加载 ${aiBoardList.length} 个行业板块`;
    } catch (e) {
        if (tip) tip.textContent = '板块列表加载失败（数据源可能暂时不可用）';
        console.error('板块列表加载失败:', e);
    }
}

function bindAIFilterMutex() {
    const boardInput = document.getElementById('aiBoardInput');
    const codesInput = document.getElementById('aiCodesInput');
    if (!boardInput || !codesInput) return;
    boardInput.addEventListener('input', () => {
        if (boardInput.value.trim()) codesInput.value = '';
    });
    codesInput.addEventListener('input', () => {
        if (codesInput.value.trim()) boardInput.value = '';
    });
}

function toggleAIBoardVisibility() {
    const isA = aiMarket === 'a';
    const boardInput = document.getElementById('aiBoardInput');
    const btn = document.getElementById('btnRefreshBoards');
    if (boardInput) boardInput.style.display = isA ? '' : 'none';
    if (btn) btn.style.display = isA ? '' : 'none';
}

function renderAIRecommendations(el, list) {
    if (!list || list.length === 0) {
        el.innerHTML = '<div class="loading">暂无推荐，请点击「开始AI选股」</div>';
        return;
    }
    el.innerHTML = list.map(r => {
        const gradeClass = `ai-grade-${r.grade || 'C'}`;
        const signalClass = r.signal_type === 'buy' ? 'signal-buy' : r.signal_type === 'sell' ? 'signal-sell' : 'signal-hold';
        const dimColors = { tech: '#58a6ff', fund: '#3fb950', sent: '#d29922' };
        const fund = r.fund || {};
        const aiTag = r.ai_available ? 'AI深度解读' : '规则引擎解读';
        const marketTag = r.market && r.market !== 'a'
            ? `<span class="ai-market-tag">${r.market_name || r.market.toUpperCase()}</span>` : '';
        return `<div class="ai-recommend-item" onclick="openAIAnalysis('${r.code}', '${r.name}', '${r.market || aiMarket || 'a'}')">
            <div class="ai-score-badge ${gradeClass}">
                ${r.comprehensive_score}
                <small>${r.grade}级</small>
            </div>
            <div class="ai-rec-main">
                <div class="ai-rec-name">${r.name}<span class="ai-rec-code">${r.code}</span>${marketTag}</div>
                <div class="ai-dim-bars">
                    <span class="ai-dim-bar">技
                        <span class="ai-dim-track"><span class="ai-dim-fill" style="width:${r.scores.tech}%;background:${dimColors.tech};display:block;"></span></span>${r.scores.tech}
                    </span>
                    <span class="ai-dim-bar">基
                        <span class="ai-dim-track"><span class="ai-dim-fill" style="width:${r.scores.fund}%;background:${dimColors.fund};display:block;"></span></span>${r.scores.fund}
                    </span>
                    <span class="ai-dim-bar">情
                        <span class="ai-dim-track"><span class="ai-dim-fill" style="width:${r.scores.sent}%;background:${dimColors.sent};display:block;"></span></span>${r.scores.sent}
                    </span>
                </div>
                ${fund.pe ? `<div class="ai-fund-info">PE ${fund.pe}${fund.pb ? ` | PB ${fund.pb}` : ''}${fund.total_mv ? ` | 市值${fund.total_mv}亿` : ''}${fund.turnover_rate ? ` | 换手${fund.turnover_rate}%` : ''}</div>` : ''}
            </div>
            <div class="ai-rec-right">
                <div class="ai-rec-signal ${signalClass}">${r.signal}</div>
                <span class="ai-rec-action">${aiTag} →</span>
            </div>
        </div>`;
    }).join('');
}

// ========== AI深度分析弹窗（SSE流式） ==========
let aiModalStreamAborted = false;

async function openAIAnalysis(code, name, market) {
    market = market || aiMarket || 'a';
    const modal = document.getElementById('aiModal');
    const title = document.getElementById('aiModalTitle');
    const body = document.getElementById('aiModalBody');
    const scoresEl = document.getElementById('aiModalScores');
    const contentEl = document.getElementById('aiModalContent');
    const progressEl = document.getElementById('aiModalProgress');
    const progressText = document.getElementById('aiModalProgressText');

    title.textContent = `${name} (${code}) - AI深度解读`;
    scoresEl.style.display = 'none';
    scoresEl.innerHTML = '';
    contentEl.innerHTML = '<div class="loading">AI正在生成深度解读...</div>';
    progressEl.classList.remove('done');
    progressEl.innerHTML = '<span class="spinner"></span><span id="aiModalProgressText">连接中...</span>';
    modal.classList.add('active');

    aiModalStreamAborted = false;

    try {
        const resp = await fetch(API.aiStream(code, name, market));
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        if (!resp.body) throw new Error('浏览器不支持流式读取');

        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let buf = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done || aiModalStreamAborted) break;
            buf += decoder.decode(value, { stream: true });

            // 按SSE事件分割
            let idx;
            while ((idx = buf.indexOf('\n\n')) >= 0) {
                const event = buf.slice(0, idx);
                buf = buf.slice(idx + 2);
                handleAIStreamEvent(event, scoresEl, contentEl, progressEl, progressText);
            }
        }

        progressEl.classList.add('done');
        progressEl.innerHTML = '<span>✅ 分析完成</span>';
    } catch (e) {
        progressEl.classList.add('done');
        progressEl.innerHTML = '<span>❌ 分析中断</span>';
        contentEl.innerHTML = contentEl.innerHTML || '<div class="loading">加载失败</div>';
        console.error(e);
    }
}

function handleAIStreamEvent(event, scoresEl, contentEl, progressEl, progressText) {
    // 解析 event 行和 data 行
    const lines = event.split('\n');
    let evName = 'message';
    let dataStr = '';
    for (const line of lines) {
        if (line.startsWith('event:')) evName = line.substring(6).trim();
        else if (line.startsWith('data:')) dataStr += line.substring(5).trim();
    }
    if (!dataStr) return;

    let data;
    try { data = JSON.parse(dataStr); } catch (e) { return; }

    switch (evName) {
        case 'progress':
            progressText.textContent = data.msg || '';
            break;
        case 'scores_update':
            scoresEl.style.display = 'grid';
            const gradeClass = `ai-grade-${data.grade || 'C'}`;
            scoresEl.innerHTML = `
                <div class="ai-score-card"><div class="as-label">综合评分</div>
                    <div class="as-value" style="color:var(--accent);">${data.total}</div>
                    <div class="as-sub">${data.grade}级 · ${data.grade_label}</div></div>
                <div class="ai-score-card"><div class="as-label">技术面</div>
                    <div class="as-value" style="color:#58a6ff;">${data.tech}</div></div>
                <div class="ai-score-card"><div class="as-label">基本面</div>
                    <div class="as-value" style="color:#3fb950;">${data.fund}</div></div>
                <div class="ai-score-card"><div class="as-label">情绪面</div>
                    <div class="as-value" style="color:#d29922;">${data.sent}</div></div>`;
            break;
        case 'ai_stream':
            if (contentEl.innerHTML === '<div class="loading">AI正在生成深度解读...</div>') {
                contentEl.innerHTML = '';
            }
            contentEl.innerHTML += data.chunk || '';
            // 保留滚动位置
            contentEl.scrollTop = contentEl.scrollHeight;
            break;
        case 'final_result':
            progressText.textContent = `信号: ${data.signal}（AI: ${data.ai.available ? '已启用' : '规则引擎'}）`;
            break;
        case 'error':
            contentEl.innerHTML += `\n\n⚠️ 错误: ${data.msg || ''}`;
            break;
    }
}

function closeAIModal() {
    aiModalStreamAborted = true;
    document.getElementById('aiModal').classList.remove('active');
}

document.getElementById('aiModal').addEventListener('click', (e) => {
    if (e.target === e.currentTarget) closeAIModal();
});

// ========== AI设置面板 ==========
let aiProviderCache = {};

async function openAISettings() {
    const modal = document.getElementById('aiSettingsModal');
    modal.classList.add('active');
    document.getElementById('aiTestResult').textContent = '';

    try {
        const [cfgData, provData] = await Promise.all([
            fetchJSON(API.aiConfig),
            fetchJSON(API.aiProviders)
        ]);
        const cfg = cfgData.data;
        aiProviderCache = provData.data;

        const provSelect = document.getElementById('aiProvider');
        provSelect.innerHTML = Object.entries(aiProviderCache).map(([key, p]) =>
            `<option value="${key}" ${key === cfg.provider ? 'selected' : ''}>${p.name}${p.local ? '（本地）' : ''}</option>`
        ).join('');

        applyProviderUI(cfg.provider, cfg);
        document.getElementById('aiApiKey').value = '';
        document.getElementById('aiBaseUrl').value = cfg.base_url || '';
        document.getElementById('aiEnabled').checked = !!cfg.enabled;
    } catch (e) {
        console.error('加载AI配置失败:', e);
    }
}

// 根据提供商应用 UI（no_key 隐藏API Key、动态模型、提示文案）
function applyProviderUI(provider, cfg) {
    const p = aiProviderCache[provider] || {};
    const isNoKey = !!(p.no_key || cfg.no_key);
    const keyGroup = document.getElementById('aiKeyGroup');
    const providerHint = document.getElementById('aiProviderHint');

    if (isNoKey) {
        keyGroup.style.display = 'none';
        providerHint.textContent = p.hint || `本地模型（${p.name}），无需API Key`;
    } else {
        keyGroup.style.display = '';
        document.getElementById('aiKeyHint').textContent = cfg.has_api_key
            ? `已配置Key：${cfg.api_key_masked}（留空则保持不变）` : '未配置';
        providerHint.textContent = p.hint || 'OpenAI 兼容接口，填入你的 API Key';
    }

    // 模型：优先用 config 返回的动态列表（ollama 已自动拉取），否则用提供商内置列表
    const models = (cfg.models && cfg.models.length) ? cfg.models : (p.models || []);
    updateAIModels(provider, cfg.model || models[0] || '', models);
}

function updateAIModels(provider, selectedModel, modelsOverride) {
    const p = aiProviderCache[provider];
    const modelSelect = document.getElementById('aiModel');
    const models = modelsOverride || (p ? (p.models || []) : []);
    if (models.length === 0) {
        modelSelect.innerHTML = '<option value="">暂无模型</option>';
        return;
    }
    modelSelect.innerHTML = models.map(m =>
        `<option value="${m}" ${m === selectedModel ? 'selected' : ''}>${m}</option>`
    ).join('');
}

async function onProviderChange() {
    const prov = document.getElementById('aiProvider').value;
    const p = aiProviderCache[prov];
    if (!p) return;
    document.getElementById('aiBaseUrl').value = p.base_url;
    // 先按内置列表渲染（含 no_key/hint 处理）
    applyProviderUI(prov, { models: p.models || [], has_api_key: false, model: (p.models || [])[0] });
    // ollama 等本地模型动态拉取模型列表
    if (p.local || prov === 'ollama') {
        try {
            const res = await fetchJSON(API.aiModels(p.base_url));
            if (res.success && res.data && res.data.length > 0) {
                updateAIModels(prov, res.data[0], res.data);
            }
        } catch (e) {
            console.error('拉取本地模型列表失败:', e);
        }
    }
}

async function saveAISettings() {
    const provider = document.getElementById('aiProvider').value;
    const p = aiProviderCache[provider] || {};
    const payload = {
        enabled: document.getElementById('aiEnabled').checked,
        provider: provider,
        model: document.getElementById('aiModel').value,
        base_url: document.getElementById('aiBaseUrl').value.trim(),
        api_key: document.getElementById('aiApiKey').value.trim()
    };
    // 无需API Key的提供商（如本地Ollama）显式清空历史key
    if (p.no_key) payload.clear_key = true;
    try {
        const res = await fetch(API.aiConfig, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (data.success) {
            document.getElementById('aiTestResult').textContent = '✅ 配置已保存';
            document.getElementById('aiTestResult').style.color = 'var(--green)';
            loadAIStatus();
        } else {
            document.getElementById('aiTestResult').textContent = '❌ 保存失败';
            document.getElementById('aiTestResult').style.color = 'var(--red)';
        }
    } catch (e) {
        document.getElementById('aiTestResult').textContent = '❌ 保存出错';
        document.getElementById('aiTestResult').style.color = 'var(--red)';
    }
}

async function testAIConnection() {
    const el = document.getElementById('aiTestResult');
    el.textContent = '⏳ 测试中...';
    el.style.color = 'var(--text-secondary)';
    // 先保存当前配置再测试
    await saveAISettings();
    try {
        const data = await fetchJSON(API.aiStatus);
        const s = data.data;
        if (s.available) {
            el.textContent = '✅ 连接成功！AI深度解读已启用';
            el.style.color = 'var(--green)';
        } else {
            el.textContent = `⚠️ ${s.reason || '连接失败'}`;
            el.style.color = 'var(--gold)';
        }
    } catch (e) {
        el.textContent = '❌ 无法获取AI状态';
        el.style.color = 'var(--red)';
    }
}

function closeAISettings() {
    document.getElementById('aiSettingsModal').classList.remove('active');
}

document.getElementById('aiSettingsModal').addEventListener('click', (e) => {
    if (e.target === e.currentTarget) closeAISettings();
});

// ==================== 选股策略参数 ====================

const STRATEGY_GROUP_TITLES = {
    weights: '三维度权重',
    technical: '技术面参数',
    fundamental: '基本面参数',
    sentiment: '情绪面参数',
    signal: '信号判定阈值'
};

let _strategyLabels = null;

async function openStrategyParams() {
    const modal = document.getElementById('strategyParamsModal');
    modal.classList.add('active');
    const form = document.getElementById('strategyParamsForm');
    form.innerHTML = '<div class="loading">加载参数中...</div>';
    try {
        const data = await fetchJSON('/api/strategy/params');
        if (!data.success) throw new Error(data.error || '加载失败');
        _strategyLabels = data.labels || {};
        renderStrategyForm(data.data);
        updateWeightBar(data.data.weights);
    } catch (e) {
        form.innerHTML = `<div class="loading">加载失败: ${e.message}</div>`;
    }
}

function renderStrategyForm(params) {
    const form = document.getElementById('strategyParamsForm');
    const html = [];
    for (const [group, values] of Object.entries(params)) {
        if (typeof values !== 'object') continue;
        html.push(`<div style="margin-bottom:14px;">` +
            `<div style="font-weight:600;margin-bottom:6px;color:var(--text-primary);">` +
            `${STRATEGY_GROUP_TITLES[group] || group}</div>`);
        for (const [key, val] of Object.entries(values)) {
            const label = (_strategyLabels[group] || {})[key] || `${group}.${key}`;
            const isWeight = group === 'weights';
            const step = isWeight ? 0.05 : (Number.isInteger(val) ? 1 : 0.1);
            html.push(
                `<div class="settings-group" style="display:flex;align-items:center;gap:10px;margin-bottom:4px;">` +
                `<label class="settings-label" style="margin:0;flex:1;font-weight:400;">${label}</label>` +
                `<input type="number" class="settings-input" style="width:110px;" step="${step}" ` +
                `id="sp-${group}-${key}" value="${val}">` +
                `</div>`);
        }
        html.push('</div>');
    }
    form.innerHTML = html.join('');
}

function collectStrategyForm() {
    const result = {};
    document.querySelectorAll('#strategyParamsForm input[type=number]').forEach(inp => {
        const id = inp.id;  // sp-group-key
        const rest = id.slice(3);
        const idx = rest.indexOf('-');
        const group = rest.slice(0, idx);
        const key = rest.slice(idx + 1);
        const v = parseFloat(inp.value);
        if (isNaN(v)) return;
        (result[group] = result[group] || {})[key] = v;
    });
    return result;
}

async function saveStrategyParams() {
    const el = document.getElementById('strategySaveResult');
    el.textContent = '保存中...';
    el.style.color = 'var(--text-secondary)';
    try {
        const payload = collectStrategyForm();
        const resp = await fetch('/api/strategy/params', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(payload)
        });
        const data = await resp.json();
        if (!data.success) throw new Error(data.error || '保存失败');
        el.textContent = '✅ 已保存';
        el.style.color = 'var(--green)';
        updateWeightBar(data.data.weights);
    } catch (e) {
        el.textContent = `❌ ${e.message}`;
        el.style.color = 'var(--red)';
    }
}

async function resetStrategyParams() {
    const el = document.getElementById('strategySaveResult');
    try {
        const resp = await fetch('/api/strategy/params', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({__reset__: true})
        });
        const data = await resp.json();
        if (!data.success) throw new Error(data.error || '重置失败');
        renderStrategyForm(data.data);
        updateWeightBar(data.data.weights);
        el.textContent = '✅ 已恢复默认';
        el.style.color = 'var(--green)';
    } catch (e) {
        el.textContent = `❌ ${e.message}`;
        el.style.color = 'var(--red)';
    }
}

function updateWeightBar(weights) {
    const bar = document.getElementById('aiWeightBar');
    if (!bar || !weights) return;
    const sum = (weights.technical + weights.fundamental + weights.sentiment) || 1;
    const items = [
        {name: '技术面', v: weights.technical, color: '#58a6ff'},
        {name: '基本面', v: weights.fundamental, color: '#3fb950'},
        {name: '情绪面', v: weights.sentiment, color: '#d29922'}
    ];
    bar.innerHTML = items.map(it => {
        const pct = Math.round(it.v / sum * 100);
        return `<div class="weight-item" style="flex:${pct};">` +
            `<span class="weight-label">${it.name} ${pct}%</span>` +
            `<div class="weight-track"><div class="weight-fill" style="width:${pct}%;background:${it.color};"></div></div>` +
            `</div>`;
    }).join('');
}

function closeStrategyParams() {
    document.getElementById('strategyParamsModal').classList.remove('active');
}

document.getElementById('strategyParamsModal').addEventListener('click', (e) => {
    if (e.target === e.currentTarget) closeStrategyParams();
});

// 页面加载时同步权重显示
(async function initWeightBar() {
    try {
        const data = await fetchJSON('/api/strategy/params');
        if (data.success) updateWeightBar(data.data.weights);
    } catch (e) { /* 使用静态默认 */ }
})();
