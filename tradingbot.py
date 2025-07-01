import pandas as pd
import ta
import time
from binance.client import Client
from binance.enums import *
from binance.enums import SIDE_BUY, SIDE_SELL, ORDER_TYPE_MARKET, ORDER_TYPE_LIMIT

# ---- API Credentials (do NOT share!) ----
api_key = '9ea238b11935143104c920d35d8c390f6fd6d473adaa13b9b9c02d239d1134fc'
api_secret = '3f5db0787e7307c50051ce2dac855f0bb3a6b2481b9b0f1b64ba2b4210df43e1'

# ---- Binance Futures Testnet Setup ----
client = Client(api_key, api_secret)
client.FUTURES_URL = 'https://testnet.binancefuture.com/fapi'

# ---- Parameters ----
SYMBOL = 'BTCUSDT'
INTERVAL = Client.KLINE_INTERVAL_5MINUTE
LIMIT = 500
ADX_THRESHOLD = 20
PROXIMITY_THRESHOLD = 0.008  # 0.8%

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

    pivot_high = df['high'].shift(1)
    pivot_low = df['low'].shift(1)
    pivot_close = df['close'].shift(1)
    df['pivot'] = (pivot_high + pivot_low + pivot_close) / 3
    df['s1'] = df['pivot'] - 0.382 * (pivot_high - pivot_low)
    df['s2'] = df['pivot'] - 0.618 * (pivot_high - pivot_low)
    df['s3'] = df['pivot'] - 1.0 * (pivot_high - pivot_low)
    return df

def check_buy_signal(df):
    latest = df.iloc[-1]
    prev = df.iloc[-2]

    k_cross = prev['k'] < prev['d'] and latest['k'] > latest['d']
    oversold = latest['k'] < 0.3 and latest['d'] < 0.3
    trend = latest['adx'] > ADX_THRESHOLD

    close = latest['close']
    near_support = any([
        abs(close - latest['s1']) / close < PROXIMITY_THRESHOLD,
        abs(close - latest['s2']) / close < PROXIMITY_THRESHOLD,
        abs(close - latest['s3']) / close < PROXIMITY_THRESHOLD
    ])

    return k_cross and oversold and trend and near_support

# ✅ Order function: Futures Buy + SL + TP
def mock_place_option_order(symbol):
    print(f"🔶 [FUTURES TESTNET] Placing Futures Market Buy Order for {symbol}")
    try:
        # Set leverage
        client.futures_change_leverage(symbol=symbol, leverage=10)

        # Place Market Buy Order
        order = client.futures_create_order(
            symbol=symbol,
            side=SIDE_BUY,
            type=ORDER_TYPE_MARKET,
            quantity=0.001
        )
        print("✅ Entry order placed!")

        # Get entry 
       
        entry_price =  float(client.futures_symbol_ticker(symbol=SYMBOL)['price'])

        # Calculate SL and TP
        stop_loss_price = round(entry_price * 0.90, 2)   # 10% below
        take_profit_price = round(entry_price * 1.30, 2) # 30% above

        print(f"📉 Stop-Loss at: {stop_loss_price}")
        print(f"📈 Take-Profit at: {take_profit_price}")

        # Place Take-Profit LIMIT Order
        tp_order = client.futures_create_order(
            symbol=symbol,
            side=SIDE_SELL,
            type=ORDER_TYPE_LIMIT,
            quantity=0.001,
            price=str(take_profit_price),
            timeInForce='GTC',
            reduceOnly=True
        )

        # Place Stop-Loss STOP_MARKET Order
        sl_order = client.futures_create_order(
            symbol=symbol,
            side=SIDE_SELL,
            type='STOP_MARKET',
            stopPrice=str(stop_loss_price),
            quantity=0.001,
            timeInForce='GTC',
            reduceOnly=True
        )

        print("✅ TP & SL orders placed.")
        return {
            "entry_order": order,
            "tp_order": tp_order,
            "sl_order": sl_order
        }

    except Exception as e:
        print("❌ Error placing futures or SL/TP orders:", e)
        return None

# ✅ Your existing main loop remains unchanged
def main():
    while True:
        df = get_klines(SYMBOL, INTERVAL, LIMIT)
        df = calculate_indicators(df)

        if check_buy_signal(df):
            current_price = df.iloc[-1]['close']
            result = mock_place_option_order(SYMBOL)
            print("✅ Result:", result)
        else:
            print("No valid buy signal.")

        print("Sleeping 5 minutes...\n")
        time.sleep(60 * 5)

if __name__ == "__main__":
    main()
