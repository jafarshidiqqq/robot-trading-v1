import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf

# ==========================================
# KONFIGURASI HALAMAN WEB
# ==========================================
st.set_page_config(page_title="Backtest Pro", layout="wide")
st.title("📊 Dashboard Backtest: SMA 50 + RSI + ADX")
st.markdown("Strategi: **Buy** (Trend + Momentum + Strong Trend) | **Sell** (Close < SMA 50)")

# ==========================================
# SIDEBAR (INPUT USER)
# ==========================================
st.sidebar.header("⚙️ Pengaturan")
ticker = st.sidebar.text_input("Simbol Ticker (Yahoo Finance)", value="BTC-USD")
modal_awal = st.sidebar.number_input("Modal Awal ($)", value=10000, step=100)
periode_hari = st.sidebar.selectbox("Durasi Data", ["365d", "730d", "1095d", "1825d"], index=2)

tombol_mulai = st.sidebar.button("Jalankan Backtest")

# ==========================================
# FUNGSI BACKTEST
# ==========================================
@st.cache_data # Agar tidak download ulang terus menerus
def ambil_data(symbol, period):
    data = yf.download(symbol, period=period, interval="1d")
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)
    return data

if tombol_mulai:
    with st.spinner('Sedang memproses data...'):
        try:
            df = ambil_data(ticker, periode_hari)
            
            # --- 1. HITUNG INDIKATOR ---
            df['SMA_50'] = df['Close'].rolling(window=50).mean()
            
            # RSI
            delta = df['Close'].diff()
            gain = (delta.where(delta > 0, 0)).ewm(com=13, adjust=False).mean()
            loss = (-delta.where(delta < 0, 0)).ewm(com=13, adjust=False).mean()
            df['RSI'] = 100 - (100 / (1 + (gain/loss)))
            
            # ADX
            df['TR'] = df[['High', 'Low', 'Close']].apply(
                lambda x: max(x['High'] - x['Low'], abs(x['High'] - x['Close']), abs(x['Low'] - x['Close'])), axis=1)
            window_adx = 14
            df['TR14'] = df['TR'].ewm(span=window_adx, adjust=False).mean()
            df['+DM'] = np.where((df['High']-df['High'].shift(1) > df['Low'].shift(1)-df['Low']) & (df['High']-df['High'].shift(1) > 0), df['High']-df['High'].shift(1), 0)
            df['-DM'] = np.where((df['Low'].shift(1)-df['Low'] > df['High']-df['High'].shift(1)) & (df['Low'].shift(1)-df['Low'] > 0), df['Low'].shift(1)-df['Low'], 0)
            df['+DM14'] = df['+DM'].ewm(span=window_adx, adjust=False).mean()
            df['-DM14'] = df['-DM'].ewm(span=window_adx, adjust=False).mean()
            df['DX'] = 100 * abs((100*df['+DM14']/df['TR14']) - (100*df['-DM14']/df['TR14'])) / ((100*df['+DM14']/df['TR14']) + (100*df['-DM14']/df['TR14']))
            df['ADX'] = df['DX'].ewm(span=window_adx, adjust=False).mean()

            # --- 2. LOGIKA BACKTEST ---
            uang_tunai = modal_awal
            jumlah_koin = 0
            posisi = "CASH"
            fee = 0.001
            
            riwayat_profit = []
            riwayat_durasi = []
            tanggal_beli = None
            modal_beli = 0
            
            for i in range(50, len(df)):
                harga = float(df['Close'].iloc[i])
                sma = float(df['SMA_50'].iloc[i])
                rsi = float(df['RSI'].iloc[i])
                adx = float(df['ADX'].iloc[i])
                tgl = df.index[i]
                
                # ENTRY RULE
                syarat_buy = (harga > sma) and (rsi > 50) and (rsi < 70) and (adx > 25)
                
                if posisi == "CASH" and syarat_buy:
                    modal_beli = uang_tunai * (1 - fee)
                    jumlah_koin = modal_beli / harga
                    uang_tunai = 0
                    posisi = "KOIN"
                    tanggal_beli = tgl
                
                # EXIT RULE (Simple SMA Breakdown)
                elif posisi == "KOIN" and harga < sma:
                    uang_dapat = jumlah_koin * harga * (1 - fee)
                    profit = uang_dapat - modal_beli
                    riwayat_profit.append(profit)
                    riwayat_durasi.append((tgl - tanggal_beli).days)
                    
                    uang_tunai = uang_dapat
                    jumlah_koin = 0
                    posisi = "CASH"

            # Final Settlement
            if posisi == "KOIN":
                uang_tunai = jumlah_koin * df['Close'].iloc[-1] * (1 - fee)
                riwayat_profit.append(uang_tunai - modal_beli)
                riwayat_durasi.append((df.index[-1] - tanggal_beli).days)

            # --- 3. TAMPILKAN HASIL ---
            saldo_akhir = uang_tunai
            profit_total = saldo_akhir - modal_awal
            profit_persen = (profit_total / modal_awal) * 100
            total_trades = len(riwayat_profit)
            
            win_rate = 0
            rr_ratio = 0
            if total_trades > 0:
                wins = [p for p in riwayat_profit if p > 0]
                losses = [p for p in riwayat_profit if p <= 0]
                win_rate = (len(wins) / total_trades) * 100
                avg_win = np.mean(wins) if wins else 0
                avg_loss = np.mean(losses) if losses else 0
                rr_ratio = avg_win / abs(avg_loss) if avg_loss != 0 else 0

            # METRICS ROW
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Saldo Akhir", f"${saldo_akhir:,.2f}")
            col2.metric("Total Profit", f"{profit_persen:.2f}%", f"${profit_total:,.2f}")
            col3.metric("Win Rate", f"{win_rate:.1f}%")
            col4.metric("Risk Reward", f"1 : {rr_ratio:.2f}")

            # STATISTICS ROW
            st.markdown("---")
            colA, colB = st.columns(2)
            with colA:
                st.subheader("Statistik Waktu")
                avg_hold = np.mean(riwayat_durasi) if riwayat_durasi else 0
                st.write(f"⏳ **Rata-rata Hold:** {avg_hold:.1f} Hari")
                st.write(f"🔄 **Jumlah Transaksi:** {total_trades} kali")
            
            with colB:
                st.subheader("Kesimpulan")
                if saldo_akhir > modal_awal:
                    st.success(f"Strategi Profit! Anda menghasilkan ${profit_total:,.2f}")
                else:
                    st.error(f"Strategi Loss. Anda rugi ${abs(profit_total):,.2f}")
            
            # CHART SEDERHANA (Opsional)
            st.markdown("---")
            st.subheader("Grafik Harga & SMA 50")
            st.line_chart(df[['Close', 'SMA_50']])

        except Exception as e:
            st.error(f"Terjadi Error: {e}")
            st.info("Coba cek apakah simbol ticker benar (contoh: BTC-USD, AAPL, BBCA.JK)")