# -*- coding: utf-8 -*-
"""
Technical Analysis Engine - 技术指标计算与分析
"""
import pandas as pd
import numpy as np
from datetime import datetime


class AnalysisEngine:
    """技术分析引擎"""

    @staticmethod
    def calc_ma(df, periods=[5, 10, 20, 60]):
        """计算移动平均线"""
        for p in periods:
            if len(df) >= p:
                df[f'ma{p}'] = df['close'].rolling(window=p).mean()
            else:
                df[f'ma{p}'] = np.nan
        return df

    @staticmethod
    def calc_macd(df, fast=12, slow=26, signal=9):
        """计算MACD指标"""
        ema_fast = df['close'].ewm(span=fast, adjust=False).mean()
        ema_slow = df['close'].ewm(span=slow, adjust=False).mean()
        df['dif'] = ema_fast - ema_slow
        df['dea'] = df['dif'].ewm(span=signal, adjust=False).mean()
        df['macd'] = (df['dif'] - df['dea']) * 2
        return df

    @staticmethod
    def calc_rsi(df, periods=[6, 12, 24]):
        """计算RSI指标"""
        delta = df['close'].diff()
        for p in periods:
            gain = delta.where(delta > 0, 0).rolling(window=p).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=p).mean()
            rs = gain / loss.replace(0, np.nan)
            df[f'rsi{p}'] = (100 - (100 / (1 + rs))).fillna(50)
        return df

    @staticmethod
    def calc_kdj(df, n=9):
        """计算KDJ指标"""
        low_n = df['low'].rolling(window=n).min()
        high_n = df['high'].rolling(window=n).max()
        rsv = (df['close'] - low_n) / (high_n - low_n).replace(0, np.nan) * 100
        rsv = rsv.fillna(50)
        df['k'] = rsv.ewm(com=2, adjust=False).mean()
        df['d'] = df['k'].ewm(com=2, adjust=False).mean()
        df['j'] = 3 * df['k'] - 2 * df['d']
        return df

    @staticmethod
    def calc_boll(df, n=20, k=2):
        """计算布林带"""
        df['boll_mid'] = df['close'].rolling(window=n).mean()
        std = df['close'].rolling(window=n).std()
        df['boll_upper'] = df['boll_mid'] + k * std
        df['boll_lower'] = df['boll_mid'] - k * std
        return df

    @staticmethod
    def find_support_resistance(df, lookback=60):
        """识别支撑位和压力位"""
        recent = df.tail(lookback) if len(df) >= lookback else df
        # 近期最高最低
        recent_high = recent['high'].max()
        recent_low = recent['low'].min()
        current_price = df['close'].iloc[-1]

        # 寻找关键水平：成交密集区
        levels = []
        # 使用近期的局部高点和低点
        for i in range(2, len(recent) - 2):
            # 局部高点
            if (recent['high'].iloc[i] > recent['high'].iloc[i-1] and
                recent['high'].iloc[i] > recent['high'].iloc[i-2] and
                recent['high'].iloc[i] > recent['high'].iloc[i+1] and
                recent['high'].iloc[i] > recent['high'].iloc[i+2]):
                levels.append({'price': float(recent['high'].iloc[i]), 'type': 'resistance'})
            # 局部低点
            if (recent['low'].iloc[i] < recent['low'].iloc[i-1] and
                recent['low'].iloc[i] < recent['low'].iloc[i-2] and
                recent['low'].iloc[i] < recent['low'].iloc[i+1] and
                recent['low'].iloc[i] < recent['low'].iloc[i+2]):
                levels.append({'price': float(recent['low'].iloc[i]), 'type': 'support'})

        # 按价格排序，去重（合并相近的价位）
        levels.sort(key=lambda x: x['price'])
        merged = []
        for lv in levels:
            if merged and abs(lv['price'] - merged[-1]['price']) / merged[-1]['price'] < 0.02:
                continue
            merged.append(lv)

        # 分离支撑和压力
        supports = [lv for lv in merged if lv['price'] < current_price]
        resistances = [lv for lv in merged if lv['price'] > current_price]

        return {
            'current_price': float(current_price),
            'recent_high': float(recent_high),
            'recent_low': float(recent_low),
            'nearest_support': supports[-1]['price'] if supports else float(recent_low),
            'nearest_resistance': resistances[0]['price'] if resistances else float(recent_high),
            'support_levels': [lv['price'] for lv in supports[-3:]],
            'resistance_levels': [lv['price'] for lv in resistances[:3]]
        }

    @staticmethod
    def analyze_volume(df):
        """成交量分析"""
        if len(df) < 10:
            return {}
        recent_vol = df['volume'].tail(5).mean()
        avg_vol = df['volume'].tail(20).mean()
        vol_ratio = recent_vol / avg_vol if avg_vol > 0 else 1

        # 量能趋势：近5日均量 vs 之前15日均量
        if len(df) >= 20:
            prev_vol = df['volume'].iloc[-20:-5].mean()
            vol_trend = 'increasing' if recent_vol > prev_vol * 1.1 else (
                'decreasing' if recent_vol < prev_vol * 0.9 else 'stable')
        else:
            vol_trend = 'stable'

        # 量价关系
        last = df.iloc[-1]
        prev = df.iloc[-2]
        price_up = last['close'] > prev['close']
        vol_up = last['volume'] > prev['volume']

        if price_up and vol_up:
            pattern = "放量上涨"
        elif price_up and not vol_up:
            pattern = "缩量上涨"
        elif not price_up and vol_up:
            pattern = "放量下跌"
        else:
            pattern = "缩量下跌"

        return {
            'avg_vol_20': float(avg_vol),
            'recent_vol': float(recent_vol),
            'volume_ratio': round(float(vol_ratio), 2),
            'vol_trend': vol_trend,
            'pattern': pattern
        }

    @staticmethod
    def calc_risk_metrics(df):
        """波动率与风险指标：ATR、近14日振幅、区间高低点"""
        if len(df) < 15:
            return {}
        last = df.iloc[-1]
        prev_close = df['close'].shift(1)
        tr = pd.concat([
            df['high'] - df['low'],
            (df['high'] - prev_close).abs(),
            (df['low'] - prev_close).abs()
        ], axis=1).max(axis=1)
        atr14 = float(tr.tail(14).mean())
        close = float(last['close'])

        recent = df.tail(14)
        amp = (recent['high'] - recent['low']) / prev_close.reindex(recent.index) * 100
        amp = amp.dropna()
        high14 = float(recent['high'].max())
        low14 = float(recent['low'].min())
        range_pct = (high14 - low14) / low14 * 100 if low14 > 0 else None
        # 最大单日成交量（近14日）
        max_vol_idx = recent['volume'].idxmax()

        return {
            'atr14': round(atr14, 2),
            'atr_pct': round(atr14 / close * 100, 2) if close > 0 else None,
            'amplitude_max': round(float(amp.max()), 2) if not amp.empty else None,
            'amplitude_min': round(float(amp.min()), 2) if not amp.empty else None,
            'high_14d': round(high14, 2),
            'low_14d': round(low14, 2),
            'range_pct_14d': round(range_pct, 2) if range_pct is not None else None,
            'max_vol_date': df.loc[max_vol_idx, 'date'].strftime('%Y-%m-%d')
                            if hasattr(df.loc[max_vol_idx, 'date'], 'strftime') else str(df.loc[max_vol_idx, 'date'])[:10],
            'max_vol': float(recent['volume'].max())
        }

    @staticmethod
    def full_analysis(df):
        """完整技术分析"""
        if df is None or df.empty or len(df) < 10:
            return None

        df = df.copy()
        df = AnalysisEngine.calc_ma(df)
        df = AnalysisEngine.calc_macd(df)
        df = AnalysisEngine.calc_rsi(df)
        df = AnalysisEngine.calc_kdj(df)
        df = AnalysisEngine.calc_boll(df)

        last = df.iloc[-1]
        prev = df.iloc[-2] if len(df) >= 2 else last

        # 趋势判断
        ma5 = last.get('ma5', np.nan)
        ma10 = last.get('ma10', np.nan)
        ma20 = last.get('ma20', np.nan)
        ma60 = last.get('ma60', np.nan)
        close = last['close']

        trend = "震荡"
        if pd.notna(ma5) and pd.notna(ma20):
            if close > ma5 > ma20:
                trend = "多头排列(强势)"
            elif close < ma5 < ma20:
                trend = "空头排列(弱势)"
            elif ma5 > ma20:
                trend = "偏多震荡"
            else:
                trend = "偏空震荡"

        # MACD信号
        macd_signal = "中性"
        if pd.notna(last['dif']) and pd.notna(last['dea']):
            if last['dif'] > last['dea'] and prev['dif'] <= prev['dea']:
                macd_signal = "金叉(买入信号)"
            elif last['dif'] < last['dea'] and prev['dif'] >= prev['dea']:
                macd_signal = "死叉(卖出信号)"
            elif last['dif'] > last['dea']:
                macd_signal = "多头(偏多)"
            else:
                macd_signal = "空头(偏空)"

        # RSI信号
        rsi_val = last.get('rsi6', 50)
        rsi_signal = "中性"
        if pd.notna(rsi_val):
            if rsi_val > 80:
                rsi_signal = "超买(注意风险)"
            elif rsi_val < 20:
                rsi_signal = "超卖(关注反弹)"
            elif rsi_val > 50:
                rsi_signal = "偏强"
            else:
                rsi_signal = "偏弱"

        # KDJ信号
        k_val = last.get('k', 50)
        d_val = last.get('d', 50)
        j_val = last.get('j', 50)
        kdj_signal = "中性"
        if pd.notna(j_val):
            if j_val > 100:
                kdj_signal = "超买(注意风险)"
            elif j_val < 0:
                kdj_signal = "超卖(关注反弹)"
            elif k_val > d_val and prev.get('k', 50) <= prev.get('d', 50):
                kdj_signal = "金叉(买入信号)"
            elif k_val < d_val and prev.get('k', 50) >= prev.get('d', 50):
                kdj_signal = "死叉(卖出信号)"

        # 布林带位置
        boll_pos = "中轨附近"
        if pd.notna(last['boll_upper']) and pd.notna(last['boll_lower']):
            if close >= last['boll_upper']:
                boll_pos = "突破上轨(超强)"
            elif close <= last['boll_lower']:
                boll_pos = "跌破下轨(超弱)"
            elif close > last['boll_mid']:
                boll_pos = "中上轨之间(偏强)"
            else:
                boll_pos = "中下轨之间(偏弱)"

        # 支撑压力
        sr = AnalysisEngine.find_support_resistance(df)

        # 成交量
        vol_info = AnalysisEngine.analyze_volume(df)

        # 波动率与风险指标
        risk = AnalysisEngine.calc_risk_metrics(df)

        # 涨跌幅
        pct_change = float(last.get('pct_change', 0))

        return {
            'last_date': last['date'].strftime('%Y-%m-%d') if hasattr(last['date'], 'strftime') else str(last['date']),
            'close': float(close),
            'pct_change': pct_change,
            'trend': trend,
            'ma5': round(float(ma5), 2) if pd.notna(ma5) else None,
            'ma10': round(float(ma10), 2) if pd.notna(ma10) else None,
            'ma20': round(float(ma20), 2) if pd.notna(ma20) else None,
            'ma60': round(float(ma60), 2) if pd.notna(ma60) else None,
            'macd': {
                'dif': round(float(last['dif']), 4) if pd.notna(last['dif']) else None,
                'dea': round(float(last['dea']), 4) if pd.notna(last['dea']) else None,
                'macd': round(float(last['macd']), 4) if pd.notna(last['macd']) else None,
                'signal': macd_signal
            },
            'rsi': {
                'rsi6': round(float(rsi_val), 2) if pd.notna(rsi_val) else None,
                'rsi12': round(float(last.get('rsi12', 50)), 2) if pd.notna(last.get('rsi12', 50)) else None,
                'rsi24': round(float(last.get('rsi24', 50)), 2) if pd.notna(last.get('rsi24', 50)) else None,
                'signal': rsi_signal
            },
            'kdj': {
                'k': round(float(k_val), 2) if pd.notna(k_val) else None,
                'd': round(float(d_val), 2) if pd.notna(d_val) else None,
                'j': round(float(j_val), 2) if pd.notna(j_val) else None,
                'signal': kdj_signal
            },
            'boll': {
                'upper': round(float(last['boll_upper']), 2) if pd.notna(last['boll_upper']) else None,
                'mid': round(float(last['boll_mid']), 2) if pd.notna(last['boll_mid']) else None,
                'lower': round(float(last['boll_lower']), 2) if pd.notna(last['boll_lower']) else None,
                'position': boll_pos
            },
            'support_resistance': sr,
            'volume': vol_info,
            'risk': risk,
            # K线数据用于前端绘图
            'kline_data': AnalysisEngine._format_kline(df)
        }

    @staticmethod
    def _format_kline(df):
        """格式化K线数据供前端使用"""
        records = []
        for _, row in df.tail(60).iterrows():
            date_str = row['date'].strftime('%Y-%m-%d') if hasattr(row['date'], 'strftime') else str(row['date'])[:10]
            records.append({
                'date': date_str,
                'open': round(float(row['open']), 2),
                'close': round(float(row['close']), 2),
                'high': round(float(row['high']), 2),
                'low': round(float(row['low']), 2),
                'volume': float(row['volume']),
                'pct_change': float(row.get('pct_change', 0))
            })
        return records
