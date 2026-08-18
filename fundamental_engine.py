# -*- coding: utf-8 -*-
"""
Fundamental Engine - 基本面分析引擎
评分依据 DR-lin-eng/stock-scanner：
  - 基础分50，按财务指标数量门槛、ROE、资产负债率、营收增长、估值数据加减分
  - 所有阈值与分值由 strategy_params.py 提供，可在前端调节
"""
import logging
import math

from strategy_params import get_strategy_params

logger = logging.getLogger(__name__)


def _clean(val, ndigits=2):
    """清理数值：NaN/None 转 None，否则保留两位小数"""
    if val is None:
        return None
    try:
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return None
        return round(f, ndigits)
    except (TypeError, ValueError):
        return None


class FundamentalEngine:
    """基本面分析引擎"""

    def __init__(self, fetcher=None):
        from data_fetcher import DataFetcher
        self.fetcher = fetcher or DataFetcher()

    def analyze(self, code, name='', market='a'):
        """完整基本面分析
        market: a=沪深A股, etf=场内ETF, hk=港股
        """
        fund = self.fetcher.get_fundamental_info(code, market=market)
        if not fund:
            return {'score': 50, 'reasons_bull': [], 'reasons_bear': [],
                    'data': {}, 'signal': '未知'}

        fin = self.fetcher.get_financial_abstract(code, market=market) or {}

        reasons_bull = []
        reasons_bear = []
        p = get_strategy_params()['fundamental']
        score = p['base_score']  # 基础分

        pe = fund.get('pe', 0)
        pb = fund.get('pb', 0)
        total_mv = fund.get('total_mv', 0)
        roe = fin.get('roe')
        gross_margin = fin.get('gross_margin')
        debt_ratio = fin.get('debt_ratio')
        revenue_yoy = fin.get('revenue_yoy')
        net_profit_yoy = fin.get('net_profit_yoy')

        # ===== 财务指标齐全度（stock-scanner: 指标数量门槛加分）=====
        candidate_metrics = [
            pe, pb, total_mv, fund.get('turnover_rate'),
            roe, gross_margin, debt_ratio, revenue_yoy, net_profit_yoy,
        ]
        valid_count = sum(1 for v in candidate_metrics
                          if v is not None and _clean(v) is not None)
        if valid_count >= p['indicator_bonus_threshold']:
            score += p['indicator_bonus']
            reasons_bull.append(f"财务数据齐全({valid_count}项指标)，信息披露充分")
        else:
            reasons_bear.append(f"财务数据仅{valid_count}项可用，信息有限")

        # ===== ROE 盈利能力 =====
        roe = fin.get('roe')
        if roe is not None:
            try:
                v = float(roe)
                if v > p['roe_excellent']:
                    score += p['roe_excellent_score']
                    reasons_bull.append(f"ROE达{v:.1f}%，盈利能力优秀")
                elif v > p['roe_good']:
                    score += p['roe_good_score']
                    reasons_bull.append(f"ROE为{v:.1f}%，盈利能力良好")
                elif v < p['roe_poor']:
                    score += p['roe_poor_score']
                    reasons_bear.append(f"ROE仅{v:.1f}%，盈利能力偏弱")
            except (TypeError, ValueError):
                pass

        # ===== 资产负债率 =====
        debt_ratio = fin.get('debt_ratio')
        if debt_ratio is not None:
            try:
                v = float(debt_ratio)
                if v < p['debt_low']:
                    score += p['debt_low_score']
                    reasons_bull.append(f"资产负债率{v:.1f}%，财务结构稳健")
                elif v > p['debt_high']:
                    score += p['debt_high_score']
                    reasons_bear.append(f"资产负债率{v:.1f}%，财务杠杆偏高")
            except (TypeError, ValueError):
                pass

        # ===== 营收同比增长 =====
        revenue_yoy = fin.get('revenue_yoy')
        if revenue_yoy is not None:
            try:
                v = float(revenue_yoy)
                if v > p['rev_excellent']:
                    score += p['rev_excellent_score']
                    reasons_bull.append(f"营收同比+{v:.1f}%，收入高增长")
                elif v > p['rev_good']:
                    score += p['rev_good_score']
                    reasons_bull.append(f"营收同比+{v:.1f}%，收入稳健增长")
                elif v < p['rev_poor']:
                    score += p['rev_poor_score']
                    reasons_bear.append(f"营收同比{v:.1f}%，收入明显下滑")
            except (TypeError, ValueError):
                pass

        # ===== 估值数据存在加分 =====
        if (pe and pe > 0) or (pb and pb > 0):
            score += p['valuation_bonus']
            reasons_bull.append("估值数据完备(PE/PB可参考)")

        score = max(0, min(100, score))

        if score >= 70:
            signal = '基本面优秀'
        elif score >= 55:
            signal = '基本面良好'
        elif score >= 40:
            signal = '基本面一般'
        else:
            signal = '基本面偏弱'

        return {
            'score': score,
            'signal': signal,
            'reasons_bull': reasons_bull,
            'reasons_bear': reasons_bear,
            'data': {
                'pe': _clean(fund.get('pe', 0)),
                'pb': _clean(fund.get('pb', 0)),
                'total_mv': _clean(fund.get('total_mv', 0)),
                'float_mv': _clean(fund.get('float_mv', 0)),
                'turnover_rate': _clean(fund.get('turnover_rate', 0)),
                'net_profit_yoy': _clean(net_profit_yoy, 1),
                'revenue_yoy': _clean(revenue_yoy, 1),
                'roe': _clean(roe, 2),
                'gross_margin': _clean(gross_margin, 2),
                'debt_ratio': _clean(debt_ratio, 2),
                'name': name
            }
        }


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    eng = FundamentalEngine()
    r = eng.analyze('600519', '贵州茅台')
    print(f"评分: {r['score']}, 信号: {r['signal']}")
    print(f"利好: {r['reasons_bull']}")
    print(f"利空: {r['reasons_bear']}")
    print(f"数据: {r['data']}")
