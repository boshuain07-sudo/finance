import streamlit as st
import pandas as pd
import yfinance as yf
import ccxt
import plotly.express as px
import sqlite3
from datetime import datetime, timedelta
import time
import numpy as np

# ==========================================
# 1. 系統配置與 CSS
# ==========================================
st.set_page_config(
    page_title="AlphaPortfolio | 專業資產管理",
    layout="wide",
    initial_sidebar_state="expanded",
    page_icon="💰"
)

# ==========================================
# 2. 資料庫層
# ==========================================
DB_FILE = "portfolio_v2.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    # 主資產表
    c.execute('''
        CREATE TABLE IF NOT EXISTS assets (
            id INTEGER PRIMARY KEY, 
            type TEXT, 
            symbol TEXT, 
            name TEXT, 
            quantity REAL, 
            cost_price REAL, 
            purchase_date TEXT
        )
    ''')
    # 資產歷史表 (MWRR 計算)
    c.execute('''
        CREATE TABLE IF NOT EXISTS asset_history_mwrr (
            id INTEGER PRIMARY KEY,
            asset_id INTEGER,
            date TEXT,
            cash_flow REAL,
            type TEXT,
            status TEXT DEFAULT '有效'
        )
    ''')
    conn.commit()
    conn.close()

def add_asset_to_db(atype, symbol, name, qty, cost, date):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(
        "INSERT INTO assets (type, symbol, name, quantity, cost_price, purchase_date) VALUES (?, ?, ?, ?, ?, ?)",
        (atype, symbol, name, qty, cost, date.strftime('%Y-%m-%d'))
    )
    asset_id = c.lastrowid
    # 對應資金流，新增投入
    c.execute(
    "INSERT INTO asset_history_mwrr (asset_id, date, cash_flow, type) VALUES (?, ?, ?, ?)",
    (asset_id, date.strftime('%Y-%m-%d'), -qty * cost, '投入')
)

    conn.commit()
    conn.close()

init_db()

# ==========================================
# 3. 報價服務層
# ==========================================
def get_usdtwd():
    try:
        price = yf.Ticker("USDTWD=X").fast_info.last_price
        return price if price else 32.5
    except:
        return 32.5

def get_stock_data(code):
    try:
        if code.isdigit() or (len(code) >= 5 and code[:5].isdigit()):
            ticker_str = f"{code}.TW"
        else:
            ticker_str = code
        stock = yf.Ticker(ticker_str)
        hist = stock.history(period="1d")
        if not hist.empty:
            price = hist["Close"].iloc[-1]
        else:
            price = stock.fast_info.last_price
        currency = stock.info.get("currency", "TWD")
        if currency == "USD":
            rate = get_usdtwd()
            price = price * rate
        name = stock.info.get("longName", code)
        return price, name
    except:
        return None, None

def get_crypto_data(symbol):
    try:
        exchange = ccxt.binance()
        ticker = exchange.fetch_ticker(f"{symbol.upper()}/USDT")
        return float(ticker['last'])
    except:
        return None

# ==========================================
# 4. Sidebar 側邊欄
# ==========================================
with st.sidebar:
    st.title("AlphaPortfolio")
    page_option = st.radio("選擇頁面", ["Dashboard", "歷史紀錄與 MWRR"])

    st.subheader("📅 Day 0 設定")
    conn = sqlite3.connect(DB_FILE)
    df_dates = pd.read_sql("SELECT purchase_date FROM assets ORDER BY purchase_date ASC", conn)
    conn.close()
    default_day0 = df_dates['purchase_date'].min() if not df_dates.empty else datetime.today().strftime('%Y-%m-%d')
    day0_str = st.date_input("選擇 Day 0", value=pd.to_datetime(default_day0))
    st.caption("Day 0 將作為計算年化報酬率與資金流的起點")

    st.subheader("➕ 新增資產")
    asset_type = st.selectbox("資產類型", ["股票", "加密貨幣", "現金", "存款", "負債"])
    market_price = 0.0
    asset_name = ""
    symbol = ""
    if asset_type == "股票":
        symbol = st.text_input("股票代號 (如 2330, 00981A, TSLA)").upper()
        if symbol:
            p, n = get_stock_data(symbol)
            if p:
                market_price, asset_name = p, n
                st.info(f"現價: {p:,.2f} TWD (已換算) | {n}")
            else:
                st.warning("搜尋中或代號無效...")
    elif asset_type == "加密貨幣":
        symbol = st.text_input("幣種 (如 BTC, ETH)").upper()
        if symbol:
            p = get_crypto_data(symbol)
            if p:
                rate = get_usdtwd()
                market_price = p * rate
                asset_name = symbol
                st.info(f"現價: {p:,.6f} USDT (≈{market_price:,.2f} TWD)")
            else:
                st.warning("無法取得價格")
    else:
        symbol = st.text_input("幣種", value="TWD").upper()
        asset_name = st.text_input("項目名稱", value=asset_type)
        market_price = 1.0

    quantity = st.number_input("數量", min_value=0.0, step=0.000001, format="%.6f")
    show_details = st.checkbox("修改成本或日期 (進階)")
    if show_details:
        cost_input = st.number_input("單位成本 (TWD)", value=float(market_price))
        date_input = st.date_input("購入日期", datetime.today())
    else:
        cost_input = float(market_price)
        date_input = datetime.today()

    if st.button("新增至投資組合", use_container_width=True):
        if quantity > 0 and asset_name:
            actual_qty = -quantity if asset_type == "負債" else quantity
            add_asset_to_db(asset_type, symbol, asset_name, actual_qty, cost_input, date_input)
            st.success("資產已成功加入！")
            time.sleep(0.5)
            st.rerun()

    st.markdown("---")
    st.subheader("⚙️ 顯示設定")
    is_red_up = st.toggle("顏色顯示", value=False)
    if is_red_up:
        toggle_label = "紅漲綠跌"
        up_color = "#FF4757"
        down_color = "#00C087"
    else:
        toggle_label = "紅跌綠漲"
        up_color = "#00C087"
        down_color = "#FF4757"
    st.caption(toggle_label)
    st.markdown(f"""
        <style>
        :root {{
            --up-color: {up_color};
            --down-color: {down_color};
        }}
        </style>
    """, unsafe_allow_html=True)

# ==========================================
# 5. Dashboard 主頁面
# ==========================================
if page_option == "Dashboard":
    col_title, col_btn = st.columns([4, 1])
    with col_title:
        st.title("資產管理儀表板")
    with col_btn:
        if st.button("🔄 更新即時報價"):
            st.cache_data.clear()
            st.rerun()

    conn = sqlite3.connect(DB_FILE)
    df = pd.read_sql("SELECT * FROM assets", conn)
    conn.close()

    if not df.empty:
        usdtwd = get_usdtwd()
        def fetch_now(row):
            if row['type'] == '股票':
                p, _ = get_stock_data(row['symbol'])
                return p if p is not None else row['cost_price']
            elif row['type'] == '加密貨幣':
                p = get_crypto_data(row['symbol'])
                return p * usdtwd if p is not None else row['cost_price']
            return 1.0

        with st.spinner('同步市場行情中...'):
            df['current_price'] = df.apply(fetch_now, axis=1)
            df['current_value'] = df['current_price'] * df['quantity']
            df['invested_amount'] = df['cost_price'] * df['quantity']
            df['pnl'] = df['current_value'] - df['invested_amount']
            df['roi'] = (df['pnl'] / df['invested_amount'].abs() * 100).fillna(0)

        total_val = df['current_value'].sum()
        total_pnl = df['pnl'].sum()

        # KPI 顯示
        k1, k2, k3 = st.columns(3)
        k1.markdown(f'<div class="kpi-card"><div class="kpi-title">總資產 (TWD)</div><div class="kpi-value">{total_val:,.0f}</div></div>', unsafe_allow_html=True)
        pnl_class = "text-green" if total_pnl > 0 else "text-red" if total_pnl < 0 else "color: #FFFFFF"
        k2.markdown(f'<div class="kpi-card"><div class="kpi-title">未實現損益</div><div class="kpi-value" style="{pnl_class}">{total_pnl:+,.0f}</div></div>', unsafe_allow_html=True)
        denominator = df[df['quantity'] > 0]['invested_amount'].sum()
        roi_val = (total_pnl / denominator * 100) if denominator != 0 else 0
        k3.markdown(f'<div class="kpi-card"><div class="kpi-title">總投報率</div><div class="kpi-value" style="{pnl_class}">{roi_val:+.2f}%</div></div>', unsafe_allow_html=True)

        # 圓餅圖
        c1, c2 = st.columns([1,1])
        with c1:
            pie_df = df[df['current_value'] > 0].groupby('name')['current_value'].sum().reset_index()
            if not pie_df.empty:
                total = pie_df['current_value'].sum()
                pie_df['pct'] = pie_df['current_value'] / total
                others = pie_df[pie_df['pct'] < 0.03]['current_value'].sum()
                pie_df = pie_df[pie_df['pct'] >= 0.03]
                if others > 0:
                    pie_df = pd.concat([pie_df, pd.DataFrame([{"name": "其他", "current_value": others}])], ignore_index=True)
                fig_pie = px.pie(pie_df, values='current_value', names='name', hole=0.5, title="資產配置比重")
                fig_pie.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font_color="white")
                st.plotly_chart(fig_pie, use_container_width=True)
        with c2:
            st.subheader("資產變化趨勢")
            history_df = pd.DataFrame({"日期": [datetime.now().strftime("%m/%d")], "總資產": [total_val]})
            st.line_chart(history_df.set_index("日期"))

        # 資產明細 (改用 columns 模擬表格以加入按鈕)
    st.subheader("資產明細")
    
    # 表頭
    h_cols = st.columns([1.5, 1.5, 1.2, 1.2, 1.2, 1.2, 1.5, 2.5])
    headers = ['類型', '名稱', '數量', '成本', '現價', '報酬率', '價值', '操作']
    for col, h in zip(h_cols, headers):
        col.markdown(f"**{h}**")
    st.divider()

    for idx, row in df.iterrows():
        c = st.columns([1.5, 1.5, 1.2, 1.2, 1.2, 1.2, 1.5, 2.5])
        
        # 顯示數值
        c[0].text(row['type'])
        c[1].text(row['name'])
        c[2].text(f"{row['quantity']:,.6f}")
        c[3].text(f"{row['cost_price']:,.6f}")
        c[4].text(f"{row['current_price']:,.6f}")
        
        # 報酬率顏色
        roi_color = up_color if row['roi'] > 0 else down_color if row['roi'] < 0 else "white"
        c[5].markdown(f"<span style='color:{roi_color}'>{row['roi']:+.2f}%</span>", unsafe_allow_html=True)
        c[6].text(f"{row['current_value']:,.0f}")

        # --- 操作按鈕區 ---
        btn_col1, btn_col2 = c[7].columns(2)
        
        # 1. 結清按鈕
        if btn_col1.button("結清", key=f"sell_{row['id']}"):
            st.session_state[f"show_sell_dialog_{row['id']}"] = True

        # 2. 刪除按鈕
        if btn_col2.button("刪除", key=f"del_{row['id']}"):
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM assets WHERE id = ?", (row['id'],))
            # 同時刪除該資產相關的 MWRR 紀錄（可選）
            cursor.execute("DELETE FROM asset_history_mwrr WHERE asset_id = ?", (row['id'],))
            conn.commit()
            conn.close()
            st.rerun()

        # --- 結清對話框 (彈出式) ---
        if st.session_state.get(f"show_sell_dialog_{row['id']}", False):
            with st.form(key=f"form_sell_{row['id']}"):
                st.write(f"### 結清項目：{row['name']}")
                col_s1, col_s2, col_s3 = st.columns(3)
                sell_date = col_s1.date_input("結清時間", datetime.today())
                sell_qty = col_s2.number_input("結清數量", min_value=0.000001, max_value=float(row['quantity']), value=float(row['quantity']), format="%.6f")
                sell_price = col_s3.number_input("結清價格 (TWD)", value=float(row['current_price']), format="%.6f")
                
                f_c1, f_c2 = st.columns(2)
                if f_c1.form_submit_button("確認結清"):
                    conn = sqlite3.connect(DB_FILE)
                    cur = conn.cursor()
                    
                    # 記錄現金流入 MWRR (賣出是正向現金流)
                    real_cash_in = sell_qty * sell_price
                    cur.execute(
                        "INSERT INTO asset_history_mwrr (asset_id, date, cash_flow, type, status) VALUES (?, ?, ?, ?, ?)",
                        (row['id'], sell_date.strftime('%Y-%m-%d'), real_cash_in, '取出', '部分結清' if sell_qty < row['quantity'] else '已結清')
                    )
                    
                    # 更新或刪除原始資產
                    if sell_qty >= row['quantity']:
                        cur.execute("DELETE FROM assets WHERE id = ?", (row['id'],))
                    else:
                        new_qty = row['quantity'] - sell_qty
                        cur.execute("UPDATE assets SET quantity = ? WHERE id = ?", (new_qty, row['id']))
                    
                    conn.commit()
                    conn.close()
                    st.session_state[f"show_sell_dialog_{row['id']}"] = False
                    st.rerun()
                
                if f_c2.form_submit_button("取消"):
                    st.session_state[f"show_sell_dialog_{row['id']}"] = False
                    st.rerun()

# ==========================================
# 6. 歷史紀錄與 MWRR 頁面
# ==========================================
elif page_option == "歷史紀錄與 MWRR":
    st.title("歷史資金流與 MWRR 分析")
    
    # 讀取歷史資料
    conn = sqlite3.connect(DB_FILE)
    hist_df = pd.read_sql("SELECT h.id, h.asset_id, a.name, h.date, h.cash_flow, h.type, h.status FROM asset_history_mwrr h LEFT JOIN assets a ON h.asset_id=a.id", conn)
    conn.close()

    if hist_df.empty:
        st.info("暫無歷史紀錄，請先新增資產或進行交易。")
    else:
        # 資料預處理
        hist_df['date'] = pd.to_datetime(hist_df['date'])
        hist_df = hist_df.sort_values('date')
        # 計算相對於 Day 0 的天數
        hist_df['days_raw'] = (hist_df['date'] - pd.to_datetime(day0_str)).dt.days
        # ★ 唯一新增規則：距今 90 天內的投資，一律視為 90 天
        today_days = (pd.to_datetime(datetime.today()) - pd.to_datetime(day0_str)).days
        hist_df['days'] = hist_df['days_raw'].apply(
    lambda d: min(d, today_days - 90) if d > today_days - 90 else d
)

        # --- 原始數據表格 ---
        with st.expander("查看原始資金流紀錄"):
            st.dataframe(hist_df, use_container_width=True)

        # ==========================================
        # MWRR 核心計算與可視化區塊
        # ==========================================
        st.markdown("---")
        st.header("💹 MWRR 計算診斷面板")

        # 1. 準備現金流數據
        cf_list = hist_df['cash_flow'].tolist()
        days_list = hist_df['days'].tolist()
        names_list = (hist_df['name'].fillna("已刪除資產") + " (" + hist_df['type'] + ")").tolist()

        # 2. 加入當前持倉的「期末市值」作為最後一筆流入
        conn = sqlite3.connect(DB_FILE)
        df_assets_now = pd.read_sql("SELECT * FROM assets", conn)
        conn.close()

        terminal_value = 0
        if not df_assets_now.empty:
            with st.spinner('計算即時市場價值...'):
                usdtwd = get_usdtwd()
                def fetch_now_mwrr(row):
                    if row['type'] == '股票':
                        p, _ = get_stock_data(row['symbol'])
                        return p if p is not None else row['cost_price']
                    elif row['type'] == '加密貨幣':
                        p = get_crypto_data(row['symbol'])
                        return p * usdtwd if p is not None else row['cost_price']
                    return 1.0

                df_assets_now['current_value'] = df_assets_now.apply(fetch_now_mwrr, axis=1) * df_assets_now['quantity']
                terminal_value = df_assets_now['current_value'].sum()

                # 加入列表
                today_days = (pd.to_datetime(datetime.today()) - pd.to_datetime(day0_str)).days
                cf_list.append(terminal_value)
                days_list.append(today_days)
                names_list.append("★ 當前持倉總市值 (假設今日結清)")

        # --- 顯示診斷資訊 ---
        col_diag, col_chart = st.columns([1, 1])

        with col_diag:
            st.subheader("1. 計算清單 (Checklist)")
            calc_df = pd.DataFrame({
                "項目名稱": names_list,
                "天數 (Day n)": days_list,
                "金額 (TWD)": cf_list
            })
            # 💡 這裡最關鍵：檢查買入是否為負數，市值是否為正數
            st.dataframe(calc_df.style.format({"金額 (TWD)": "{:,.6f}"}), use_container_width=True)
            
            # 自動檢測正負號異常
            has_neg = any(x < 0 for x in cf_list)
            has_pos = any(x > 0 for x in cf_list)
            
            if not has_neg:
                st.error("❌ 診斷結果：缺少『負數金額』。請確認買入資產時，金額是否正確記錄為負值。")
            if not has_pos:
                st.error("❌ 診斷結果：缺少『正數金額』。可能是目前資產價值為 0。")

        # 定義 NPV 與 IRR 邏輯
        def calculate_npv(r, cfs, days):
            return sum(cf / ((1 + r)**(d / 365)) for cf, d in zip(cfs, days))

        with col_chart:
            st.subheader("2. NPV 曲線圖 (尋找報酬率)")
            if has_neg and has_pos:
                # 繪製 NPV 曲線，觀察交點
                test_rates = np.linspace(-0.5, 3.0, 100) # 測試 -50% 到 300%
                npv_values = [calculate_npv(r, cf_list, days_list) for r in test_rates]
                
                fig = px.line(x=test_rates, y=npv_values, labels={'x':'年化利率 (r)', 'y':'NPV'}, title="當線條穿過紅線(0)時即為解答")
                fig.add_hline(y=0, line_dash="dash", line_color="red")
                st.plotly_chart(fig, use_container_width=True)

                # 執行二分法求解
                def solve_irr(cfs, days):
                    low, high = -0.99, 50.0 # 提高上限
                    for _ in range(100):
                        mid = (low + high) / 2
                        val = calculate_npv(mid, cfs, days)
                        if abs(val) < 0.01: return mid
                        if val > 0: low = mid
                        else: high = mid
                    return mid

                result_r = solve_irr(cf_list, days_list)
                
                # 顯示結果
                if not pd.isna(result_r):
                    color = "green" if result_r > 0 else "red"
                    st.markdown(f"### 最終計算 MWRR: <span style='color:{color}'>{result_r*100:.2f}%</span>", unsafe_allow_html=True)
                else:
                    st.warning("無法收斂，請檢查數據時間跨度是否過短。")
            else:
                st.warning("數據不足以繪製曲線圖。")