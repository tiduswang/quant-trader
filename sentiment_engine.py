# -*- coding: utf-8 -*-
"""
Sentiment Engine - 新闻情绪分析引擎
评分公式依据 DR-lin-eng/stock-scanner：
  - 基础分 = (整体情绪 + 1) * 50，整体情绪 = (利好数 - 利空数) / 总数
  - 置信度加分 = min(总数 / 置信度封顶数, 1) * 最大加分
  - 新闻数量加分 = min(总数 / 新闻封顶数, 1) * 最大加分
  - 参数由 strategy_params.py 提供，可在前端调节
"""
import logging
import re

from strategy_params import get_strategy_params

logger = logging.getLogger(__name__)

# 利好关键词
BULLISH_KEYWORDS = [
    '业绩预增', '净利润增长', '营收增长', '涨停', '大涨', '回购', '增持',
    '中标', '签订合同', '大单', '合作', '战略', '突破', '创新高', '涨价',
    '扩产', '投资', '并购', '收购', '重组', '利好', '分红', '高送转',
    '盈利', '扭亏为盈', '超预期', '行业景气', '需求旺盛', '供不应求',
    '专利', '获批', '核准', '批复', '政策支持', '补贴', '减税', '降息',
    '增发', '定增', '获注资', '股权激励', '预收款增长', '毛利率提升',
    '新订单', '产能利用率', '满产', '市场占有率提升', '龙头', '成长'
]

# 利空关键词
BEARISH_KEYWORDS = [
    '业绩预减', '净利润下滑', '营收下降', '跌停', '大跌', '减持', '质押',
    '立案', '调查', '处罚', '罚款', '违规', '诉讼', '仲裁', '亏损', '退市',
    '风险提示', '警示', '警示函', '问询函', '监管', '冻结', '拍卖',
    '债务违约', '逾期', '停产', '停工', '召回', '质量问题', '事故',
    '裁员', '降薪', '资金链', '爆雷', '崩塌', '利空', '低于预期',
    '减值', '计提', '商誉', '存货跌价', '坏账', '受限', '被否',
    '下调评级', '卖出评级', '清仓', '解禁'
]

# 中性但值得关注的关键词
ATTENTION_KEYWORDS = [
    '提示', '公告', '停牌', '复牌', '关注', '异动', '澄清', '说明'
]


class SentimentEngine:
    """新闻情绪分析引擎"""

    def __init__(self, fetcher=None):
        from data_fetcher import DataFetcher
        self.fetcher = fetcher or DataFetcher()

    def analyze(self, code, name='', market='a'):
        """分析个股新闻情绪
        market: a=沪深A股, etf=场内ETF, hk=港股
        ETF/港股暂无新闻数据源时返回中性分
        """
        try:
            news = self.fetcher.get_stock_news(code, market=market)
        except Exception as e:
            logger.error(f"获取{code}新闻失败: {e}")
            news = []

        if not news:
            return {
                'score': 50, 'signal': '无新闻',
                'reasons_bull': [], 'reasons_bear': [],
                'news_count': 0, 'news': [], 'pos_count': 0, 'neg_count': 0
            }

        pos_count = 0
        neg_count = 0
        pos_titles = []
        neg_titles = []
        neutral_titles = []

        for item in news:
            title = item.get('title', '') or ''
            content = item.get('content', '') or ''
            text = title + content
            if not text:
                continue

            bull_hits = [kw for kw in BULLISH_KEYWORDS if kw in text]
            bear_hits = [kw for kw in BEARISH_KEYWORDS if kw in text]

            if len(bull_hits) > len(bear_hits):
                pos_count += 1
                pos_titles.append({'title': title, 'date': item.get('date', ''),
                                   'hits': bull_hits[:3]})
            elif len(bear_hits) > len(bull_hits):
                neg_count += 1
                neg_titles.append({'title': title, 'date': item.get('date', ''),
                                   'hits': bear_hits[:3]})
            else:
                neutral_titles.append({'title': title, 'date': item.get('date', '')})

        total = max(pos_count + neg_count + len(neutral_titles), 1)
        # stock-scanner 情绪评分公式
        p = get_strategy_params()['sentiment']
        overall_sentiment = (pos_count - neg_count) / total  # [-1, 1]
        base = (overall_sentiment + 1) * 50
        confidence = min(total / p['confidence_news_max'], 1.0)
        news_bonus = min(total / p['news_count_max'], 1.0) * p['news_bonus_max']
        score = base + confidence * p['confidence_bonus_max'] + news_bonus
        score = max(0, min(100, round(score, 1)))

        if score >= 65:
            signal = '情绪偏多'
        elif score >= 45:
            signal = '情绪中性'
        else:
            signal = '情绪偏空'

        reasons_bull = []
        reasons_bear = []
        if pos_count > 0:
            reasons_bull.append(f"近期新闻偏正面({pos_count}条利好)")
            if pos_titles:
                reasons_bull.append(f"利好报道如「{pos_titles[0]['title'][:30]}」")
        if neg_count > 0:
            reasons_bear.append(f"近期新闻偏负面({neg_count}条利空)")
            if neg_titles:
                reasons_bear.append(f"利空报道如「{neg_titles[0]['title'][:30]}」")
        if not reasons_bull and not reasons_bear:
            reasons_bull.append(f"近期{len(news)}条新闻无明显多空信号")

        return {
            'score': score,
            'signal': signal,
            'reasons_bull': reasons_bull,
            'reasons_bear': reasons_bear,
            'news_count': len(news),
            'pos_count': pos_count,
            'neg_count': neg_count,
            'news': news[:5],
            'pos_titles': pos_titles[:3],
            'neg_titles': neg_titles[:3]
        }


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    eng = SentimentEngine()
    r = eng.analyze('600519', '贵州茅台')
    print(f"情绪分: {r['score']}, 信号: {r['signal']}, 新闻数: {r['news_count']}")
    print(f"正面: {r['pos_count']}, 负面: {r['neg_count']}")
    print(f"利好理由: {r['reasons_bull']}")
    print(f"利空理由: {r['reasons_bear']}")
