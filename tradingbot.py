import pandas as pd
import ta
import time
import sys
from binance.client import Client
from binance.enums import SIDE_BUY, SIDE_SELL, ORDER_TYPE_MARKET

# Enable real-time log flushing for nohup
sys.stdout.reconfigure(line_buffering=True)

# ---- API Credentials ----
api_key = '920d35d8c390f6fd6d473adaa13b9b9c02d239d1134fc'
api_secret = '3f5db0787e7307c50051ce2dac855f0bb3a6b2481b9b0f1b64ba2b4210df43e1'

client = Client(api_key, api_secret)
client.FUTURES_URL = 'https://testnet.binancefuture.com/fapi'

# ---- Config ----
SYMBOL = 'BTCUSDT'
INTERVAL = Client.KLINE_INTERVAL_1MINUTE
LIMIT = 500
ADX_THRESHOLD = 20
CAPITAL_PERCENTAGE = 0.2  # 20% of available USDT
TP_MULTIPLIER = 0.3  # 30% gain on employed capital
SL_MULTIPLIER = 0.1  # 10% loss on employed capital

def get_klines(symbol, interval, limit):
    klines = client.get_klines(symbol=symbol, interval=interval, limit=limit)
    df = pd.DataFrame(klines, columns=[
        'timestamp', 'open', 'high', 'low', 'close', 'volume',
        'close_time', 'quote_asset_volume', 'number_of_trades',
        'taker_buy_base_volume', 'taker_buy_quote_volume', 'ignore'
    ])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df[['open', 'high', 'low', 'close', 'volume']] = df[['open', 'high', 'low', 'close', 'volume']].astype(float)
    return df

def calculate_indicators(df):
    df['rsi'] = ta.momentum.RSIIndicator(df['close'], window=14).rsi()
    stoch_rsi = (df['rsi'] - df['rsi'].rolling(14).min()) / (df['rsi'].rolling(14).max() - df['rsi'].rolling(14).min())
    df['k'] = stoch_rsi.rolling(3).mean()
    df['d'] = df['k'].rolling(3).mean()

    adx = ta.trend.ADXIndicator(df['high'], df['low'], df['close'], window=14)
    df['adx'] = adx.adx()
    return df

def check_buy_signal(df):
    latest = df.iloc[-1]
    prev = df.iloc[-2]
    k_cross = prev['k'] < prev['d'] and latest['k'] > latest['d']
    oversold = latest['k'] < 0.3 and latest['d'] < 0.3
    trend = latest['adx'] > ADX_THRESHOLD
    return k_cross and oversold and trend

def get_available_usdt():
    balance = client.futures_account_balance()
    for asset in balance:
        if asset['asset'] == 'USDT':
            return float(asset['balance'])
    return 0

def monitor_trade(entry_price, qty, employed_capital):
    while True:
        try:
            mark_price_data = client.futures_mark_price(symbol=SYMBOL)
            current_price = float(mark_price_data['markPrice'])
            pnl = (current_price - entry_price) * qty * 10  # 10x leverage

            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 🔄 PnL: {pnl:.2f} USDT")

            if pnl >= employed_capital * TP_MULTIPLIER:
                print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 🎯 Take Profit Hit! Closing trade...")
                client.futures_create_order(symbol=SYMBOL, side=SIDE_SELL, type=ORDER_TYPE_MARKET, quantity=qty, reduceOnly=True)
                break
            elif pnl <= -employed_capital * SL_MULTIPLIER:
                print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 🛑 Stop Loss Hit! Closing trade...")
                client.futures_create_order(symbol=SYMBOL, side=SIDE_SELL, type=ORDER_TYPE_MARKET, quantity=qty, reduceOnly=True)
                break

            time.sleep(10)
        except Exception as e:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] ⚠️ Error monitoring trade: {e}")
            time.sleep(10)

def place_trade():
    try:
        client.futures_change_leverage(symbol=SYMBOL, leverage=10)
        price = float(client.futures_symbol_ticker(symbol=SYMBOL)['price'])
        usdt_balance = get_available_usdt()
        employed_capital = usdt_balance * CAPITAL_PERCENTAGE
        qty = round(employed_capital / price, 5)

        order = client.futures_create_order(
            symbol=SYMBOL,
            side=SIDE_BUY,
            type=ORDER_TYPE_MARKET,
            quantity=qty
        )
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] ✅ Trade Executed at {price}, Qty: {qty}, Capital: {employed_capital:.2f} USDT")

        monitor_trade(entry_price=price, qty=qty, employed_capital=employed_capital)

    except Exception as e:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] ❌ Trade failed: {e}")

def main():
    while True:
        df = get_klines(SYMBOL, INTERVAL, LIMIT)
        df = calculate_indicators(df)

        if check_buy_signal(df):
            place_trade()
        else:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 📉 No valid buy signal.")

        time.sleep(60)

if __name__ == "__main__":
    main()

