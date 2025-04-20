import streamlit as st
import requests
import plotly.graph_objs as go
import pandas as pd
from datetime import datetime
from textblob import TextBlob
from sklearn.linear_model import LinearRegression
import numpy as np

# ---- SETUP ----
st.set_page_config(page_title="Crypto Dashboard", layout="wide")
st.title("🚀 Live Crypto Dashboard")

# ---- MOBILE MODE TOGGLE ----
mobile_mode = st.sidebar.toggle("📱 Mobile Mode", value=False)

# ---- FETCH COIN DATA (COINLORE) ----
all_coins = requests.get("https://api.coinlore.net/api/tickers/").json().get("data", [])
coin_names = [f"{coin['name']} ({coin['symbol']})" for coin in all_coins]
coin_lookup = {f"{coin['name']} ({coin['symbol']})": coin for coin in all_coins}

# ---- SESSION STATE TO REMEMBER COIN SELECTION ----
if "selected_coin" not in st.session_state:
    st.session_state.selected_coin = coin_names[0]

# ---- DROPDOWN SELECTOR ----
st.subheader("🔍 Explore a Coin")
selected_coin = st.selectbox("Choose a cryptocurrency:", coin_names, index=coin_names.index(st.session_state.selected_coin))
st.session_state.selected_coin = selected_coin
coin_data = coin_lookup[selected_coin]

# ---- REFRESH BUTTON ----
if st.button("🔄 Refresh Data"):
    st.rerun()

# ---- GLOBAL STATS (COINLORE) ----
try:
    global_data = requests.get("https://api.coinlore.net/api/global/").json()[0]
    st.metric("🌍 Total Market Cap (USD)", f"${int(global_data.get('total_mcap', 0)):,}")
    st.metric("📊 24h Volume", f"${int(global_data.get('total_volume', 0)):,}")

    # Market Sentiment Gauge
    top10 = requests.get("https://api.coinlore.net/api/tickers/?limit=10").json()["data"]
    green = sum(float(c["percent_change_24h"]) > 0 for c in top10)
    red = sum(float(c["percent_change_24h"]) < 0 for c in top10)

    if green > red:
        st.success("📈 Market Sentiment: **Bullish**")
    elif red > green:
        st.error("📉 Market Sentiment: **Bearish**")
    else:
        st.info("⚖️ Market Sentiment: **Neutral**")

except Exception as e:
    st.error("Error fetching global stats.")
    st.exception(e)

# ---- BTC DOMINANCE (COINMARKETCAP) ----
st.markdown("---")
st.subheader("🧠 BTC Dominance (via CoinMarketCap)")
CMC_API_KEY = "a0180469-d0b4-417b-88a8-815272576d44"
headers = {
    "Accepts": "application/json",
    "X-CMC_PRO_API_KEY": CMC_API_KEY
}
try:
    cmc_url = "https://pro-api.coinmarketcap.com/v1/global-metrics/quotes/latest"
    response = requests.get(cmc_url, headers=headers)
    btc_dominance = response.json().get("data", {}).get("btc_dominance", None)
    if btc_dominance is not None:
        st.metric(label="Bitcoin Dominance", value=f"{btc_dominance:.2f}%")
    else:
        st.warning("Could not fetch BTC dominance.")
except Exception as e:
    st.warning("CoinMarketCap BTC dominance fetch failed.")
    st.exception(e)

st.markdown("---")
st.write(f"### 💰 {coin_data['name']} ({coin_data['symbol']})")
st.metric("Price (USD)", f"${coin_data['price_usd']}", delta=f"{coin_data['percent_change_24h']}%")

# ---- CANDLESTICK CHART (REAL OHLC FROM BINANCE) ----
# Some symbols like BNB or USDC might not have a direct Binance match
binance_symbol = f"{coin_data['symbol'].upper()}USDT"

# Optional: override for common mismatches
symbol_overrides = {
    "IOTA": "IOTAUSDT",
    "MIOTA": "IOTAUSDT",
    "BCH": "BCHUSDT",
    "USDC": "USDCUSDT",  # Sometimes may not be available
}
binance_symbol = symbol_overrides.get(coin_data["symbol"].upper(), binance_symbol)


try:
    binance_url = "https://api.binance.com/api/v3/klines"
    params = {
        "symbol": binance_symbol,
        "interval": "1d",
        "limit": 180
    }
    response = requests.get(binance_url, params=params)
    data = response.json()

    if isinstance(data, list) and len(data) > 0:
        df = pd.DataFrame(data, columns=[
            "open_time", "open", "high", "low", "close", "volume",
            "close_time", "quote_asset_volume", "number_of_trades",
            "taker_buy_base_volume", "taker_buy_quote_volume", "ignore"
        ])
        df["open_time"] = pd.to_datetime(df["open_time"], unit='ms')
        df[["open", "high", "low", "close"]] = df[["open", "high", "low", "close"]].astype(float)

        display_df = df.tail(60)

        fig = go.Figure(data=[go.Candlestick(
            x=display_df["open_time"],
            open=display_df["open"],
            high=display_df["high"],
            low=display_df["low"],
            close=display_df["close"],
            increasing_line_color='green',
            decreasing_line_color='red'
        )])
        fig.update_layout(
            title=f"{selected_coin} - 60-Day Candlestick Chart (Binance)",
            xaxis_title="Date",
            yaxis_title="Price (USD)",
            template="plotly_dark",
            xaxis_rangeslider_visible=False,
            height=500 if not mobile_mode else 350
        )
        st.plotly_chart(fig, use_container_width=True)

        # ---- PRICE PREDICTION ----
        st.subheader("🤖 Price Prediction (Next Day)")
        df['timestamp'] = df['open_time'].map(datetime.timestamp)
        model = LinearRegression()
        model.fit(df[['timestamp']], df[['close']])

        next_day = df['timestamp'].iloc[-1] + 86400  # add 1 day in seconds
        prediction = model.predict([[next_day]])[0][0]
        st.success(f"📈 Predicted Price for Next Day: ${prediction:.2f}")

    else:
        st.warning("No OHLC data found for this coin on Binance.")
except Exception as e:
    st.warning("Failed to load OHLC data from Binance.")
    st.exception(e)

# ---- WALLET TRACKER ----
st.markdown("---")
st.subheader(f"🦈 Wallet Tracker for {coin_data['symbol']}")

if coin_data['symbol'].upper() == "BTC":
    btc_address = st.text_input("Enter a BTC address to view recent transactions")
    if btc_address:
        try:
            balance_url = f"https://mempool.space/api/address/{btc_address}"
            balance_data = requests.get(balance_url).json()
            btc_balance = balance_data.get("chain_stats", {}).get("funded_txo_sum", 0) - balance_data.get("chain_stats", {}).get("spent_txo_sum", 0)
            st.info(f"**BTC Balance:** {btc_balance / 1e8:.8f} BTC")
        except Exception as e:
            st.error("Failed to fetch BTC balance.")
            st.exception(e)

elif coin_data['symbol'].upper() == "ETH":
    eth_address = st.text_input("Enter an ETH address to view recent transactions")
    if eth_address:
        try:
            ETHERSCAN_API = "2P87NYEHZC2DH5ZAK66AN7KBPDCMF9DF53"
            balance_params = {
                "module": "account",
                "action": "balance",
                "address": eth_address,
                "tag": "latest",
                "apikey": ETHERSCAN_API
            }
            balance_response = requests.get("https://api.etherscan.io/api", params=balance_params).json()
            eth_balance = int(balance_response["result"]) / 1e18
            st.info(f"**ETH Balance:** {eth_balance:.6f} ETH")
        except Exception as e:
            st.error("Failed to fetch ETH balance.")
            st.exception(e)
else:
    st.info("🔍 Wallet tracking is currently supported only for BTC and ETH.")

# ---- NEWS SENTIMENT ----
st.markdown("---")
st.subheader(f"📰 News Sentiment for {coin_data['symbol']}")

# CryptoPanic News
st.write("#### 🔍 From CryptoPanic:")
try:
    CP_API_KEY = "75ee95d93ce89cb076283c7de5e445a3853ea094"
    symbol = coin_data["symbol"]
    news_url = f"https://cryptopanic.com/api/v1/posts/?auth_token={CP_API_KEY}&currencies={symbol}&public=true"
    news_response = requests.get(news_url)
    news_data = news_response.json().get("results", [])[:5]

    if not news_data:
        st.info("No CryptoPanic news articles found.")
    else:
        for article in news_data:
            title = article.get("title")
            sentiment = TextBlob(title).sentiment.polarity
            emoji = "🔺" if sentiment > 0 else "🔻" if sentiment < 0 else "➖"
            st.write(f"{emoji} **{title}**")
except Exception as e:
    st.warning("Unable to load CryptoPanic sentiment data.")
    st.exception(e)

# CoinMarketCap News
st.write("#### 📰 From CoinMarketCap:")
try:
    cmc_news_url = f"https://pro-api.coinmarketcap.com/v1/content/posts/latest?symbol={symbol}"
    cmc_news_response = requests.get(cmc_news_url, headers=headers)
    cmc_news_data = cmc_news_response.json().get("data", [])[:5]

    if not cmc_news_data:
        st.info("No CoinMarketCap news articles found.")
    else:
        for article in cmc_news_data:
            title = article.get("title", "No Title")
            sentiment = TextBlob(title).sentiment.polarity
            emoji = "🔺" if sentiment > 0 else "🔻" if sentiment < 0 else "➖"
            st.write(f"{emoji} **{title}**")
except Exception as e:
    st.warning("Unable to load CoinMarketCap news data.")
    st.exception(e)

# ---- TOP 10 COINS METRICS (COINLORE) ----
st.markdown("---")
st.subheader("💎 Top 10 Cryptocurrencies")

cols = st.columns(2 if mobile_mode else 5)

for i, coin in enumerate(top10):
    with cols[i % (2 if mobile_mode else 5)]:
        pct = float(coin['percent_change_24h'])
        color = "🟢" if pct >= 0 else "🔴"
        st.metric(
            label=f"{coin['symbol']} ({coin['name']})",
            value=f"${coin['price_usd']}",
            delta=f"{color} {pct:.2f}%"
        )
