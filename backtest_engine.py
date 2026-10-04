"""
股票回測引擎 Stock Backtesting Engine
支援：均線交叉、RSI策略、Buy&Hold、多股票組合
"""

import json
import math
from datetime import datetime, timedelta
from typing import Optional


def calculate_sma(prices: list, period: int) -> list:
    """計算簡單移動平均線"""
    sma = []
    for i in range(len(prices)):
        if i < period - 1:
            sma.append(None)
        else:
            avg = sum(prices[i - period + 1:i + 1]) / period
            sma.append(round(avg, 4))
    return sma


def calculate_rsi(prices: list, period: int = 14) -> list:
    """計算 RSI 指標"""
    rsi = [None] * period
    gains = []
    losses = []
    
    for i in range(1, len(prices)):
        change = prices[i] - prices[i - 1]
        gains.append(max(change, 0))
        losses.append(max(-change, 0))
    
    if len(gains) < period:
        return [None] * len(prices)
    
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    
    for i in range(period, len(gains)):
        if avg_loss == 0:
            rsi.append(100)
        else:
            rs = avg_gain / avg_loss
            rsi.append(round(100 - (100 / (1 + rs)), 2))
        
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    
    # 補足最後一個
    if len(rsi) < len(prices):
        if avg_loss == 0:
            rsi.append(100)
        else:
            rs = avg_gain / avg_loss
            rsi.append(round(100 - (100 / (1 + rs)), 2))
    
    return rsi


def generate_mock_prices(symbol: str, days: int = 500, start_price: float = 100.0) -> dict:
    """產生模擬股價資料（當 yfinance 不可用時使用）"""
    import random
    random.seed(hash(symbol) % 10000)
    
    prices = [start_price]
    dates = []
    
    base_date = datetime.now() - timedelta(days=days)
    trading_day = 0
    current_date = base_date
    
    # 給每個 symbol 設定不同的趨勢
    trend_map = {
        'AAPL': 0.0004, 'TSLA': 0.0006, 'MSFT': 0.0003,
        'GOOGL': 0.0003, 'AMZN': 0.0004, 'NVDA': 0.0008,
        '2330.TW': 0.0005, '2317.TW': 0.0002, '0050.TW': 0.0003,
    }
    trend = trend_map.get(symbol, 0.0003)
    volatility = 0.018
    
    while trading_day < days:
        if current_date.weekday() < 5:  # 週一到週五
            dates.append(current_date.strftime('%Y-%m-%d'))
            if trading_day > 0:
                change = random.gauss(trend, volatility)
                new_price = prices[-1] * (1 + change)
                prices.append(round(max(new_price, 1.0), 2))
            trading_day += 1
        current_date += timedelta(days=1)
    
    return {
        'dates': dates,
        'close': prices[:len(dates)],
        'open': [round(p * random.uniform(0.995, 1.005), 2) for p in prices[:len(dates)]],
        'high': [round(p * random.uniform(1.001, 1.015), 2) for p in prices[:len(dates)]],
        'low': [round(p * random.uniform(0.985, 0.999), 2) for p in prices[:len(dates)]],
        'volume': [int(random.uniform(1e6, 5e7)) for _ in range(len(dates))],
        'source': 'simulated'
    }


def _fetch_yfinance(symbol: str, start_date: str, end_date: str) -> dict:
    """從 Yahoo Finance 抓取資料"""
    import yfinance as yf
    ticker = yf.Ticker(symbol)
    df = ticker.history(start=start_date, end=end_date)

    if df.empty:
        raise ValueError("No data returned")

    return {
        'dates': [d.strftime('%Y-%m-%d') for d in df.index],
        'close': [round(float(v), 4) for v in df['Close']],
        'open': [round(float(v), 4) for v in df['Open']],
        'high': [round(float(v), 4) for v in df['High']],
        'low': [round(float(v), 4) for v in df['Low']],
        'volume': [int(v) for v in df['Volume']],
        'source': 'yfinance'
    }


def _fetch_mock(symbol: str, start_date: str, end_date: str) -> dict:
    """產生模擬資料"""
    try:
        start = datetime.strptime(start_date, '%Y-%m-%d')
        end = datetime.strptime(end_date, '%Y-%m-%d')
        days = (end - start).days
    except Exception:
        days = 365
    return generate_mock_prices(symbol, days=days)


def fetch_stock_data(symbol: str, start_date: str, end_date: str,
                     data_source: str = 'auto') -> dict:
    """
    取得股票資料。
    data_source:
      'auto'     — 依序嘗試 IB → yfinance → 模擬資料
      'ib'       — 只用 Interactive Brokers（失敗直接報錯）
      'yfinance' — 只用 Yahoo Finance（失敗退回模擬資料）
      'mock'     — 直接使用模擬資料
    """
    errors = []

    if data_source == 'mock':
        return _fetch_mock(symbol, start_date, end_date)

    # --- IB ---
    if data_source in ('auto', 'ib'):
        try:
            from ib_data import fetch_ib_data, is_ib_available
            if is_ib_available():
                return fetch_ib_data(symbol, start_date, end_date)
            else:
                errors.append('IB: 未安裝 ib_async 套件')
        except Exception as e:
            errors.append(f'IB: {e}')
        if data_source == 'ib':
            # 指定只用 IB → 回傳錯誤讓使用者知道原因
            return {'error': 'IB 資料抓取失敗：' + '; '.join(errors)}

    # --- yfinance ---
    if data_source in ('auto', 'yfinance'):
        try:
            return _fetch_yfinance(symbol, start_date, end_date)
        except Exception as e:
            errors.append(f'yfinance: {e}')

    # --- 模擬資料（最後手段）---
    return _fetch_mock(symbol, start_date, end_date)


def run_ma_cross_strategy(prices: list, dates: list, capital: float,
                           short_period: int = 20, long_period: int = 60) -> dict:
    """均線交叉策略回測"""
    short_ma = calculate_sma(prices, short_period)
    long_ma = calculate_sma(prices, long_period)
    
    cash = capital
    shares = 0
    trades = []
    portfolio_values = []
    position = 'out'
    
    for i in range(len(prices)):
        portfolio_values.append(round(cash + shares * prices[i], 2))
        
        if short_ma[i] is None or long_ma[i] is None:
            continue
        
        if i == 0:
            continue
        
        prev_short = short_ma[i - 1]
        prev_long = long_ma[i - 1]
        
        if prev_short is None or prev_long is None:
            continue
        
        # 金叉：買入
        if prev_short <= prev_long and short_ma[i] > long_ma[i] and position == 'out':
            shares = math.floor(cash / prices[i])
            if shares > 0:
                cost = shares * prices[i]
                cash -= cost
                position = 'in'
                trades.append({
                    'date': dates[i],
                    'action': 'BUY',
                    'price': prices[i],
                    'shares': shares,
                    'value': round(cost, 2)
                })
        
        # 死叉：賣出
        elif prev_short >= prev_long and short_ma[i] < long_ma[i] and position == 'in':
            revenue = shares * prices[i]
            cash += revenue
            trades.append({
                'date': dates[i],
                'action': 'SELL',
                'price': prices[i],
                'shares': shares,
                'value': round(revenue, 2)
            })
            shares = 0
            position = 'out'
    
    # 期末結算（非實際交易，僅按最後收盤價評估未平倉部位）
    final_value = cash + shares * prices[-1]
    if shares > 0:
        trades.append({
            'date': dates[-1],
            'action': '期末持有',
            'price': prices[-1],
            'shares': shares,
            'value': round(shares * prices[-1], 2),
            'note': '回測結束時仍持有，按最後收盤價估值（非實際賣出）',
            'is_settlement': True
        })
    
    return {
        'strategy': 'MA Cross',
        'params': {'short_period': short_period, 'long_period': long_period},
        'final_position': {
            'shares': shares,
            'stock_value': round(shares * prices[-1], 2),
            'cash': round(cash, 2),
            'holding': shares > 0
        },
        'initial_capital': capital,
        'final_value': round(final_value, 2),
        'total_return': round((final_value / capital - 1) * 100, 2),
        'trades': trades,
        'portfolio_values': portfolio_values,
        'indicators': {'short_ma': short_ma, 'long_ma': long_ma}
    }


def run_rsi_strategy(prices: list, dates: list, capital: float,
                      period: int = 14, oversold: int = 30, overbought: int = 70) -> dict:
    """RSI 超買超賣策略"""
    rsi = calculate_rsi(prices, period)
    
    cash = capital
    shares = 0
    trades = []
    portfolio_values = []
    position = 'out'
    
    for i in range(len(prices)):
        portfolio_values.append(round(cash + shares * prices[i], 2))
        
        if rsi[i] is None or i == 0:
            continue
        
        prev_rsi = rsi[i - 1]
        if prev_rsi is None:
            continue
        
        # RSI 從超賣區域往上穿越：買入
        if prev_rsi <= oversold and rsi[i] > oversold and position == 'out':
            shares = math.floor(cash / prices[i])
            if shares > 0:
                cost = shares * prices[i]
                cash -= cost
                position = 'in'
                trades.append({
                    'date': dates[i],
                    'action': 'BUY',
                    'price': prices[i],
                    'shares': shares,
                    'value': round(cost, 2)
                })
        
        # RSI 從超買區域往下穿越：賣出
        elif prev_rsi >= overbought and rsi[i] < overbought and position == 'in':
            revenue = shares * prices[i]
            cash += revenue
            trades.append({
                'date': dates[i],
                'action': 'SELL',
                'price': prices[i],
                'shares': shares,
                'value': round(revenue, 2)
            })
            shares = 0
            position = 'out'
    
    # 期末結算（非實際交易，僅按最後收盤價評估未平倉部位）
    final_value = cash + shares * prices[-1]
    if shares > 0:
        trades.append({
            'date': dates[-1],
            'action': '期末持有',
            'price': prices[-1],
            'shares': shares,
            'value': round(shares * prices[-1], 2),
            'note': '回測結束時仍持有，按最後收盤價估值（非實際賣出）',
            'is_settlement': True
        })
    
    return {
        'strategy': 'RSI',
        'params': {'period': period, 'oversold': oversold, 'overbought': overbought},
        'final_position': {
            'shares': shares,
            'stock_value': round(shares * prices[-1], 2),
            'cash': round(cash, 2),
            'holding': shares > 0
        },
        'initial_capital': capital,
        'final_value': round(final_value, 2),
        'total_return': round((final_value / capital - 1) * 100, 2),
        'trades': trades,
        'portfolio_values': portfolio_values,
        'indicators': {'rsi': rsi}
    }


def run_buy_hold_strategy(prices: list, dates: list, capital: float) -> dict:
    """Buy & Hold 策略"""
    shares = math.floor(capital / prices[0])
    cost = shares * prices[0]
    remaining_cash = capital - cost
    
    portfolio_values = [round(remaining_cash + shares * p, 2) for p in prices]
    final_value = remaining_cash + shares * prices[-1]
    
    trades = [
        {'date': dates[0], 'action': 'BUY', 'price': prices[0], 'shares': shares, 'value': round(cost, 2)},
        {'date': dates[-1], 'action': '期末持有', 'price': prices[-1], 'shares': shares,
         'value': round(shares * prices[-1], 2),
         'note': '回測結束時仍持有，按最後收盤價估值（非實際賣出）',
         'is_settlement': True}
    ]
    
    return {
        'strategy': 'Buy & Hold',
        'params': {},
        'final_position': {
            'shares': shares,
            'stock_value': round(shares * prices[-1], 2),
            'cash': round(remaining_cash, 2),
            'holding': shares > 0
        },
        'initial_capital': capital,
        'final_value': round(final_value, 2),
        'total_return': round((final_value / capital - 1) * 100, 2),
        'trades': trades,
        'portfolio_values': portfolio_values,
        'indicators': {}
    }


def run_fixed_ratio_strategy(prices: list, dates: list, capital: float,
                              stock_ratio: float = 0.5, rebalance_days: int = 30) -> dict:
    """
    固定比例再平衡策略
    維持股票:現金 = stock_ratio:(1-stock_ratio)
    每隔 rebalance_days 個交易日重新調整回目標比例
    """
    cash_ratio = 1.0 - stock_ratio

    # 初始配置
    target_stock_value = capital * stock_ratio
    shares = math.floor(target_stock_value / prices[0])
    initial_stock_cost = shares * prices[0]
    cash = capital - initial_stock_cost

    trades = []
    portfolio_values = []
    stock_values = []   # 股票部位價值
    cash_values = []    # 現金部位價值
    rebalance_log = []  # 再平衡記錄
    last_rebalance_idx = 0

    trades.append({
        'date': dates[0],
        'action': '初始買入',
        'price': prices[0],
        'shares': shares,
        'value': round(initial_stock_cost, 2),
        'note': f'股票 {stock_ratio*100:.0f}% / 現金 {cash_ratio*100:.0f}%'
    })

    for i in range(len(prices)):
        stock_val = shares * prices[i]
        total_val = cash + stock_val
        portfolio_values.append(round(total_val, 2))
        stock_values.append(round(stock_val, 2))
        cash_values.append(round(cash, 2))

        # 到達再平衡週期（第一天不再平衡）
        if i > 0 and (i - last_rebalance_idx) >= rebalance_days:
            current_stock_ratio = stock_val / total_val if total_val > 0 else 0
            target_stock_val = total_val * stock_ratio
            diff = target_stock_val - stock_val  # 正數=需買股，負數=需賣股

            rebalanced = False
            action_desc = ''

            if diff > prices[i]:  # 需買進股票
                shares_to_buy = math.floor(diff / prices[i])
                cost = shares_to_buy * prices[i]
                if shares_to_buy > 0 and cash >= cost:
                    cash -= cost
                    shares += shares_to_buy
                    action_desc = f'再平衡買入 {shares_to_buy} 股'
                    trades.append({
                        'date': dates[i],
                        'action': '再平衡(買入)',
                        'price': prices[i],
                        'shares': shares_to_buy,
                        'value': round(cost, 2),
                        'note': f'前比例 {current_stock_ratio*100:.1f}% → 目標 {stock_ratio*100:.0f}%'
                    })
                    rebalanced = True

            elif diff < -prices[i]:  # 需賣出股票
                shares_to_sell = math.floor(-diff / prices[i])
                if shares_to_sell > 0 and shares_to_sell <= shares:
                    revenue = shares_to_sell * prices[i]
                    cash += revenue
                    shares -= shares_to_sell
                    action_desc = f'再平衡賣出 {shares_to_sell} 股'
                    trades.append({
                        'date': dates[i],
                        'action': '再平衡(賣出)',
                        'price': prices[i],
                        'shares': shares_to_sell,
                        'value': round(revenue, 2),
                        'note': f'前比例 {current_stock_ratio*100:.1f}% → 目標 {stock_ratio*100:.0f}%'
                    })
                    rebalanced = True
            else:
                action_desc = '比例已在目標範圍內，不需調整'

            # 更新再平衡後的實際值
            new_stock_val = shares * prices[i]
            new_total = cash + new_stock_val
            stock_values[-1] = round(new_stock_val, 2)
            cash_values[-1] = round(cash, 2)
            portfolio_values[-1] = round(new_total, 2)

            rebalance_log.append({
                'date': dates[i],
                'day_index': i,
                'before_ratio': round(current_stock_ratio * 100, 1),
                'after_ratio': round((shares * prices[i]) / new_total * 100, 1) if new_total > 0 else 0,
                'action': action_desc,
                'rebalanced': rebalanced
            })
            last_rebalance_idx = i

    final_value = cash + shares * prices[-1]

    return {
        'strategy': 'Fixed Ratio',
        'params': {
            'stock_ratio': stock_ratio,
            'cash_ratio': cash_ratio,
            'rebalance_days': rebalance_days
        },
        'initial_capital': capital,
        'final_value': round(final_value, 2),
        'total_return': round((final_value / capital - 1) * 100, 2),
        'trades': trades,
        'portfolio_values': portfolio_values,
        'stock_values': stock_values,
        'cash_values': cash_values,
        'rebalance_log': rebalance_log,
        'rebalance_count': sum(1 for r in rebalance_log if r['rebalanced']),
        'indicators': {}
    }


def run_ma_rebalance_strategy(prices: list, dates: list, capital: float,
                               bull_ratio: float = 0.7, bear_ratio: float = 0.3,
                               ma_short: int = 20, ma_long: int = 60) -> dict:
    """
    MA 交叉再平衡策略
    - 金叉（短均線上穿長均線）→ 調整至多頭比例（bull_ratio）
    - 死叉（短均線下穿長均線）→ 調整至空頭比例（bear_ratio）
    初始以兩者平均比例買入
    """
    short_ma = calculate_sma(prices, ma_short)
    long_ma = calculate_sma(prices, ma_long)

    # 初始比例：多空均值中性
    initial_ratio = (bull_ratio + bear_ratio) / 2.0
    shares = math.floor(capital * initial_ratio / prices[0])
    initial_cost = shares * prices[0]
    cash = capital - initial_cost

    mode = 'neutral'
    golden_cross_count = 0
    death_cross_count = 0

    trades = []
    portfolio_values = []
    stock_values = []
    cash_values = []
    rebalance_log = []

    trades.append({
        'date': dates[0],
        'action': '初始買入',
        'price': prices[0],
        'shares': shares,
        'value': round(initial_cost, 2),
        'note': f'中性比例 {initial_ratio*100:.0f}%（多頭{bull_ratio*100:.0f}% / 空頭{bear_ratio*100:.0f}% 均值）'
    })

    for i in range(len(prices)):
        stock_val = shares * prices[i]
        total_val = cash + stock_val
        portfolio_values.append(round(total_val, 2))
        stock_values.append(round(stock_val, 2))
        cash_values.append(round(cash, 2))

        if short_ma[i] is None or long_ma[i] is None or i == 0:
            continue
        prev_short = short_ma[i - 1]
        prev_long = long_ma[i - 1]
        if prev_short is None or prev_long is None:
            continue

        # 偵測交叉信號
        new_mode = None
        if prev_short <= prev_long and short_ma[i] > long_ma[i]:
            new_mode = 'bull'
            golden_cross_count += 1
        elif prev_short >= prev_long and short_ma[i] < long_ma[i]:
            new_mode = 'bear'
            death_cross_count += 1

        # 只在模式切換時才再平衡
        if new_mode is None or new_mode == mode:
            continue

        mode = new_mode
        target_ratio = bull_ratio if mode == 'bull' else bear_ratio
        target_stock_val = total_val * target_ratio
        diff = target_stock_val - stock_val  # 正=買股，負=賣股

        before_ratio = round(stock_val / total_val * 100, 1) if total_val > 0 else 0
        signal_label = '金叉 ↑' if mode == 'bull' else '死叉 ↓'
        rebalanced = False
        action_desc = f'{signal_label} — 比例未達調整門檻，維持現狀'

        if diff > prices[i]:  # 買股
            shares_to_buy = math.floor(diff / prices[i])
            cost = shares_to_buy * prices[i]
            if shares_to_buy > 0 and cash >= cost:
                cash -= cost
                shares += shares_to_buy
                action_desc = f'{signal_label} 買入 {shares_to_buy} 股'
                trades.append({
                    'date': dates[i],
                    'action': '再平衡(買入)',
                    'price': prices[i],
                    'shares': shares_to_buy,
                    'value': round(cost, 2),
                    'note': f'{signal_label} → 目標 {target_ratio*100:.0f}%'
                })
                rebalanced = True
            else:
                action_desc = f'{signal_label} 現金不足，無法完整調整'

        elif diff < -prices[i]:  # 賣股
            shares_to_sell = math.floor(-diff / prices[i])
            if shares_to_sell > 0 and shares_to_sell <= shares:
                revenue = shares_to_sell * prices[i]
                cash += revenue
                shares -= shares_to_sell
                action_desc = f'{signal_label} 賣出 {shares_to_sell} 股'
                trades.append({
                    'date': dates[i],
                    'action': '再平衡(賣出)',
                    'price': prices[i],
                    'shares': shares_to_sell,
                    'value': round(revenue, 2),
                    'note': f'{signal_label} → 目標 {target_ratio*100:.0f}%'
                })
                rebalanced = True

        # 更新當天最終值
        new_stock_val = shares * prices[i]
        new_total = cash + new_stock_val
        stock_values[-1] = round(new_stock_val, 2)
        cash_values[-1] = round(cash, 2)
        portfolio_values[-1] = round(new_total, 2)

        after_ratio = round(new_stock_val / new_total * 100, 1) if new_total > 0 else 0
        rebalance_log.append({
            'date': dates[i],
            'signal': signal_label,
            'mode': mode,
            'target_ratio': round(target_ratio * 100, 0),
            'before_ratio': before_ratio,
            'after_ratio': after_ratio,
            'action': action_desc,
            'rebalanced': rebalanced
        })

    final_value = cash + shares * prices[-1]

    return {
        'strategy': 'MA Rebalance',
        'params': {
            'bull_ratio': bull_ratio,
            'bear_ratio': bear_ratio,
            'ma_short': ma_short,
            'ma_long': ma_long,
            'initial_ratio': initial_ratio
        },
        'initial_capital': capital,
        'final_value': round(final_value, 2),
        'total_return': round((final_value / capital - 1) * 100, 2),
        'trades': trades,
        'portfolio_values': portfolio_values,
        'stock_values': stock_values,
        'cash_values': cash_values,
        'rebalance_log': rebalance_log,
        'rebalance_count': sum(1 for r in rebalance_log if r['rebalanced']),
        'golden_cross_count': golden_cross_count,
        'death_cross_count': death_cross_count,
        'indicators': {'short_ma': short_ma, 'long_ma': long_ma}
    }


def run_threshold_rebalance_strategy(prices: list, dates: list, capital: float,
                                      target_ratio: float = 0.5,
                                      threshold: float = 0.05) -> dict:
    """
    閾值再平衡策略
    每天檢查股票比例是否偏離目標超過 threshold，
    若超過則補回 target_ratio。不看時間、不看均線。
    """
    # 初始買入
    shares = math.floor(capital * target_ratio / prices[0])
    initial_cost = shares * prices[0]
    cash = capital - initial_cost

    trades = [{
        'date': dates[0],
        'action': '初始買入',
        'price': prices[0],
        'shares': shares,
        'value': round(initial_cost, 2),
        'note': f'初始比例 {target_ratio*100:.0f}%'
    }]

    portfolio_values = []
    stock_values = []
    cash_values = []
    ratio_history = []   # 每日股票佔比 (%)，用於繪圖
    rebalance_log = []

    for i in range(len(prices)):
        stock_val = shares * prices[i]
        total_val = cash + stock_val
        current_ratio = stock_val / total_val if total_val > 0 else 0

        portfolio_values.append(round(total_val, 2))
        stock_values.append(round(stock_val, 2))
        cash_values.append(round(cash, 2))
        ratio_history.append(round(current_ratio * 100, 2))

        if i == 0:
            continue

        deviation = current_ratio - target_ratio   # 正=偏多，負=偏少

        if abs(deviation) < threshold:
            continue  # 在容忍區間內，不動

        # 觸發再平衡：補回 target_ratio
        target_stock_val = total_val * target_ratio
        diff = target_stock_val - stock_val   # 正=買股，負=賣股

        rebalanced = False
        direction = '比例過高 → 賣股' if deviation > 0 else '比例過低 → 買股'

        if diff > prices[i]:   # 買股
            shares_to_buy = math.floor(diff / prices[i])
            cost = shares_to_buy * prices[i]
            if shares_to_buy > 0 and cash >= cost:
                cash -= cost
                shares += shares_to_buy
                trades.append({
                    'date': dates[i],
                    'action': '再平衡(買入)',
                    'price': prices[i],
                    'shares': shares_to_buy,
                    'value': round(cost, 2),
                    'note': f'偏離 {deviation*100:+.1f}% → 補回 {target_ratio*100:.0f}%'
                })
                rebalanced = True

        elif diff < -prices[i]:   # 賣股
            shares_to_sell = math.floor(-diff / prices[i])
            if shares_to_sell > 0 and shares_to_sell <= shares:
                revenue = shares_to_sell * prices[i]
                cash += revenue
                shares -= shares_to_sell
                trades.append({
                    'date': dates[i],
                    'action': '再平衡(賣出)',
                    'price': prices[i],
                    'shares': shares_to_sell,
                    'value': round(revenue, 2),
                    'note': f'偏離 {deviation*100:+.1f}% → 補回 {target_ratio*100:.0f}%'
                })
                rebalanced = True

        # 更新當天最終值
        new_stock_val = shares * prices[i]
        new_total = cash + new_stock_val
        after_ratio = new_stock_val / new_total * 100 if new_total > 0 else 0

        stock_values[-1] = round(new_stock_val, 2)
        cash_values[-1] = round(cash, 2)
        portfolio_values[-1] = round(new_total, 2)
        ratio_history[-1] = round(after_ratio, 2)

        rebalance_log.append({
            'date': dates[i],
            'deviation': round(deviation * 100, 1),
            'direction': direction,
            'before_ratio': round(current_ratio * 100, 1),
            'after_ratio': round(after_ratio, 1),
            'rebalanced': rebalanced
        })

    final_value = cash + shares * prices[-1]

    return {
        'strategy': 'Threshold Rebalance',
        'params': {
            'target_ratio': target_ratio,
            'threshold': threshold
        },
        'initial_capital': capital,
        'final_value': round(final_value, 2),
        'total_return': round((final_value / capital - 1) * 100, 2),
        'trades': trades,
        'portfolio_values': portfolio_values,
        'stock_values': stock_values,
        'cash_values': cash_values,
        'ratio_history': ratio_history,
        'rebalance_log': rebalance_log,
        'rebalance_count': len(rebalance_log),
        'indicators': {}
    }


def run_portfolio_strategy(symbols_weights: dict, capital: float,
                            start_date: str, end_date: str, rebalance: str = 'none',
                            data_source: str = 'auto') -> dict:
    """多股票組合策略（按權重分配資金）"""
    portfolio_data = {}
    all_dates = None
    
    for symbol, weight in symbols_weights.items():
        stock_capital = capital * weight
        data = fetch_stock_data(symbol, start_date, end_date, data_source)
        if 'error' in data:
            return data
        bh = run_buy_hold_strategy(data['close'], data['dates'], stock_capital)
        
        portfolio_data[symbol] = {
            'weight': weight,
            'capital': stock_capital,
            'data': data,
            'result': bh
        }
        
        if all_dates is None:
            all_dates = data['dates']
    
    # 計算組合總價值
    # 找最短的日期序列
    min_len = min(len(v['result']['portfolio_values']) for v in portfolio_data.values())
    
    combined_values = []
    for i in range(min_len):
        total = sum(v['result']['portfolio_values'][i] for v in portfolio_data.values())
        combined_values.append(round(total, 2))
    
    final_value = combined_values[-1]
    
    return {
        'strategy': 'Portfolio',
        'params': {'weights': symbols_weights, 'rebalance': rebalance},
        'initial_capital': capital,
        'final_value': round(final_value, 2),
        'total_return': round((final_value / capital - 1) * 100, 2),
        'portfolio_values': combined_values,
        'portfolio_breakdown': {
            sym: {
                'weight': d['weight'],
                'capital': d['capital'],
                'final_value': round(d['result']['portfolio_values'][-1], 2),
                'return': d['result']['total_return']
            } for sym, d in portfolio_data.items()
        },
        'dates': all_dates[:min_len] if all_dates else []
    }


def calculate_metrics(portfolio_values: list, initial_capital: float) -> dict:
    """計算回測績效指標"""
    if not portfolio_values or len(portfolio_values) < 2:
        return {}
    
    # 計算每日回報
    daily_returns = []
    for i in range(1, len(portfolio_values)):
        r = (portfolio_values[i] - portfolio_values[i - 1]) / portfolio_values[i - 1]
        daily_returns.append(r)
    
    if not daily_returns:
        return {}
    
    # 最大回撤
    peak = portfolio_values[0]
    max_drawdown = 0
    for v in portfolio_values:
        if v > peak:
            peak = v
        dd = (peak - v) / peak
        if dd > max_drawdown:
            max_drawdown = dd
    
    # 夏普比率（假設年化無風險利率 2%）
    avg_daily_return = sum(daily_returns) / len(daily_returns)
    if len(daily_returns) > 1:
        variance = sum((r - avg_daily_return) ** 2 for r in daily_returns) / (len(daily_returns) - 1)
        std_dev = math.sqrt(variance)
    else:
        std_dev = 0
    
    risk_free_daily = 0.02 / 252
    sharpe = ((avg_daily_return - risk_free_daily) / std_dev * math.sqrt(252)) if std_dev > 0 else 0
    
    # 勝率（正回報天數）
    win_days = sum(1 for r in daily_returns if r > 0)
    win_rate = win_days / len(daily_returns) * 100
    
    # 年化報酬
    total_days = len(portfolio_values)
    total_return = (portfolio_values[-1] / initial_capital) - 1
    annual_return = ((1 + total_return) ** (252 / total_days) - 1) * 100 if total_days > 0 else 0
    
    return {
        'max_drawdown': round(max_drawdown * 100, 2),
        'sharpe_ratio': round(sharpe, 3),
        'win_rate': round(win_rate, 2),
        'annual_return': round(annual_return, 2),
        'volatility': round(std_dev * math.sqrt(252) * 100, 2)
    }


def run_backtest(config: dict) -> dict:
    """主要回測入口"""
    symbol = config.get('symbol', 'AAPL')
    start_date = config.get('start_date', '2022-01-01')
    end_date = config.get('end_date', '2024-12-31')
    capital = float(config.get('capital', 100000))
    strategy = config.get('strategy', 'buy_hold')
    data_source = config.get('data_source', 'auto')
    
    # 取得資料
    data = fetch_stock_data(symbol, start_date, end_date, data_source)
    if 'error' in data:
        return data
    prices = data['close']
    dates = data['dates']
    
    if not prices:
        return {'error': '無法取得股票資料'}
    
    # 執行策略
    if strategy == 'ma_cross':
        short_period = int(config.get('ma_short', 20))
        long_period = int(config.get('ma_long', 60))
        result = run_ma_cross_strategy(prices, dates, capital, short_period, long_period)
    elif strategy == 'rsi':
        period = int(config.get('rsi_period', 14))
        oversold = int(config.get('rsi_oversold', 30))
        overbought = int(config.get('rsi_overbought', 70))
        result = run_rsi_strategy(prices, dates, capital, period, oversold, overbought)
    elif strategy == 'fixed_ratio':
        stock_ratio = float(config.get('stock_ratio', 0.5))
        rebalance_days = int(config.get('rebalance_days', 30))
        result = run_fixed_ratio_strategy(prices, dates, capital, stock_ratio, rebalance_days)
    elif strategy == 'ma_rebalance':
        bull_ratio = float(config.get('bull_ratio', 0.7))
        bear_ratio = float(config.get('bear_ratio', 0.3))
        ma_short = int(config.get('ma_short', 20))
        ma_long = int(config.get('ma_long', 60))
        result = run_ma_rebalance_strategy(prices, dates, capital, bull_ratio, bear_ratio, ma_short, ma_long)
    elif strategy == 'threshold_rebalance':
        target_ratio = float(config.get('target_ratio', 0.5))
        threshold = float(config.get('threshold', 0.05))
        result = run_threshold_rebalance_strategy(prices, dates, capital, target_ratio, threshold)
    else:  # buy_hold
        result = run_buy_hold_strategy(prices, dates, capital)
    
    # 計算績效指標
    metrics = calculate_metrics(result['portfolio_values'], capital)
    result['metrics'] = metrics
    result['stock_data'] = data
    result['dates'] = dates
    
    return result


if __name__ == '__main__':
    # 命令列模式
    import sys
    
    if len(sys.argv) > 1:
        config_file = sys.argv[1]
        with open(config_file, 'r') as f:
            config = json.load(f)
    else:
        # 預設測試
        config = {
            'symbol': 'AAPL',
            'start_date': '2022-01-01',
            'end_date': '2024-12-31',
            'capital': 100000,
            'strategy': 'ma_cross',
            'ma_short': 20,
            'ma_long': 60
        }
    
    result = run_backtest(config)
    print(json.dumps(result, ensure_ascii=False, indent=2))
