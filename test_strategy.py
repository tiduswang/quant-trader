# -*- coding: utf-8 -*-
"""离线单测：stock-scanner 新评分逻辑 + 参数调节"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from strategy_params import get_strategy_params, update_strategy_params
from recommendation_engine import RecommendationEngine
from ai_recommendation_engine import AIRecommendationEngine

# ---- 1. 参数读写 ----
p = get_strategy_params()
assert p['weights'] == {'technical': 0.4, 'fundamental': 0.4, 'sentiment': 0.2}, p['weights']
assert p['technical']['ma_bull_score'] == 20
assert p['signal']['strong_buy'] == 80
print("1. 参数默认值 OK")

# ---- 2. 技术面评分（多头+RSI健康+MACD金叉+BOLL中区+放量上涨 = 50+20+10+15+5+10=110→100） ----
re = RecommendationEngine.__new__(RecommendationEngine)
fake_bull = {
    'trend': '多头排列(强势)', 'close': 10.0, 'pct_change': 2.5,
    'rsi': {'rsi6': 55},
    'macd': {'signal': '金叉向上'},
    'boll': {'upper': 11.0, 'lower': 9.0, 'mid': 10.0},
    'volume': {'volume_ratio': 2.0, 'pattern': '放量上涨'},
}
score, bull, bear = re.score_stock(fake_bull)
assert score == 100, score
print(f"2a. 强势组合技术分 = {score} (预期100) OK")

# 空头+超买+死叉+近上轨+放量下跌 = 50-20-5-15-5-10 = -5 → 0
fake_bear = {
    'trend': '空头排列(弱势)', 'close': 10.9, 'pct_change': -2.5,
    'rsi': {'rsi6': 75},
    'macd': {'signal': '死叉向下'},
    'boll': {'upper': 11.0, 'lower': 9.0, 'mid': 10.0},
    'volume': {'volume_ratio': 2.0, 'pattern': '放量下跌'},
}
score2, _, _ = re.score_stock(fake_bear)
assert score2 == 0, score2
print(f"2b. 弱势组合技术分 = {score2} (预期0) OK")

# ---- 3. 参数调节生效：把MA多头加分改为5 ----
update_strategy_params({'technical': {'ma_bull_score': 5}})
score3, _, _ = re.score_stock(fake_bull)
assert score3 == 95, score3
update_strategy_params({}, reset=True)
print("3. 参数调节生效并恢复默认 OK")

# ---- 4. 综合评分与信号分级 ----
ai = AIRecommendationEngine.__new__(AIRecommendationEngine)
# ≥80 且 tech/fund ≥75 → 强烈推荐买入 (85*0.4+80*0.4+80*0.2=82)
comp = ai.comprehensive_score({'score': 85}, {'score': 80}, {'score': 80})
assert comp['signal'] == '强烈推荐买入' and comp['total'] == 82.0, comp
# ≥80 但基本面 <75 → 推荐买入 (95*0.4+72*0.4+90*0.2=84.8)
comp2 = ai.comprehensive_score({'score': 95}, {'score': 72}, {'score': 90})
assert comp2['signal'] == '推荐买入', comp2
# 65-80 且 sent≥60 → 建议买入
comp3 = ai.comprehensive_score({'score': 70}, {'score': 70}, {'score': 65})
assert comp3['signal'] == '建议买入', comp3
# 65-80 且 sent<60 → 谨慎买入
comp4 = ai.comprehensive_score({'score': 70}, {'score': 70}, {'score': 50})
assert comp4['signal'] == '谨慎买入', comp4
# 45-65 → 持有观望
comp5 = ai.comprehensive_score({'score': 60}, {'score': 50}, {'score': 50})
assert comp5['signal'] == '持有观望', comp5
# <45 → 减仓/卖出
comp6 = ai.comprehensive_score({'score': 40}, {'score': 40}, {'score': 40})
assert comp6['signal'] == '建议减仓', comp6
comp7 = ai.comprehensive_score({'score': 20}, {'score': 20}, {'score': 20})
assert comp7['signal'] == '建议卖出', comp7
print("4. 综合信号分级 OK")

# ---- 5. 权重调节：技术面权重提到1.0 ----
update_strategy_params({'weights': {'technical': 1.0, 'fundamental': 0, 'sentiment': 0}})
comp8 = ai.comprehensive_score({'score': 90}, {'score': 50}, {'score': 50})
assert comp8['total'] == 90, comp8
update_strategy_params({}, reset=True)
print("5. 权重调节生效 OK")

# ---- 6. config.json 完整性（ai 节未被破坏） ----
import json
with open('config.json', encoding='utf-8') as f:
    cfg = json.load(f)
assert cfg.get('ai', {}).get('provider') == 'ollama', cfg
assert 'strategy' in cfg
print("6. config.json 完整 OK")

print("\n全部离线测试通过")
