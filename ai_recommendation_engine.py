# -*- coding: utf-8 -*-
"""
AI Recommendation Engine - AI综合选股引擎
综合评分与信号判定依据 DR-lin-eng/stock-scanner：
  - 综合评分 = 技术面(w) + 基本面(w) + 情绪面(w)，默认 0.4/0.4/0.2（可调）
  - 信号分级: ≥80且技术/基本面双强→强烈推荐买入；≥80→推荐买入；
    65-80且情绪≥60→建议买入；65-80→谨慎买入；45-65→持有观望；
    30-45→建议减仓；<30→建议卖出（阈值可调）
  - AI 深度解读：基于三维度数据生成自然语言买卖建议（保持不变）
  - AI 不可用时自动降级为规则引擎解读
"""
import json
import logging
import time

from analysis_engine import AnalysisEngine
from data_fetcher import DataFetcher
from fundamental_engine import FundamentalEngine
from sentiment_engine import SentimentEngine
from recommendation_engine import RecommendationEngine
from ai_client import get_ai_client, load_config
from strategy_params import get_strategy_params

logger = logging.getLogger(__name__)

# 市场名称
MARKET_NAMES = {'a': 'A股', 'etf': 'ETF', 'hk': '港股'}

# 评分分档
GRADE_LEVELS = [
    (80, 'A+', '极强'),
    (70, 'A', '优秀'),
    (60, 'B', '良好'),
    (50, 'C', '一般'),
    (0, 'D', '偏弱'),
]


def _grade(score):
    for threshold, grade, label in GRADE_LEVELS:
        if score >= threshold:
            return grade, label
    return 'D', '偏弱'


class AIRecommendationEngine:
    """AI综合选股引擎"""

    def __init__(self, fetcher=None, analyzer=None):
        self.fetcher = fetcher or DataFetcher()
        self.analyzer = analyzer or AnalysisEngine()
        self.rule_recommender = RecommendationEngine(fetcher=self.fetcher, analyzer=self.analyzer)
        self.fundamental_engine = FundamentalEngine(fetcher=self.fetcher)
        self.sentiment_engine = SentimentEngine(fetcher=self.fetcher)
        self.ai_client = get_ai_client()

    # ==================== 三维度评分 ====================

    def get_technical_score(self, code, name='', market='a'):
        """技术面分析（复用规则推荐引擎）"""
        result = self.rule_recommender.analyze_single_stock(code, name, market=market)
        if not result:
            return None
        return result

    def get_fundamental_score(self, code, name='', market='a'):
        """基本面分析"""
        return self.fundamental_engine.analyze(code, name, market=market)

    def get_sentiment_score(self, code, name='', market='a'):
        """情绪面分析"""
        return self.sentiment_engine.analyze(code, name, market=market)

    def comprehensive_score(self, tech, fund, sent):
        """综合加权评分（stock-scanner 权重与信号分级，参数可调）"""
        params = get_strategy_params()
        w = params['weights']
        sp = params['signal']

        tech_s = tech.get('score', 50) if tech else 50
        fund_s = fund.get('score', 50) if fund else 50
        sent_s = sent.get('score', 50) if sent else 50

        # 权重归一化（用户可自由调节，和不为1时按比例缩放）
        w_sum = (w['technical'] + w['fundamental'] + w['sentiment']) or 1.0
        total = round((tech_s * w['technical'] + fund_s * w['fundamental']
                       + sent_s * w['sentiment']) / w_sum, 1)
        total = max(0, min(100, total))
        grade, grade_label = _grade(total)

        # 信号判定（stock-scanner generate_recommendation 规则）
        if total >= sp['strong_buy']:
            if tech_s >= sp['strong_tech_min'] and fund_s >= sp['strong_fund_min']:
                signal, signal_type = "强烈推荐买入", "buy"
            else:
                signal, signal_type = "推荐买入", "buy"
        elif total >= sp['buy']:
            if sent_s >= sp['buy_sentiment_min']:
                signal, signal_type = "建议买入", "buy"
            else:
                signal, signal_type = "谨慎买入", "buy"
        elif total >= sp['hold']:
            signal, signal_type = "持有观望", "hold"
        elif total >= sp['sell']:
            signal, signal_type = "建议减仓", "sell"
        else:
            signal, signal_type = "建议卖出", "sell"

        return {
            'total': total,
            'grade': grade,
            'grade_label': grade_label,
            'tech': tech_s,
            'fund': fund_s,
            'sent': sent_s,
            'signal': signal,
            'signal_type': signal_type
        }

    # ==================== AI解读 ====================

    def build_ai_prompt(self, code, name, tech, fund, sent, comp, market='a'):
        """构建AI分析提示词"""
        t = tech.get('analysis', {}) if tech else {}
        points = tech.get('points', {}) if tech else {}
        market_name = MARKET_NAMES.get(market, market)

        # 市场特定规则
        market_note = {
            'a': 'A股实行T+1交易，涨跌幅限制主板10%/创业板科创板20%',
            'etf': '场内ETF为T+0或T+1交易（跨境/债券ETF为T+0），无涨跌幅限制（部分品种有±10%），价格跟随对应指数',
            'hk': '港股实行T+0回转交易（买入当天可卖）但资金T+2结算，无涨跌幅限制，注意汇率波动影响'
        }.get(market, '')

        lines = []
        lines.append(f"请分析{market_name}标的【{name}({code})】，当前综合评分{comp['total']}分（{comp['grade']}级，{comp['grade_label']}）。")
        lines.append(f"交易规则提示：{market_note}。")
        lines.append("")
        lines.append("## 技术面")
        if tech:
            lines.append(f"- 评分: {comp['tech']}/100，信号: {tech.get('signal', '')}")
            lines.append(f"- 现价: {t.get('close', '-')}，涨跌幅: {t.get('pct_change', 0):+.2f}%")
            lines.append(f"- 趋势: {t.get('trend', '-')}")
            lines.append(f"- MA5/MA10/MA20: {t.get('ma5', '-')} / {t.get('ma10', '-')} / {t.get('ma20', '-')}")
            if t.get('macd'):
                lines.append(f"- MACD: {t['macd'].get('signal', '-')} (DIF={t['macd'].get('dif', '-')}, "
                             f"DEA={t['macd'].get('dea', '-')}, 柱={t['macd'].get('macd', '-')})")
            if t.get('rsi'):
                lines.append(f"- RSI6: {t['rsi'].get('rsi6', '-')} ({t['rsi'].get('signal', '-')})")
            if t.get('kdj'):
                lines.append(f"- KDJ: K={t['kdj'].get('k', '-')}, D={t['kdj'].get('d', '-')}, J={t['kdj'].get('j', '-')} ({t['kdj'].get('signal', '-')})")
            if t.get('boll'):
                lines.append(f"- 布林带: {t['boll'].get('position', '-')} (上轨{t['boll'].get('upper', '-')} 中轨{t['boll'].get('mid', '-')} 下轨{t['boll'].get('lower', '-')})")
            if t.get('volume'):
                vol = t['volume']
                lines.append(f"- 量比: {vol.get('volume_ratio', '-')}，量价形态: {vol.get('pattern', '-')}，"
                             f"量能趋势: {vol.get('vol_trend', '-')}")
            if t.get('risk'):
                rk = t['risk']
                if rk.get('atr14') is not None:
                    lines.append(f"- 波动率: ATR14={rk['atr14']}（占现价{rk.get('atr_pct', '-')}%）")
                if rk.get('amplitude_max') is not None:
                    lines.append(f"- 近14日振幅: 最大{rk['amplitude_max']}% / 最小{rk['amplitude_min']}%")
                if rk.get('high_14d') is not None:
                    lines.append(f"- 近14日区间: 最高{rk['high_14d']} / 最低{rk['low_14d']}"
                                 f"（区间幅度{rk.get('range_pct_14d', '-')}%），最大成交量日: {rk.get('max_vol_date', '-')}")
            if t.get('support_resistance'):
                sr = t['support_resistance']
                sup = sr.get('support_levels') or []
                res = sr.get('resistance_levels') or []
                lines.append(f"- 压力位(由近到远): {res}，支撑位(由近到远): {sup}")
                lines.append(f"- 近期最高/最低: {sr.get('recent_high', '-')} / {sr.get('recent_low', '-')}")
            if points.get('strategy'):
                lines.append(f"- 规则引擎交易计划: {points['strategy']}")
            if tech.get('reasons_bull'):
                lines.append(f"- 技术利好: {'；'.join(tech['reasons_bull'][:3])}")
            if tech.get('reasons_bear'):
                lines.append(f"- 技术风险: {'；'.join(tech['reasons_bear'][:3])}")
        else:
            lines.append("- 技术数据获取失败")

        lines.append("")
        lines.append("## 基本面")
        if fund:
            lines.append(f"- 评分: {comp['fund']}/100，信号: {fund.get('signal', '')}")
            fd = fund.get('data', {})
            lines.append(f"- 市盈率(PE): {fd.get('pe', '-')}，市净率(PB): {fd.get('pb', '-')}")
            lines.append(f"- 总市值: {fd.get('total_mv', '-')}亿，换手率: {fd.get('turnover_rate', '-')}%")
            if fd.get('net_profit_yoy') is not None:
                lines.append(f"- 净利润同比: {fd['net_profit_yoy']}%")
            if fd.get('revenue_yoy') is not None:
                lines.append(f"- 营收同比: {fd['revenue_yoy']}%")
            if fd.get('roe') is not None:
                lines.append(f"- ROE: {fd['roe']}%")
            if fd.get('gross_margin') is not None:
                lines.append(f"- 毛利率: {fd['gross_margin']}%")
            if fd.get('debt_ratio') is not None:
                lines.append(f"- 资产负债率: {fd['debt_ratio']}%")
            if fund.get('reasons_bull'):
                lines.append(f"- 基本面亮点: {'；'.join(fund['reasons_bull'][:3])}")
            if fund.get('reasons_bear'):
                lines.append(f"- 基本面隐忧: {'；'.join(fund['reasons_bear'][:3])}")
        else:
            lines.append("- 基本面数据获取失败")

        lines.append("")
        lines.append("## 情绪面")
        if sent:
            lines.append(f"- 评分: {comp['sent']}/100，信号: {sent.get('signal', '')}")
            lines.append(f"- 近期新闻: {sent.get('news_count', 0)}条 (利好{sent.get('pos_count', 0)} / 利空{sent.get('neg_count', 0)})")
            if sent.get('reasons_bull'):
                lines.append(f"- 情绪亮点: {'；'.join(sent['reasons_bull'][:2])}")
            if sent.get('reasons_bear'):
                lines.append(f"- 情绪风险: {'；'.join(sent['reasons_bear'][:2])}")
        else:
            lines.append("- 情绪数据获取失败")

        lines.append("")
        lines.append("## 请严格按以下结构输出深度分析")
        lines.append("1. **趋势分析（支撑位与压力位）**: 先判断当前趋势性质（趋势延续/回调/反转，结合K线与均线说明依据）；"
                     "列出强压力位（第一压力）、次压力位、强支撑位（第一支撑）、次支撑位，每个价位注明依据（前高/密集成交区/均线/整数关口等）")
        lines.append("2. **成交量分析及其含义**: 量价特征（放量上涨/缩量回调等）、换手率与量能趋势的含义、变盘信号观察要点（放量突破/放量跌破的应对）")
        lines.append("3. **风险评估（波动率分析）**: 依据ATR及占比、近14日振幅、RSI位置、该市场涨跌幅规则与近期涨幅，给出风险等级（低/中/高/极高）及理由")
        lines.append("4. **短期和中期目标价位**: 短期（1-5个交易日）分乐观/中性/悲观三档目标价；中期（1-3个月）给出第一、第二目标价及条件")
        lines.append("5. **关键技术位分析**: 用markdown表格列出：强压力/次压力/强弱分界线/关键支撑/止损位，每行含价格和依据")
        lines.append("6. **具体交易建议（含止损位）**: 区分**持仓者**（激进策略/稳健策略）与**空仓者**（最佳买点及信号、突破买点及条件）；"
                     "明确止损位及执行纪律；仓位控制（单笔亏损占总资金比例上限、该标的最大仓位占比）")
        lines.append("7. **总结**: 一段话总结核心逻辑、关键价位与纪律要点")
        lines.append("")
        lines.append("注意：请结合该市场交易规则与上述数据给出建议，价位须与提供的数据吻合（压力/支撑参考已列出的档位），"
                     "不要凭空编造数据。输出使用markdown格式，全文控制在1200字以内。")
        return "\n".join(lines)

    def generate_rule_interpretation(self, code, name, tech, fund, sent, comp, market='a'):
        """规则引擎解读（AI不可用时的兜底方案）"""
        t = tech.get('analysis', {}) if tech else {}
        points = tech.get('points', {}) if tech else {}
        fd = fund.get('data', {}) if fund else {}
        market_name = MARKET_NAMES.get(market, market)

        parts = []
        # 综合研判
        parts.append(f"## 综合研判\n{name}({code})综合评分{comp['total']}分（{comp['grade']}级），"
                     f"技术面{comp['tech']}分、基本面{comp['fund']}分、情绪面{comp['sent']}分。")

        # 技术面简述
        trend = t.get('trend', '震荡')
        tech_desc = f"当前技术面呈「{trend}」状态"
        if t.get('macd'):
            tech_desc += f"，MACD{t['macd'].get('signal', '中性')}"
        if t.get('rsi') and t['rsi'].get('signal'):
            tech_desc += f"，RSI处于{t['rsi']['signal']}"
        parts.append(f"\n**技术面**: {tech_desc}。")
        if tech and tech.get('reasons_bull'):
            parts.append(f"主要利好：{'；'.join(tech['reasons_bull'][:2])}。")
        if tech and tech.get('reasons_bear'):
            parts.append(f"主要风险：{'；'.join(tech['reasons_bear'][:2])}。")

        # 基本面简述
        if fund:
            fund_parts = []
            if fd.get('pe'):
                fund_parts.append(f"PE {fd['pe']}")
            if fd.get('pb'):
                fund_parts.append(f"PB {fd['pb']}")
            if fd.get('total_mv'):
                fund_parts.append(f"市值{fd['total_mv']}亿")
            parts.append(f"\n**基本面**: {fund.get('signal', '')}（{'，'.join(fund_parts)}）。")
            if fund.get('reasons_bull'):
                parts.append(f"亮点：{'；'.join(fund['reasons_bull'][:2])}。")
            if fund.get('reasons_bear'):
                parts.append(f"隐忧：{'；'.join(fund['reasons_bear'][:2])}。")

        # 情绪面简述
        if sent:
            parts.append(f"\n**情绪面**: {sent.get('signal', '')}（近{sent.get('news_count', 0)}条新闻，"
                         f"利好{sent.get('pos_count', 0)}/利空{sent.get('neg_count', 0)}）。")

        # 操作建议
        action_map = {
            'buy': ('建议关注买入', '当前多维评分整体偏多，可在支撑位附近分批建仓，严格执行止损。'),
            'hold': ('建议观望', '当前多空信号交织，建议等待趋势明朗后再介入。'),
            'sell': ('建议回避/减仓', '当前综合评分偏弱，建议控制仓位、逢高减仓，规避下行风险。')
        }
        action, action_desc = action_map.get(comp['signal_type'], ('建议观望', ''))
        parts.append(f"\n## 操作建议\n**{action}**（{comp['signal']}）。{action_desc}")

        # 价格区间
        if t and t.get('support_resistance'):
            sr = t['support_resistance']
            current = sr.get('current_price', '-')
            support = sr.get('nearest_support', '-')
            resistance = sr.get('nearest_resistance', '-')
            parts.append(f"\n## 价格区间\n现价{current}，下方支撑{support}，上方压力{resistance}。")
            if points.get('strategy'):
                parts.append(f"\n参考交易计划：{points['strategy']}")

        # 风险提示
        risks = []
        if tech and tech.get('reasons_bear'):
            risks.extend(tech['reasons_bear'][:2])
        if fund and fund.get('reasons_bear'):
            risks.extend(fund['reasons_bear'][:2])
        if sent and sent.get('reasons_bear'):
            risks.extend(sent['reasons_bear'][:2])
        if risks:
            parts.append(f"\n## 风险提示\n{'；'.join(list(dict.fromkeys(risks))[:4])}")
        else:
            parts.append("\n## 风险提示\n当前未识别到明显风险信号，但仍需注意大盘系统性风险。")

        parts.append("\n---\n*本分析由内置规则引擎生成（未配置AI服务）。配置AI Key后可获得更深入的智能解读。*")
        return "\n".join(parts)

    def ai_interpret(self, code, name, tech, fund, sent, comp, market='a', stream=False):
        """AI深度解读
        stream=True 时使用流式接口收集完整解读（适用于长文本/本地模型，避免整体超时）
        """
        prompt = self.build_ai_prompt(code, name, tech, fund, sent, comp, market)

        if not self.ai_client.is_available():
            return {
                'available': False,
                'content': self.generate_rule_interpretation(code, name, tech, fund, sent, comp, market),
                'model': '规则引擎'
            }

        if stream:
            # 流式收集完整解读（对本地Ollama等长推理更友好）
            try:
                ok, generator = self.ai_client.analyze_stock_stream(prompt)
                if not ok:
                    logger.warning(f"AI分析失败({code}): {generator}")
                    return {
                        'available': False,
                        'content': self.generate_rule_interpretation(code, name, tech, fund, sent, comp, market),
                        'model': '规则引擎',
                        'ai_error': str(generator)
                    }
                chunks = []
                for chunk in generator:
                    chunks.append(chunk)
                if not chunks:
                    return {
                        'available': False,
                        'content': self.generate_rule_interpretation(code, name, tech, fund, sent, comp, market),
                        'model': '规则引擎',
                        'ai_error': 'AI未返回内容'
                    }
                return {
                    'available': True,
                    'content': ''.join(chunks),
                    'model': load_config().get('ai', {}).get('model', '')
                }
            except Exception as e:
                logger.warning(f"AI流式分析失败({code}): {e}")
                return {
                    'available': False,
                    'content': self.generate_rule_interpretation(code, name, tech, fund, sent, comp, market),
                    'model': '规则引擎',
                    'ai_error': str(e)
                }

        ok, content = self.ai_client.analyze_stock(prompt)
        if not ok:
            logger.warning(f"AI分析失败({code}): {content}")
            return {
                'available': False,
                'content': self.generate_rule_interpretation(code, name, tech, fund, sent, comp, market),
                'model': '规则引擎',
                'ai_error': str(content)
            }

        return {
            'available': True,
            'content': content,
            'model': load_config().get('ai', {}).get('model', '')
        }

    # ==================== 主流程 ====================

    def analyze_stock(self, code, name='', market='a', use_ai=True):
        """
        综合AI分析单只股票
        返回: 三维评分 + 综合评分 + AI解读 + 交易计划
        market: a=沪深A股, etf=场内ETF, hk=港股
        """
        tech = self.get_technical_score(code, name, market=market)
        fund = self.get_fundamental_score(code, name, market=market)
        sent = self.get_sentiment_score(code, name, market=market)

        comp = self.comprehensive_score(tech, fund, sent)

        # 合并交易点位（技术面计算）
        points = tech.get('points', {}) if tech else {}

        # AI解读
        ai_result = self.ai_interpret(code, name, tech, fund, sent, comp, market) if use_ai else None

        return {
            'code': code,
            'name': name,
            'market': market,
            'market_name': MARKET_NAMES.get(market, market),
            'comprehensive_score': comp['total'],
            'grade': comp['grade'],
            'grade_label': comp['grade_label'],
            'signal': comp['signal'],
            'signal_type': comp['signal_type'],
            'scores': {
                'tech': comp['tech'],
                'fund': comp['fund'],
                'sent': comp['sent'],
                'total': comp['total']
            },
            'technical': tech,
            'fundamental': fund,
            'sentiment': sent,
            'points': points,
            'ai': ai_result
        }

    def scan_market(self, max_stocks=12, use_ai=False, market='a', codes=None,
                    board=None, ai_min_score=70, progress=None):
        """
        扫描市场生成AI推荐列表
        use_ai=True 时仅对综合评分 >= ai_min_score 的股票调用AI深度解读
        codes: 指定股票代码列表（优先于此模式，与 board 互斥）
        board: 行业板块名（如'半导体'），扫描该板块成分股
        progress: 进度回调 progress(stage, done, total, message)
                  stage: 'quotes'=拉行情 'score'=评分 'ai'=AI解读
        market: a=沪深A股, etf=场内ETF, hk=港股
        """
        fetcher = self.fetcher

        # ---------- 1. 生成候选股票 ----------
        if codes:
            quotes = fetcher.get_realtime_quotes(codes, market=market)
            if not quotes:
                return []
            candidates = quotes[:max_stocks]
            if progress:
                progress('quotes', len(candidates), len(candidates),
                         f'已获取 {len(candidates)} 只指定股票的行情')
        elif board:
            from data_fetcher import get_board_stocks
            stocks = get_board_stocks(board)
            if not stocks:
                logger.warning(f"板块[{board}]无成分股数据")
                return []
            codes_in_board = [s['code'] for s in stocks]
            quotes = fetcher.get_realtime_quotes(codes_in_board, market=market)
            if progress:
                progress('quotes', 1, 1, f'板块[{board}]共 {len(stocks)} 只成分股，'
                                         f'已获取 {len(quotes)} 只行情')
            # 板块行情较多时按涨跌幅排序取前 max_stocks 只
            valid = [q for q in quotes if -10 < q.get('pct_change', 0) < 11]
            valid.sort(key=lambda x: x.get('pct_change', 0), reverse=True)
            candidates = valid[:max_stocks]
            if progress:
                progress('quotes', len(candidates), len(candidates),
                         f'板块[{board}]筛选出涨跌幅前 {len(candidates)} 只候选')
        else:
            all_quotes = fetcher.get_realtime_quotes(market=market)
            if not all_quotes:
                return []
            valid = [q for q in all_quotes if -10 < q.get('pct_change', 0) < 11]
            top_gainers = sorted(valid, key=lambda x: x.get('pct_change', 0), reverse=True)[:max_stocks // 2]
            top_volume = sorted(valid, key=lambda x: x.get('amount', 0), reverse=True)[:max_stocks // 2]
            candidates = []
            seen = set()
            for s in top_gainers + top_volume:
                if s['code'] not in seen:
                    candidates.append(s)
                    seen.add(s['code'])
            candidates = candidates[:max_stocks]
            if progress:
                progress('quotes', len(candidates), len(candidates),
                         f'已获取全市场行情，筛出 {len(candidates)} 只候选')

        # ---------- 2. 第一阶段：全量评分（不调用AI，速度快） ----------
        results = []
        total = len(candidates)
        for idx, stock in enumerate(candidates):
            try:
                result = self.analyze_stock(stock['code'], stock.get('name', ''),
                                            market=market, use_ai=False)
                results.append(result)
            except Exception as e:
                logger.error(f"分析{stock['code']}失败: {e}")
            if progress:
                done = idx + 1
                name = stock.get('name', stock['code'])
                progress('score', done, total, f'评分中 ({done}/{total}) {name}')
            time.sleep(0.2)

        results.sort(key=lambda x: x['comprehensive_score'], reverse=True)

        # ---------- 3. 第二阶段：对综合评分 >= ai_min_score 的调用AI深度解读 ----------
        if use_ai and results:
            ai_targets = [r for r in results if r['comprehensive_score'] >= ai_min_score]
            ai_total = len(ai_targets)
            logger.info(f"市场扫描(market={market})评分完成共{len(results)}只，"
                        f"综合评分>={ai_min_score}的{ai_total}只进行AI深度解读...")
            for idx, r in enumerate(ai_targets):
                try:
                    comp = {
                        'total': r['comprehensive_score'],
                        'grade': r['grade'],
                        'grade_label': r['grade_label'],
                        'tech': r['scores']['tech'],
                        'fund': r['scores']['fund'],
                        'sent': r['scores']['sent'],
                        'signal': r['signal'],
                        'signal_type': r['signal_type']
                    }
                    if progress:
                        progress('ai', idx + 1, ai_total,
                                 f'AI解读中 ({idx + 1}/{ai_total}) {r["name"]} '
                                 f'综合{int(r["comprehensive_score"])}分')
                    r['ai'] = self.ai_interpret(r['code'], r['name'],
                                                r['technical'], r['fundamental'],
                                                r['sentiment'], comp, market,
                                                stream=True)
                except Exception as e:
                    logger.error(f"AI解读{r['code']}失败: {e}")
                    r['ai'] = None
            if progress and ai_total == 0:
                progress('ai', 0, 0, f'无综合评分>={ai_min_score}的股票，跳过AI深度解读')

        return results


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    eng = AIRecommendationEngine()
    r = eng.analyze_stock('600519', '贵州茅台', use_ai=False)
    print(json.dumps(r, ensure_ascii=False, indent=2)[:2000])
