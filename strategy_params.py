# -*- coding: utf-8 -*-
"""
Strategy Params - 选股策略参数管理
评分体系依据 DR-lin-eng/stock-scanner：
  - 综合评分 = 技术面(w) + 基本面(w) + 情绪面(w)，默认 0.4/0.4/0.2
  - 各维度基础分50，按指标阈值加减分，限制0-100
所有参数可在前端调节，持久化到 config.json 的 strategy 节。
"""
import copy
import json
import logging
import os
import threading

logger = logging.getLogger(__name__)

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')

_lock = threading.Lock()

# 默认参数（与 stock-scanner 源码保持一致）
DEFAULT_STRATEGY_PARAMS = {
    # 三维度权重（总和应为1）
    'weights': {
        'technical': 0.4,
        'fundamental': 0.4,
        'sentiment': 0.2,
    },
    # ===== 技术面参数 =====
    'technical': {
        'base_score': 50,            # 基础分
        # 均线趋势
        'ma_bull_score': 20,         # 多头排列加分
        'ma_bear_score': 20,         # 空头排列减分
        # RSI
        'rsi_oversold': 30,          # 超卖阈值
        'rsi_overbought': 70,        # 超买阈值
        'rsi_normal_score': 10,      # 30-70健康区间加分
        'rsi_oversold_score': 5,     # 超卖反弹加分
        'rsi_overbought_score': -5,  # 超买回调减分
        # MACD
        'macd_golden_score': 15,     # 金叉向上加分
        'macd_dead_score': 15,       # 死叉向下减分
        # 布林带
        'boll_lower_zone': 0.2,      # 接近下轨阈值
        'boll_upper_zone': 0.8,      # 接近上轨阈值
        'boll_mid_score': 5,         # 中间区域加分
        'boll_lower_score': 10,      # 接近下轨（超卖）加分
        'boll_upper_score': -5,      # 接近上轨（超买）减分
        # 量价
        'vol_surge_ratio': 1.5,      # 放量阈值（量比）
        'vol_shrink_ratio': 0.5,     # 缩量阈值（量比）
        'vol_up_score': 10,          # 放量上涨加分
        'vol_down_score': 10,        # 放量下跌减分
    },
    # ===== 基本面参数 =====
    'fundamental': {
        'base_score': 50,                 # 基础分
        'indicator_bonus_threshold': 6,   # 有效财务指标数量门槛（本地数据源约9项，可调）
        'indicator_bonus': 20,            # 达到门槛加分
        # ROE（%）
        'roe_excellent': 15,
        'roe_excellent_score': 10,
        'roe_good': 10,
        'roe_good_score': 5,
        'roe_poor': 5,
        'roe_poor_score': -5,
        # 资产负债率（%）
        'debt_low': 30,
        'debt_low_score': 5,
        'debt_high': 70,
        'debt_high_score': -10,
        # 营收同比增长率（%）
        'rev_excellent': 20,
        'rev_excellent_score': 10,
        'rev_good': 10,
        'rev_good_score': 5,
        'rev_poor': -10,
        'rev_poor_score': -10,
        # 估值数据（PE/PB存在有效值）
        'valuation_bonus': 10,
    },
    # ===== 情绪面参数 =====
    'sentiment': {
        # 最终分 = (整体情绪+1)*50 + 置信度*confidence_bonus_max + min(新闻数/news_count_max,1)*news_bonus_max
        'confidence_news_max': 50,    # 置信度封顶新闻条数
        'confidence_bonus_max': 10,   # 置信度最大加分
        'news_count_max': 100,        # 新闻数量加分封顶条数
        'news_bonus_max': 10,         # 新闻数量最大加分
    },
    # ===== 综合信号判定阈值 =====
    'signal': {
        'strong_buy': 80,        # 综合分达到该值进入买入区
        'buy': 65,               # 建议买入下限
        'hold': 45,              # 持有观望下限
        'sell': 30,              # 建议减仓下限（低于为建议卖出）
        'strong_tech_min': 75,   # 强烈推荐所需技术面最低分
        'strong_fund_min': 75,   # 强烈推荐所需基本面最低分
        'buy_sentiment_min': 60, # 买入区内的情绪面门槛（区分建议买入/谨慎买入）
    },
}


def _deep_merge(base, override):
    """深度合并 override 到 base（返回新对象）"""
    result = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(result.get(k), dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def _read_config():
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"读取config.json失败: {e}")
    return {}


def _write_config(config):
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logger.error(f"写入config.json失败: {e}")
        return False


def get_strategy_params():
    """获取当前选股参数（默认值 + config.json 覆盖）"""
    with _lock:
        saved = _read_config().get('strategy', {}) or {}
    return _deep_merge(DEFAULT_STRATEGY_PARAMS, saved)


def update_strategy_params(new_params, reset=False):
    """更新选股参数并持久化
    reset=True 时忽略 new_params，直接恢复默认值
    """
    with _lock:
        config = _read_config()
        if reset:
            config['strategy'] = copy.deepcopy(DEFAULT_STRATEGY_PARAMS)
        else:
            current = config.get('strategy', {}) or {}
            config['strategy'] = _deep_merge(current, new_params or {})
        ok = _write_config(config)
    return ok


# 参数元信息：供前端渲染设置界面（键 -> 中文标签）
PARAM_LABELS = {
    'weights': {
        'technical': '技术面权重',
        'fundamental': '基本面权重',
        'sentiment': '情绪面权重',
    },
    'technical': {
        'base_score': '基础分',
        'ma_bull_score': '均线多头排列加分',
        'ma_bear_score': '均线空头排列减分',
        'rsi_oversold': 'RSI超卖阈值',
        'rsi_overbought': 'RSI超买阈值',
        'rsi_normal_score': 'RSI健康区间加分',
        'rsi_oversold_score': 'RSI超卖加分',
        'rsi_overbought_score': 'RSI超买减分',
        'macd_golden_score': 'MACD金叉加分',
        'macd_dead_score': 'MACD死叉减分',
        'boll_lower_zone': '布林带下轨区阈值',
        'boll_upper_zone': '布林带上轨区阈值',
        'boll_mid_score': '布林带中区加分',
        'boll_lower_score': '布林带近下轨加分',
        'boll_upper_score': '布林带近上轨减分',
        'vol_surge_ratio': '放量阈值(量比)',
        'vol_shrink_ratio': '缩量阈值(量比)',
        'vol_up_score': '放量上涨加分',
        'vol_down_score': '放量下跌减分',
    },
    'fundamental': {
        'base_score': '基础分',
        'indicator_bonus_threshold': '财务指标数量门槛',
        'indicator_bonus': '指标齐全加分',
        'roe_excellent': 'ROE优秀阈值(%)',
        'roe_excellent_score': 'ROE优秀加分',
        'roe_good': 'ROE良好阈值(%)',
        'roe_good_score': 'ROE良好加分',
        'roe_poor': 'ROE偏弱阈值(%)',
        'roe_poor_score': 'ROE偏弱减分',
        'debt_low': '低负债阈值(%)',
        'debt_low_score': '低负债加分',
        'debt_high': '高负债阈值(%)',
        'debt_high_score': '高负债减分',
        'rev_excellent': '营收高增阈值(%)',
        'rev_excellent_score': '营收高增加分',
        'rev_good': '营收良好阈值(%)',
        'rev_good_score': '营收良好加分',
        'rev_poor': '营收下滑阈值(%)',
        'rev_poor_score': '营收下滑减分',
        'valuation_bonus': '估值数据齐全加分',
    },
    'sentiment': {
        'confidence_news_max': '置信度封顶新闻数',
        'confidence_bonus_max': '置信度最大加分',
        'news_count_max': '新闻加分封顶数',
        'news_bonus_max': '新闻数量最大加分',
    },
    'signal': {
        'strong_buy': '强烈买入线',
        'buy': '买入线',
        'hold': '观望线',
        'sell': '减仓线',
        'strong_tech_min': '强烈推荐-技术面最低分',
        'strong_fund_min': '强烈推荐-基本面最低分',
        'buy_sentiment_min': '买入情绪门槛',
    },
}
