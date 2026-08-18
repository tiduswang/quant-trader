# -*- coding: utf-8 -*-
"""
Recommendation Engine - 量化选股与买卖推荐引擎
技术面评分依据 DR-lin-eng/stock-scanner：
  - 基础分50，按均线/RSI/MACD/布林带/量价状态加减分，限制0-100
  - 所有阈值与分值由 strategy_params.py 提供，可在前端调节
"""
import pandas as pd
import numpy as np
from analysis_engine import AnalysisEngine
from data_fetcher import DataFetcher
from strategy_params import get_strategy_params


class RecommendationEngine:
    """量化推荐引擎"""

    def __init__(self, fetcher=None, analyzer=None):
        self.fetcher = fetcher or DataFetcher()
        self.analyzer = analyzer or AnalysisEngine()

    def score_stock(self, analysis_result):
        """
        stock-scanner 技术面评分模型（满分100）
        - 基础分50
        - 均线趋势: 多头排列 +20 / 空头排列 -20
        - RSI: 健康区间(30-70) +10 / 超卖 +5 / 超买 -5
        - MACD: 金叉向上 +15 / 死叉向下 -15
        - 布林带: 中间区域 +5 / 接近下轨 +10 / 接近上轨 -5
        - 量价: 放量上涨 +10 / 放量下跌 -10 / 缩量 0
        """
        if analysis_result is None:
            return 0, [], []

        p = get_strategy_params()['technical']
        score = p['base_score']
        reasons_bull = []
        reasons_bear = []

        # ===== 均线趋势 =====
        trend = analysis_result.get('trend', '')
        if '多头排列' in trend:
            score += p['ma_bull_score']
            reasons_bull.append(f"均线{trend}，中期趋势向上")
        elif '空头排列' in trend:
            score -= p['ma_bear_score']
            reasons_bear.append(f"均线{trend}，中期趋势向下")
        elif '偏多' in trend:
            reasons_bull.append("均线偏多震荡，趋势相对乐观")
        elif '偏空' in trend:
            reasons_bear.append("均线偏空震荡，趋势偏弱")

        # ===== RSI =====
        rsi_info = analysis_result.get('rsi', {})
        rsi_val = rsi_info.get('rsi6', 50)
        if isinstance(rsi_val, (int, float)) and not pd.isna(rsi_val):
            if p['rsi_oversold'] <= rsi_val <= p['rsi_overbought']:
                score += p['rsi_normal_score']
                reasons_bull.append(f"RSI({rsi_val:.1f})处于健康区间，无明显超买超卖")
            elif rsi_val < p['rsi_oversold']:
                score += p['rsi_oversold_score']
                reasons_bull.append(f"RSI({rsi_val:.1f})处于超卖区域，存在技术性反弹机会")
            else:
                score += p['rsi_overbought_score']
                reasons_bear.append(f"RSI({rsi_val:.1f})处于超买区域，回调风险加大")

        # ===== MACD =====
        macd_info = analysis_result.get('macd', {})
        macd_signal = macd_info.get('signal', '')
        if '金叉' in macd_signal or '多头' in macd_signal:
            score += p['macd_golden_score']
            reasons_bull.append(f"MACD{macd_signal}，上涨动能增强")
        elif '死叉' in macd_signal or '空头' in macd_signal:
            score -= p['macd_dead_score']
            reasons_bear.append(f"MACD{macd_signal}，下跌动能增强")

        # ===== 布林带位置 =====
        boll_info = analysis_result.get('boll', {})
        boll_upper = boll_info.get('upper')
        boll_lower = boll_info.get('lower')
        close = analysis_result.get('close', 0)
        if boll_upper and boll_lower and boll_upper > boll_lower and close:
            # 布林带相对位置: 0=下轨, 1=上轨
            bb_pos = (close - boll_lower) / (boll_upper - boll_lower)
            if bb_pos < p['boll_lower_zone']:
                score += p['boll_lower_score']
                reasons_bull.append(f"价格接近布林带下轨(位置{bb_pos:.2f})，超卖反弹概率增大")
            elif bb_pos > p['boll_upper_zone']:
                score += p['boll_upper_score']
                reasons_bear.append(f"价格接近布林带上轨(位置{bb_pos:.2f})，短期过热")
            else:
                score += p['boll_mid_score']
                reasons_bull.append("价格运行于布林带中间区域，走势平稳")

        # ===== 量价配合 =====
        vol_info = analysis_result.get('volume', {})
        vol_ratio = vol_info.get('volume_ratio', 1)
        vol_pattern = vol_info.get('pattern', '')
        pct_change = analysis_result.get('pct_change', 0) or 0
        if vol_ratio and vol_ratio > p['vol_surge_ratio']:
            if pct_change > 0:
                score += p['vol_up_score']
                reasons_bull.append(f"放量上涨(量比{vol_ratio})，量价配合良好")
            else:
                score -= p['vol_down_score']
                reasons_bear.append(f"放量下跌(量比{vol_ratio})，资金出逃迹象")
        elif vol_ratio and vol_ratio < p['vol_shrink_ratio']:
            reasons_bull.append("缩量整理，抛压减轻")

        score = max(0, min(100, score))
        return score, reasons_bull, reasons_bear

    def generate_signal(self, score):
        """根据评分生成交易信号"""
        if score >= 75:
            return "强烈推荐", "buy"
        elif score >= 60:
            return "推荐关注", "buy"
        elif score >= 45:
            return "中性观望", "hold"
        elif score >= 30:
            return "谨慎", "sell"
        else:
            return "建议回避", "sell"

    def calc_entry_exit_points(self, analysis_result, signal_type):
        """计算买入卖出点位"""
        if analysis_result is None:
            return {}

        sr = analysis_result.get('support_resistance', {})
        current = sr.get('current_price', 0)
        nearest_support = sr.get('nearest_support', current * 0.95)
        nearest_resistance = sr.get('nearest_resistance', current * 1.05)
        boll = analysis_result.get('boll', {})
        boll_lower = boll.get('lower', nearest_support)
        boll_upper = boll.get('upper', nearest_resistance)

        if signal_type == "buy":
            # 买入策略：在支撑位附近买入
            entry_price = round(min(current, nearest_support * 1.01), 2)
            # 止损设在支撑位下方3%
            stop_loss = round(nearest_support * 0.97, 2)
            # 第一目标价：压力位
            target1 = round(nearest_resistance, 2)
            # 第二目标价：压力位上方5%
            target2 = round(nearest_resistance * 1.05, 2)

            return {
                'entry_price': entry_price,
                'stop_loss': stop_loss,
                'target1': target1,
                'target2': target2,
                'risk_reward_ratio': round((target1 - entry_price) / (entry_price - stop_loss), 2) if (entry_price - stop_loss) > 0 else None,
                'strategy': f"建议在{entry_price}附近买入，止损设于{stop_loss}(支撑位下方3%)，"
                           f"第一目标{target1}(压力位)，第二目标{target2}(突破压力位后5%)"
            }
        elif signal_type == "sell":
            # 卖出策略
            return {
                'exit_price': round(current * 0.99, 2),
                'stop_loss': round(max(nearest_support, boll_lower) * 0.97, 2),
                'rebound_target': round(nearest_resistance, 2),
                'strategy': f"当前处于弱势，建议逢高减仓，"
                           f"若跌破{round(max(nearest_support, boll_lower), 2)}应果断止损"
            }
        else:
            # 观望
            return {
                'watch_level_buy': round(nearest_support, 2),
                'watch_level_sell': round(nearest_resistance, 2),
                'strategy': f"建议观望，若回调至{round(nearest_support, 2)}附近企稳可考虑买入，"
                           f"若反弹至{round(nearest_resistance, 2)}附近受阻则继续观望"
            }

    def generate_reasoning(self, stock_info, analysis_result, score, reasons_bull, reasons_bear, signal, signal_type, points):
        """生成详细的买卖理由分析"""
        name = stock_info.get('name', '')
        code = stock_info.get('code', '')
        close = analysis_result.get('close', 0)
        pct = analysis_result.get('pct_change', 0)
        trend = analysis_result.get('trend', '')

        bull_text = "；".join(reasons_bull) if reasons_bull else "暂无明显利好技术信号"
        bear_text = "；".join(reasons_bear) if reasons_bear else "暂无明显利空技术信号"

        if signal_type == "buy":
            action = f"建议买入"
            reasoning = (
                f"【{name}({code}) 技术分析报告】\n\n"
                f"当前价格: {close} (涨跌幅: {pct:+.2f}%)\n"
                f"趋势判断: {trend}\n"
                f"综合评分: {score}/100\n"
                f"操作建议: {signal}\n\n"
                f"利好因素:\n{bull_text}\n\n"
                f"风险提示:\n{bear_text}\n\n"
                f"交易计划:\n{points.get('strategy', '')}\n"
            )
        elif signal_type == "sell":
            action = f"建议卖出/回避"
            reasoning = (
                f"【{name}({code}) 技术分析报告】\n\n"
                f"当前价格: {close} (涨跌幅: {pct:+.2f}%)\n"
                f"趋势判断: {trend}\n"
                f"综合评分: {score}/100\n"
                f"操作建议: {signal}\n\n"
                f"利空因素:\n{bear_text}\n\n"
                f"潜在支撑:\n{bull_text}\n\n"
                f"交易计划:\n{points.get('strategy', '')}\n"
            )
        else:
            action = "建议观望"
            reasoning = (
                f"【{name}({code}) 技术分析报告】\n\n"
                f"当前价格: {close} (涨跌幅: {pct:+.2f}%)\n"
                f"趋势判断: {trend}\n"
                f"综合评分: {score}/100\n"
                f"操作建议: {signal}\n\n"
                f"利好因素:\n{bull_text}\n\n"
                f"风险提示:\n{bear_text}\n\n"
                f"交易计划:\n{points.get('strategy', '')}\n"
            )

        return reasoning

    def analyze_single_stock(self, code, name='', market='a'):
        """分析单只股票
        market: a=沪深A股, etf=场内ETF, hk=港股
        """
        # 获取历史数据
        df = self.fetcher.get_stock_history(code, days=120, market=market)
        if df is None or df.empty:
            return None

        # 技术分析
        analysis = self.analyzer.full_analysis(df)
        if analysis is None:
            return None

        # 打分
        score, reasons_bull, reasons_bear = self.score_stock(analysis)

        # 生成信号
        signal, signal_type = self.generate_signal(score)

        # 计算买卖点位
        points = self.calc_entry_exit_points(analysis, signal_type)

        # 生成理由
        stock_info = {'code': code, 'name': name}
        reasoning = self.generate_reasoning(stock_info, analysis, score,
                                            reasons_bull, reasons_bear,
                                            signal, signal_type, points)

        return {
            'code': code,
            'name': name,
            'score': score,
            'signal': signal,
            'signal_type': signal_type,
            'reasoning': reasoning,
            'analysis': analysis,
            'points': points,
            'reasons_bull': reasons_bull,
            'reasons_bear': reasons_bear
        }

    def scan_market(self, max_stocks=20):
        """
        扫描市场，生成推荐列表
        从股票池获取实时行情，取涨幅前N名+成交额前N名进行技术分析
        """
        import logging
        logger = logging.getLogger(__name__)

        # 获取全部股票池的实时行情
        logger.info("scan_market: 开始获取实时行情...")
        all_quotes = self.fetcher.get_realtime_quotes()
        logger.info(f"scan_market: 获取到{len(all_quotes)}条行情")
        if not all_quotes:
            logger.warning("scan_market: 行情为空，返回空列表")
            return []

        # 过滤涨跌幅异常的
        valid = [q for q in all_quotes if -10 < q.get('pct_change', 0) < 11]

        # 涨幅前N
        top_gainers = sorted(valid, key=lambda x: x.get('pct_change', 0), reverse=True)[:max_stocks // 2]
        # 成交额前N
        top_volume = sorted(valid, key=lambda x: x.get('amount', 0), reverse=True)[:max_stocks // 2]

        candidates = []
        seen_codes = set()
        for s in top_gainers + top_volume:
            if s['code'] not in seen_codes:
                candidates.append(s)
                seen_codes.add(s['code'])

        candidates = candidates[:max_stocks]

        results = []
        for stock in candidates:
            try:
                result = self.analyze_single_stock(stock['code'], stock.get('name', ''))
                if result:
                    results.append(result)
                import time as _time
                _time.sleep(0.3)  # 避免API请求过快
            except Exception as e:
                continue

        # 按评分排序
        results.sort(key=lambda x: x['score'], reverse=True)
        return results

    def get_top_recommendations(self, max_stocks=15):
        """获取推荐列表（精简版）- 优先返回买入信号，不足则补充其他"""
        all_results = self.scan_market(max_stocks)
        # 优先买入信号，不足补充中性观望
        buy_list = [r for r in all_results if r['signal_type'] == 'buy']
        hold_list = [r for r in all_results if r['signal_type'] == 'hold']
        result = buy_list[:10]
        if len(result) < 10:
            result.extend(hold_list[:10 - len(result)])
        return result
