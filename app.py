# -*- coding: utf-8 -*-
"""
Flask Backend - 量化交易分析系统后端
提供A股行情、技术分析、选股推荐、新闻等API
"""
from flask import Flask, render_template, jsonify, request, Response, stream_with_context
import logging
import threading
import time
import json
from data_fetcher import DataFetcher
from analysis_engine import AnalysisEngine
from recommendation_engine import RecommendationEngine
from ai_recommendation_engine import AIRecommendationEngine
from ai_client import get_ai_config, update_ai_config, load_config

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__, template_folder='templates', static_folder='static')

fetcher = DataFetcher()
analyzer = AnalysisEngine()
recommender = RecommendationEngine(fetcher=fetcher, analyzer=analyzer)
ai_recommender = AIRecommendationEngine(fetcher=fetcher, analyzer=analyzer)

# 全局缓存
_market_cache = {'data': None, 'time': 0}
_recommend_cache = {'data': None, 'time': 0}
_ai_recommend_cache = {'data': None, 'time': 0}


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/market/overview')
def market_overview():
    """市场概览：指数 + 涨幅榜 + 成交额榜"""
    try:
        indices = fetcher.get_index_data()
        hot = fetcher.get_hot_stocks()
        sectors = fetcher.get_sector_performance()
        return jsonify({
            'success': True,
            'indices': indices,
            'top_gainers': hot.get('top_gainers', []),
            'top_volume': hot.get('top_volume', []),
            'sectors': sectors[:10]
        })
    except Exception as e:
        logger.error(f"市场概览失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/market/quotes')
def market_quotes():
    """获取全部A股实时行情"""
    try:
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 50))
        search = request.args.get('search', '').strip()

        quotes = fetcher.get_realtime_quotes()

        if search:
            quotes = [q for q in quotes if search in q.get('code', '') or search in q.get('name', '')]

        total = len(quotes)
        start = (page - 1) * per_page
        end = start + per_page
        page_data = quotes[start:end]

        return jsonify({
            'success': True,
            'total': total,
            'page': page,
            'per_page': per_page,
            'data': page_data
        })
    except Exception as e:
        logger.error(f"获取行情失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/search')
def search_stocks():
    """全市场股票搜索：支持代码、名称、拼音首字母、全拼"""
    from data_fetcher import get_search_index
    q = request.args.get('q', '').strip().lower()
    if not q:
        return jsonify({'success': True, 'data': []})

    results = []
    for item in get_search_index():
        code = item['code']
        name = item['name']
        initials = item['pinyin_initials']
        full = item['pinyin_full']

        matched = False
        match_type = ''

        # 优先级 1: 代码精确/前缀匹配
        if q in code.lower():
            matched = True
            match_type = 'code'
        # 优先级 2: 名称包含匹配
        elif q in name.lower():
            matched = True
            match_type = 'name'
        # 优先级 3: 拼音首字母匹配（前缀或包含）
        elif initials and (initials.startswith(q) or q in initials):
            matched = True
            match_type = 'pinyin'
        # 优先级 4: 全拼匹配（前缀）
        elif full and full.startswith(q):
            matched = True
            match_type = 'pinyin_full'

        if matched:
            market_name = {'a': 'A股', 'etf': 'ETF', 'hk': '港股'}.get(item['market'], '')
            results.append({
                'code': code,
                'name': name,
                'market': item['market'],
                'market_name': market_name,
                'match_type': match_type,
            })

    # 代码匹配优先，然后名称，然后拼音
    type_order = {'code': 0, 'name': 1, 'pinyin': 2, 'pinyin_full': 3}
    results.sort(key=lambda x: (type_order.get(x['match_type'], 9), x['code']))
    return jsonify({'success': True, 'data': results[:20]})


@app.route('/api/stock/<code>/analysis')
def stock_analysis(code):
    """获取个股技术分析"""
    try:
        name = request.args.get('name', '')
        result = recommender.analyze_single_stock(code, name)
        if result is None:
            return jsonify({'success': False, 'error': '无法获取该股票数据'}), 404

        return jsonify({'success': True, 'data': result})
    except Exception as e:
        logger.error(f"个股分析失败({code}): {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/stock/<code>/news')
def stock_news(code):
    """获取个股新闻"""
    try:
        news = fetcher.get_stock_news(code)
        return jsonify({'success': True, 'data': news})
    except Exception as e:
        logger.error(f"获取新闻失败({code}): {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/market/news')
def market_news():
    """获取市场财经新闻"""
    try:
        news = fetcher.get_market_news()
        return jsonify({'success': True, 'data': news})
    except Exception as e:
        logger.error(f"市场新闻失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/recommendations')
def recommendations():
    """获取量化选股推荐（带缓存，5分钟有效）"""
    global _recommend_cache
    now = time.time()
    if _recommend_cache['data'] and (now - _recommend_cache['time']) < 300:
        return jsonify({'success': True, 'data': _recommend_cache['data'],
                       'cached': True})

    try:
        logger.info("开始生成推荐...")
        results = recommender.get_top_recommendations(max_stocks=15)
        logger.info(f"推荐生成完成，共{len(results)}条结果")
        _recommend_cache['data'] = results
        _recommend_cache['time'] = now
        return jsonify({'success': True, 'data': results, 'cached': False})
    except Exception as e:
        logger.error(f"选股推荐失败: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/debug/scan')
def debug_scan():
    """调试扫描过程"""
    try:
        quotes = fetcher.get_realtime_quotes()
        logger.info(f"获取到{len(quotes)}条行情")
        valid = [q for q in quotes if -10 < q.get('pct_change', 0) < 11]
        top_g = sorted(valid, key=lambda x: x.get('pct_change', 0), reverse=True)[:5]
        results = []
        for s in top_g:
            logger.info(f"分析 {s['code']} {s['name']}...")
            r = recommender.analyze_single_stock(s['code'], s['name'])
            if r:
                results.append({'code': r['code'], 'name': r['name'], 'score': r['score'], 'signal': r['signal']})
                logger.info(f"  -> 评分{r['score']} {r['signal']}")
            else:
                logger.warning(f"  -> 分析返回None")
        return jsonify({'quotes_count': len(quotes), 'results': results})
    except Exception as e:
        logger.error(f"调试扫描失败: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/api/scan/full')
def full_scan():
    """完整市场扫描（耗时较长）"""
    try:
        max_stocks = int(request.args.get('max', 50))
        results = recommender.scan_market(max_stocks)
        return jsonify({'success': True, 'data': results, 'count': len(results)})
    except Exception as e:
        logger.error(f"全市场扫描失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/stock/<code>/history')
def stock_history(code):
    """获取个股K线历史数据"""
    try:
        days = int(request.args.get('days', 120))
        df = fetcher.get_stock_history(code, days)
        if df is None or df.empty:
            return jsonify({'success': False, 'error': '无数据'}), 404

        records = []
        for _, row in df.iterrows():
            date_str = row['date'].strftime('%Y-%m-%d') if hasattr(row['date'], 'strftime') else str(row['date'])[:10]
            records.append({
                'date': date_str,
                'open': float(row['open']),
                'close': float(row['close']),
                'high': float(row['high']),
                'low': float(row['low']),
                'volume': float(row['volume']),
                'pct_change': float(row.get('pct_change', 0))
            })

        return jsonify({'success': True, 'data': records})
    except Exception as e:
        logger.error(f"获取历史数据失败({code}): {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/health')
def health():
    return jsonify({'status': 'ok', 'service': 'quant-trader'})


# ==================== 选股策略参数API ====================

@app.route('/api/strategy/params', methods=['GET', 'POST'])
def strategy_params_api():
    """获取/更新选股策略参数（技术面/基本面/情绪面阈值与权重）"""
    from strategy_params import (get_strategy_params, update_strategy_params,
                                 PARAM_LABELS, DEFAULT_STRATEGY_PARAMS)
    if request.method == 'GET':
        return jsonify({'success': True, 'data': get_strategy_params(),
                        'labels': PARAM_LABELS,
                        'defaults': DEFAULT_STRATEGY_PARAMS})

    try:
        data = request.json or {}
        reset = bool(data.pop('__reset__', False))
        ok = update_strategy_params(data, reset=reset)
        if ok:
            # 参数变更后清空推荐缓存，使新评分立即生效
            global _recommend_cache, _ai_recommend_cache
            _recommend_cache = {'data': None, 'time': 0}
            _ai_recommend_cache = {'data': None, 'time': 0}
            return jsonify({'success': True, 'data': get_strategy_params(),
                            'message': '选股参数已保存'})
        return jsonify({'success': False, 'error': '保存失败'}), 500
    except Exception as e:
        logger.error(f"更新选股参数失败: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


# ==================== AI选股相关API ====================

@app.route('/api/ai/status')
def ai_status():
    """AI服务状态"""
    try:
        return jsonify({'success': True, 'data': ai_recommender.ai_client.status()})
    except Exception as e:
        logger.error(f"AI状态获取失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/ai/config', methods=['GET', 'POST'])
def ai_config():
    """获取/更新AI配置"""
    if request.method == 'GET':
        return jsonify({'success': True, 'data': get_ai_config()})

    try:
        data = request.json or {}
        ok = update_ai_config(data)
        if ok:
            return jsonify({'success': True, 'data': get_ai_config(),
                           'message': '配置已保存'})
        return jsonify({'success': False, 'error': '保存失败'}), 500
    except Exception as e:
        logger.error(f"更新AI配置失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/ai/providers')
def ai_providers():
    """支持的AI服务商列表"""
    from ai_client import AI_PROVIDERS
    data = {k: v for k, v in AI_PROVIDERS.items()}
    return jsonify({'success': True, 'data': data})


@app.route('/api/ai/models')
def ai_models():
    """动态拉取提供商模型列表（如本地Ollama模型）"""
    from ai_client import get_ollama_models
    base_url = request.args.get('base_url', '')
    models = get_ollama_models(base_url)
    return jsonify({'success': True, 'data': models})


@app.route('/api/ai/markets')
def ai_markets():
    """AI选股支持的市场列表"""
    from data_fetcher import MARKETS
    data = []
    for key, info in MARKETS.items():
        pool_size = len(fetcher.get_stock_list(key))
        data.append({'key': key, 'name': info['name'], 'desc': info['desc'], 'pool_size': pool_size})
    return jsonify({'success': True, 'data': data})


@app.route('/api/ai/stock/<code>/analysis')
def ai_stock_analysis(code):
    """AI综合个股分析"""
    try:
        name = request.args.get('name', '')
        market = request.args.get('market', 'a')
        use_ai = request.args.get('ai', '1') != '0'
        result = ai_recommender.analyze_stock(code, name, market=market, use_ai=use_ai)
        return jsonify({'success': True, 'data': result})
    except Exception as e:
        logger.error(f"AI个股分析失败({code}): {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/ai/recommendations')
def ai_recommendations():
    """AI智能选股推荐（带缓存，10分钟）"""
    market = request.args.get('market', 'a')
    market_cache_key = f"{market}_data"
    global _ai_recommend_cache
    now = time.time()
    if _ai_recommend_cache.get(market_cache_key) and (now - _ai_recommend_cache.get('time', 0)) < 600:
        return jsonify({'success': True, 'data': _ai_recommend_cache[market_cache_key],
                       'cached': True, 'market': market})

    try:
        use_ai = request.args.get('ai', '0') == '1'
        max_stocks = int(request.args.get('max', 12))
        logger.info(f"开始AI智能选股扫描 (market={market}, max={max_stocks}, ai={use_ai})...")
        results = ai_recommender.scan_market(max_stocks=max_stocks, use_ai=use_ai, market=market)
        # 精简返回，避免过大数据量
        summary = []
        for r in results:
            summary.append({
                'code': r['code'],
                'name': r['name'],
                'market': r.get('market', market),
                'market_name': r.get('market_name', market),
                'comprehensive_score': r['comprehensive_score'],
                'grade': r['grade'],
                'grade_label': r['grade_label'],
                'signal': r['signal'],
                'signal_type': r['signal_type'],
                'scores': r['scores'],
                'ai_available': r['ai'].get('available', False) if r.get('ai') else False,
                'fund': (r['fundamental'] or {}).get('data', {}) or {},
                'trend': (r['technical'] or {}).get('analysis', {}).get('trend', '') if r.get('technical') else ''
            })
        _ai_recommend_cache[market_cache_key] = summary
        _ai_recommend_cache['time'] = now
        return jsonify({'success': True, 'data': summary, 'cached': False,
                       'count': len(summary), 'ai_used': use_ai, 'market': market})
    except Exception as e:
        logger.error(f"AI选股失败: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/ai/stream/<code>')
def ai_stream_analysis(code):
    """AI流式分析（SSE）"""
    name = request.args.get('name', '')
    market = request.args.get('market', 'a')

    def generate():
        # 先推送开始事件
        yield "event: connected\ndata: {\"msg\": \"连接成功\"}\n\n"
        try:
            # 三维度评分
            yield "event: progress\ndata: {\"step\": \"tech\", \"msg\": \"正在计算技术指标...\"}\n\n"
            tech = ai_recommender.get_technical_score(code, name, market=market)

            yield "event: progress\ndata: {\"step\": \"fund\", \"msg\": \"正在分析基本面数据...\"}\n\n"
            fund = ai_recommender.get_fundamental_score(code, name, market=market)

            yield "event: progress\ndata: {\"step\": \"sent\", \"msg\": \"正在分析新闻情绪...\"}\n\n"
            sent = ai_recommender.get_sentiment_score(code, name, market=market)

            comp = ai_recommender.comprehensive_score(tech, fund, sent)
            yield "event: scores_update\ndata: " + json.dumps(comp, ensure_ascii=False) + "\n\n"

            # AI解读
            yield "event: progress\ndata: {\"step\": \"ai\", \"msg\": \"AI正在深度解读...\"}\n\n"

            prompt = ai_recommender.build_ai_prompt(code, name, tech, fund, sent, comp, market)
            client = ai_recommender.ai_client

            if client.is_available():
                ok, result = client.analyze_stock_stream(prompt)
                if ok:
                    for chunk in result:
                        yield f"event: ai_stream\ndata: {json.dumps({'chunk': chunk}, ensure_ascii=False)}\n\n"
                    final = {'available': True, 'model': load_config().get('ai', {}).get('model', '')}
                else:
                    fallback = ai_recommender.generate_rule_interpretation(code, name, tech, fund, sent, comp, market)
                    yield f"event: ai_stream\ndata: {json.dumps({'chunk': fallback}, ensure_ascii=False)}\n\n"
                    final = {'available': False, 'model': '规则引擎', 'ai_error': str(result)}
            else:
                fallback = ai_recommender.generate_rule_interpretation(code, name, tech, fund, sent, comp, market)
                yield f"event: ai_stream\ndata: {json.dumps({'chunk': fallback}, ensure_ascii=False)}\n\n"
                final = {'available': False, 'model': '规则引擎'}

            # 最终结果
            result_data = {
                'code': code, 'name': name, 'market': market,
                'comprehensive_score': comp['total'],
                'grade': comp['grade'], 'grade_label': comp['grade_label'],
                'signal': comp['signal'], 'signal_type': comp['signal_type'],
                'scores': {'tech': comp['tech'], 'fund': comp['fund'], 'sent': comp['sent'], 'total': comp['total']},
                'ai': final
            }
            yield f"event: final_result\ndata: {json.dumps(result_data, ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.error(f"AI流式分析失败({code}): {e}", exc_info=True)
            yield f"event: error\ndata: {json.dumps({'msg': str(e)}, ensure_ascii=False)}\n\n"
        finally:
            yield "event: done\ndata: {}\n\n"

    return Response(stream_with_context(generate()),
                    mimetype='text/event-stream',
                    headers={'Cache-Control': 'no-cache',
                             'X-Accel-Buffering': 'no'})


@app.route('/api/ai/backtest')
def ai_backtest():
    """回测最近N个交易日信号表现（简化版）"""
    try:
        code = request.args.get('code', '')
        name = request.args.get('name', '')
        days = int(request.args.get('days', 60))

        if not code:
            return jsonify({'success': False, 'error': '缺少code参数'}), 400

        df = fetcher.get_stock_history(code, days=days + 30)
        if df is None or df.empty or len(df) < 30:
            return jsonify({'success': False, 'error': '历史数据不足'}), 404

        import pandas as pd
        df = df.copy()
        from analysis_engine import AnalysisEngine
        df = AnalysisEngine.calc_ma(df, periods=[5, 20])
        signals = []  # (date, signal, price)
        for i in range(20, len(df), 20):
            row = df.iloc[i]
            if pd.isna(row.get('ma5')) or pd.isna(row.get('ma20')):
                continue
            prev = df.iloc[i - 1]
            buy = row['ma5'] > row['ma20'] and prev.get('ma5', 0) <= prev.get('ma20', 0)
            if buy:
                signals.append({'date': row['date'].strftime('%Y-%m-%d'), 'signal': '买入',
                               'price': round(float(row['close']), 2)})

        # 计算最后一笔买入到现在的收益
        stats = {'signal_count': len(signals)}
        if signals and len(df) > 1:
            last_entry = signals[-1]
            current_price = float(df.iloc[-1]['close'])
            # 找到该信号对应的bar
            entry_price = last_entry['price']
            stats['last_entry'] = last_entry
            stats['current_price'] = current_price
            stats['profit_pct'] = round((current_price - entry_price) / entry_price * 100, 2) if entry_price else 0
            stats['profit_text'] = f"{stats['profit_pct']:+.2f}%"

        # 近N日涨幅
        stats['days'] = len(df)
        first_close = float(df.iloc[0]['close'])
        last_close = float(df.iloc[-1]['close'])
        stats['period_return'] = round((last_close - first_close) / first_close * 100, 2) if first_close else 0

        return jsonify({'success': True, 'data': stats, 'signals': signals})
    except Exception as e:
        logger.error(f"回测失败({code}): {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5003, debug=False)
