import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection
import yfinance as yf
import ccxt
import plotly.express as px
from datetime import datetime, timedelta
import time
import numpy as np

# ==========================================
# 1. 系統配置與核心樣式
# ==========================================
st.set_page_config(page_title="AlphaPortfolio Pro | 雲端多帳戶版", layout="wide", page_icon="💰")

def apply_style(up, down):
    st.markdown(f"""
        <style>
        :root {{ --up-color: {up}; --down-color: {down}; }}
        .kpi-card {{ background-color: #1E1E1E; padding: 20px; border-radius: 10px; border-left: 5px solid #4A90E2; text-align: center; margin-bottom: 10px; }}
        .kpi-title {{ color: #888888; font-size: 14px; }}
        .kpi-value {{ font-size: 26px; font-weight: bold; margin-top: 5px; }}
        .text-up {{ color: {up}; }}
        .text-down {{ color: {down}; }}
        </style>
    """, unsafe_allow_html=True)

# ==========================================
# 2. Google Sheets 資料庫層 (含自動初始化)
# ==========================================
conn = st.connection("gsheets", type=GSheetsConnection)

def get_data():
    try:
        # 讀取主資產表與 MWRR 歷史表
        assets = conn.read(worksheet="Sheet1", ttl="0")
        history = conn.read(worksheet="mwrr_history", ttl="0")
        return assets, history
    except Exception:
        # --- 自動初始化試算表結構 ---
        df_assets = pd.DataFrame(columns=['id', 'account', 'type', 'symbol', 'name', 'quantity', 'cost_price', 'purchase_date'])
        df_history = pd.DataFrame(columns=['account', 'asset_id', 'date', 'cash_flow', 'type', 'status'])
        return df_assets, df_history

def sync_to_cloud(assets_df, history_df):
    conn.update(worksheet="Sheet1", data=assets_df)
    conn.update(worksheet="mwrr_history", data=history_df)
    st.cache_data.clear()

# ==========================================
# 3. 報價與計算引擎
# ==========================================
@st.cache_data(ttl=600)
def get_usdtwd():
    try: return yf.Ticker("USDTWD=X").fast_info.last_price
    except: return 32.5

@st.cache_data(ttl=300)
def fetch_market_price(row, usdtwd):
    try:
        if row['type'] == '股票':
            symbol = f"{row['symbol']}.TW" if row['symbol'].isdigit() else row['symbol']
            tk = yf.Ticker(symbol)
            p = tk.fast_info.last_price
            if tk.info.get("currency") == "USD": p *= usdtwd
            return p
        elif row['type'] == '加密貨幣':
            exchange = ccxt.binance()
            p = float(exchange.fetch_ticker(f"{row['symbol']}/USDT")['last'])
            return p * usdtwd
        return 1.0
    except: return row['cost_price']

# ==========================================
# 4. Sidebar 控制面板
# ==========================================
assets_df, history_df = get_data()

with st.sidebar:
    st.title("🏦 AlphaPortfolio")
    
    # 帳戶選擇器
    all_accounts = ["全部帳戶"] + sorted(assets_df['account'].unique().tolist()) if not assets_df.empty else ["全部帳戶"]
    current_acc = st.selectbox("切換顯示帳戶", all_accounts)
    
    page = st.radio("導覽", ["儀表板", "歷史與 MWRR 分析"])
    
    st.divider()
    st.subheader("➕ 新增資產")
    in_acc = st.text_input("存入帳戶", value="預設帳戶")
    in_type = st.selectbox("類型", ["股票", "加密貨幣", "現金", "負債"])
    in_sym = st.text_input("代號 (2330 / BTC)").upper()
    in_qty = st.number_input("數量", min_value=0.0, format="%.6f")
    
    # 自動抓取現價作為預設成本
    temp_usdtwd = get_usdtwd()
    auto_p = fetch_market_price({'type': in_type, 'symbol': in_sym, 'cost_price': 0}, temp_usdtwd) if in_sym else 0.0
    in_cost = st.number_input("單位成本 (TWD)", value=float(auto_p))
    in_date = st.date_input("日期", datetime.today())

    if st.button("確認新增", use_container_width=True):
        new_id = int(time.time())
        # 更新資產表
        new_asset = pd.DataFrame([{"id": new_id, "account": in_acc, "type": in_type, "symbol": in_sym, "name": in_sym, "quantity": in_qty, "cost_price": in_cost, "purchase_date": in_date.strftime('%Y-%m-%d')}])
        # 更新 MWRR 表
        new_hist = pd.DataFrame([{"account": in_acc, "asset_id": new_id, "date": in_date.strftime('%Y-%m-%d'), "cash_flow": -in_qty * in_cost, "type": "投入", "status": "有效"}])
        sync_to_cloud(pd.concat([assets_df, new_asset]), pd.concat([history_df, new_hist]))
        st.success("同步完成！")
        st.rerun()

    st.divider()
    is_red_up = st.toggle("紅漲綠跌", value=False)
    up_c, down_c = ("#FF4757", "#00C087") if is_red_up else ("#00C087", "#FF4757")
    apply_style(up_c, down_c)

# ==========================================
# 5. Dashboard 頁面
# ==========================================
if page == "儀表板":
    st.title(f"📊 {current_acc} 資產概覽")
    
    # 篩選資料
    display_df = assets_df.copy() if current_acc == "全部帳戶" else assets_df[assets_df['account'] == current_acc]
    
    if not display_df.empty:
        usdtwd = get_usdtwd()
        with st.spinner('更新即時報價...'):
            display_df['current_price'] = display_df.apply(lambda r: fetch_market_price(r, usdtwd), axis=1)
            display_df['current_value'] = display_df['current_price'] * display_df['quantity']
            display_df['invested'] = display_df['cost_price'] * display_df['quantity']
            display_df['pnl'] = display_df['current_value'] - display_df['invested']
            display_df['roi'] = (display_df['pnl'] / display_df['invested'].abs() * 100).fillna(0)

        # KPI 卡片
        t1, t2, t3 = st.columns(3)
        total_v = display_df['current_value'].sum()
        total_p = display_df['pnl'].sum()
        total_r = (total_p / display_df['invested'].sum() * 100) if display_df['invested'].sum() != 0 else 0
        
        t1.markdown(f'<div class="kpi-card"><div class="kpi-title">總市值</div><div class="kpi-value">{total_v:,.0f}</div></div>', unsafe_allow_html=True)
        p_style = "text-up" if total_p >= 0 else "text-down"
        t2.markdown(f'<div class="kpi-card"><div class="kpi-title">未實現損益</div><div class="kpi-value {p_style}">{total_p:+,.0f}</div></div>', unsafe_allow_html=True)
        t3.markdown(f'<div class="kpi-card"><div class="kpi-title">投資報酬率</div><div class="kpi-value {p_style}">{total_r:+.2f}%</div></div>', unsafe_allow_html=True)

        # 圖表
        c1, c2 = st.columns([1, 1])
        with c1:
            fig = px.pie(display_df, values='current_value', names='account' if current_acc == "全部帳戶" else 'symbol', hole=0.4, title="資產分布")
            st.plotly_chart(fig, use_container_width=True)
        with c2:
            st.subheader("資產清單")
            st.dataframe(display_df[['account', 'symbol', 'quantity', 'current_value', 'roi']], use_container_width=True)

        # 操作區
        st.divider()
        st.subheader("🛠️ 帳戶操作")
        for idx, row in display_df.iterrows():
            col = st.columns([2, 1, 1, 1])
            col[0].write(f"**{row['account']} - {row['symbol']}** ({row['quantity']})")
            
            # 結清按鈕 (簡化邏輯：全額結清)
            if col[1].button("全額結清", key=f"sell_{row['id']}"):
                # 記錄現金流入 (正向現金流)
                new_h = pd.DataFrame([{"account": row['account'], "asset_id": row['id'], "date": datetime.today().strftime('%Y-%m-%d'), "cash_flow": row['current_value'], "type": "結清", "status": "已結清"}])
                sync_to_cloud(assets_df.drop(idx), pd.concat([history_df, new_h]))
                st.rerun()
                
            if col[2].button("刪除", key=f"del_{row['id']}"):
                sync_to_cloud(assets_df.drop(idx), history_df[history_df['asset_id'] != row['id']])
                st.rerun()
    else:
        st.info("尚無資料，請於側邊欄新增。")

# ==========================================
# 6. MWRR 分析頁面 (核心邏輯)
# ==========================================
else:
    st.title("📈 資金流分析 (MWRR)")
    h_df = history_df.copy() if current_acc == "全部帳戶" else history_df[history_df['account'] == current_acc]
    
    if not h_df.empty:
        # 計算 Day 0 (Day 0 決定年化報酬起點)
        day0 = pd.to_datetime(h_df['date']).min()
        st.write(f"分析起始日 (Day 0): {day0.date()}")
        
        # 準備 MWRR 數列：歷史現金流 + 目前帳戶餘額 (末值)
        cfs = h_df['cash_flow'].tolist()
        dates = pd.to_datetime(h_df['date']).tolist()
        
        # 加入「假設今日結清」的末值
        current_mkt = display_df['current_value'].sum() if 'display_df' in locals() else 0
        if current_mkt > 0:
            cfs.append(current_mkt)
            dates.append(pd.to_datetime(datetime.today()))
            
        st.dataframe(pd.DataFrame({"日期": dates, "現金流": cfs}), use_container_width=True)

        # 二分法求解 IRR
        def irr_solve(cfs, dates):
            def npv(r):
                return sum(cf / (1 + r)**((d - dates[0]).days / 365) for cf, d in zip(cfs, dates))
            low, high = -0.99, 10.0
            for _ in range(50):
                mid = (low + high) / 2
                if npv(mid) > 0: low = mid
                else: high = mid
            return mid

        res_mwrr = irr_solve(cfs, dates)
        st.metric("時間加權報酬率 (年化 MWRR)", f"{res_mwrr*100:.2f}%")
