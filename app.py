%%writefile app.py
import streamlit as st
import feedparser
from deep_translator import GoogleTranslator
from textblob import TextBlob
import sqlite3
import pandas as pd
import time
import threading
from datetime import datetime, timedelta
import plotly.express as px
import re
import random
from collections import Counter
from transformers import pipeline  # 引入 AI 語意仲裁所需套件
from folium.plugins import MarkerCluster
# --- 🔥 引入 Folium 相關套件 ---
import folium
from folium.plugins import MarkerCluster
import streamlit.components.v1 as components

# --- 1. 全域配置與資料庫設定 ---
st.set_page_config(page_title="全球新聞智慧監控中心", layout="wide")

DB_NAME = 'news_monitor_v9.db'

NEWS_SOURCES = [
    {"name": "BBC World", "url": "https://feeds.bbci.co.uk/news/world/rss.xml"},
    {"name": "CNN International", "url": "http://rss.cnn.com/rss/edition.rss"},
    {"name": "Reuters News", "url": "https://qz.com/rss"},
    {"name": "AP Top News", "url": "https://bits.blogs.nytimes.com/feed/"},
    {"name": "UDN 聯合國際", "url": "https://udn.com/rssnews/news/1013/7225?ch=udnnews"}
]

# 關鍵字詞庫
DEFAULT_CATEGORIES = {
    "軍事政治": ["military", "war", "russia", "israel", "defense", "election", "ukraine", "conflict", "sanctions", "die", "arrest", "retrial", "airstrike", "biden", "combat", "tactic", "ally", "ceasefire", "invasion", "refugee", "戰爭", "選舉", "軍事", "政治", "衝突", "烏克蘭", "俄羅斯", "以色列"],
    "經濟": ["economy", "inflation", "gdp", "fed", "rate", "finance", "降息", "通膨", "股市", "經濟", "財經"],
    "科技": ["tech", "semiconductor", "apple", "google", "gpu", "tsmc", "台積電", "晶片", "科技", "人工智慧"],
    "體育": ["sport", "nba", "fifa", "olympics", "football", "tennis", "rookie", "mvp", "veteran", "blowout", "comeback", "upside", "momentum", "athletics", "blank", "edge", "運動", "籃球", "奧運", "體育"],
    "民生健康": ["health", "virus", "climate", "food", "medicine", "symptoms", "chronic", "acute", "diagnosis", "side effects", "immunity", "metabolism", "nutrient", "diet", "sedentary", "cancer", "flu", "hypertension", "diabetes", "病毒", "氣候", "醫療", "健康", "民生"]
}

CATEGORY_THEMES = {
    "經濟": {"emoji": "🔵", "label": "【經濟財經】", "color": "blue"},
    "科技": {"emoji": "🟢", "label": "【科技創新】", "color": "green"},
    "體育": {"emoji": "🟠", "label": "【體育運動】", "color": "orange"},
    "軍事政治": {"emoji": "🔴", "label": "【軍事政治】", "color": "red"},
    "民生健康": {"emoji": "🟣", "label": "【民生健康】", "color": "purple"},
    "一般國際": {"emoji": "⚪", "label": "【一般國際】", "color": "gray"}
}

COUNTRY_COORDS = {
    "美國": [37.0902, -95.7129], "中國": [35.8617, 104.1954], "英國": [55.3781, -3.4360],
    "台灣": [23.6978, 120.9605], "烏克蘭": [48.3794, 31.1656], "中東": [32.4279, 53.6880],
    "日本": [36.2048, 138.2529], "歐洲": [48.6909, 9.1406], "全球": [20.0, 0.0]
}

# --- 2. 強效雙閘門混血分類器 ---
CRISIS_STRONG_WORDS = [
    "襲擊", "無人機", "轟炸", "導彈", "開火", "進攻", "突襲", "交火", "戰機", "軍事演習",
    "劫持", "人質", "擊斃", "槍擊", "逮捕", "爆炸", "恐怖襲擊", "死亡", "死傷", "炸彈",
    "combat", "drone", "attack", "missile", "hostage", "shot dead", "hijack", "explode", "bomb"
]

@st.cache_resource
def load_classifier():
    try:
        return pipeline("zero-shot-classification", model="vicgalle/xlm-roberta-large-xnli-anli")
    except:
        return None

def hybrid_news_classifier(title_zh, title_en):
    match_text = (title_en + " " + title_zh).lower()
    clf = load_classifier()

    has_crisis = any(sw in match_text for sw in CRISIS_STRONG_WORDS)
    if has_crisis and clf is not None:
        return call_ai_arbitrator(title_zh, clf)

    scores = {k: 0 for k in DEFAULT_CATEGORIES.keys()}
    for cat, keywords in DEFAULT_CATEGORIES.items():
        for word in keywords:
            if word.lower() in match_text:
                scores[cat] += match_text.count(word.lower())

    max_keyword_cat = max(scores, key=scores.get)
    max_keyword_score = scores[max_keyword_cat]

    if max_keyword_score == 0:
        if clf is not None:
            return call_ai_arbitrator(title_zh, clf)
        return "一般國際"

    sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    if len(sorted_scores) > 1 and (sorted_scores[0][1] - sorted_scores[1][1]) <= 1:
        if clf is not None:
            return call_ai_arbitrator(title_zh, clf)

    return max_keyword_cat

def call_ai_arbitrator(title_zh, clf):
    try:
        candidate_labels = [
            "military and geopolitics conflict",
            "economy and finance market",
            "technology and science innovations",
            "sports news",
            "health and lifestyle medicine",
            "general international news"
        ]
        result = clf(title_zh, candidate_labels)
        top_label = result['labels'][0]

        mapping = {
            "military and geopolitics conflict": "軍事政治",
            "economy and finance market": "經濟",
            "technology and science innovations": "科技",
            "sports news": "體育",
            "health and lifestyle medicine": "民生健康",
            "general international news": "一般國際"
        }
        return mapping.get(top_label, "一般國際")
    except:
        return "一般國際"


def get_db_connection():
    return sqlite3.connect(DB_NAME, check_same_thread=False, timeout=20)

def init_db():
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS monitor_logs
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      title_zh TEXT, category TEXT, source TEXT, time TEXT,
                      link TEXT UNIQUE, sentiment REAL, country TEXT, lat REAL, lon REAL)''')
        c.execute('''CREATE TABLE IF NOT EXISTS user_tags
                     (username TEXT PRIMARY KEY, tags TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS push_settings
                     (id INTEGER PRIMARY KEY, line_token TEXT, keywords TEXT)''')
        conn.commit()

# --- 3. 數據抓取與清洗 ---
def fetch_all_news():
    translator = GoogleTranslator(source='auto', target='zh-TW')
    with get_db_connection() as conn:
        c = conn.cursor()
        for src in NEWS_SOURCES:
            try:
                feed = feedparser.parse(src["url"])
                for entry in feed.entries[:12]:
                    if "error 500" in entry.title.lower() or "server error" in entry.title.lower():
                        continue

                    c.execute("SELECT id FROM monitor_logs WHERE link=?", (entry.link,))
                    if not c.fetchone():
                        is_chinese = any('\u4e00' <= char <= '\u9fff' for char in entry.title)
                        sentiment_score = TextBlob(entry.title).sentiment.polarity

                        if is_chinese:
                            title_zh = entry.title
                            title_en = ""
                        else:
                            title_en = entry.title
                            title_zh = translator.translate(entry.title)
                            try: title_zh = translator.translate(entry.title)
                            except: title_zh = entry.title

                        cat = hybrid_news_classifier(title_zh, title_en)

                        t_lower, z_lower = title_en.lower(), title_zh.lower()
                        target_country = "全球"

                        if "美國" in z_lower or "川普" in z_lower or "白宮" in z_lower or re.search(r'\btrump\b|\bamerica\b|\bwashington\b|\bwhite\s+house\b|\busa\b', t_lower): target_country = "美國"
                        elif "台灣" in z_lower or "台積電" in z_lower or re.search(r'\btaiwan\b', t_lower): target_country = "台灣"
                        elif "烏克蘭" in z_lower or re.search(r'\bukraine\b', t_lower): target_country = "烏克蘭"
                        elif "中國" in z_lower or re.search(r'\bchina\b', t_lower): target_country = "中國"
                        elif "英國" in z_lower or re.search(r'\buk\b|\bbritain\b|\blondon\b', t_lower): target_country = "英國"
                        elif "日本" in z_lower or re.search(r'\bjapan\b', t_lower): target_country = "日本"
                        elif "中東" in z_lower or "以色列" in z_lower or "加薩" in z_lower or re.search(r'\bisrael\b|\bgaza\b', t_lower): target_country = "中東"
                        elif "歐洲" in z_lower or re.search(r'\beurope\b', t_lower): target_country = "歐洲"
                        elif re.search(r'\bus\b', t_lower): target_country = "美國"

                        base_lat, base_lon = COUNTRY_COORDS[target_country]
                        rand_lat = base_lat + random.uniform(-0.8, 0.8) if target_country != "全球" else base_lat + random.uniform(-5, 5)
                        rand_lon = base_lon + random.uniform(-0.8, 0.8) if target_country != "全球" else base_lon + random.uniform(-5, 5)

                        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        c.execute('''INSERT INTO monitor_logs
                                     (title_zh, category, source, time, link, sentiment, country, lat, lon)
                                     VALUES (?,?,?,?,?,?,?,?,?)''',
                                  (title_zh, cat, src["name"], now, entry.link, sentiment_score, target_country, rand_lat, rand_lon))
            except:
                pass
        conn.commit()

def monitor_loop():
    time.sleep(5)
    while True:
        try: fetch_all_news()
        except: pass
        time.sleep(300)

init_db()
if 'monitor_started' not in st.session_state:
    with st.spinner("智慧監控中心初始化，正在跨國同步最新全球焦點..."):
        fetch_all_news()
    threading.Thread(target=monitor_loop, daemon=True).start()
    st.session_state['monitor_started'] = True

# --- 4. 狀態快取與控制 ---
if 'logged_in' not in st.session_state: st.session_state['logged_in'] = False
if 'username' not in st.session_state: st.session_state['username'] = ""
if 'is_guest' not in st.session_state: st.session_state['is_guest'] = False
if 'current_view' not in st.session_state: st.session_state['current_view'] = "🏠 首頁總覽"

def load_all_data():
    with get_db_connection() as conn:
        df = pd.read_sql_query("SELECT * FROM monitor_logs ORDER BY time DESC", conn)
        if not df.empty:
            df['time_dt'] = pd.to_datetime(df['time'])
        return df

df_all = load_all_data()

def get_recent_hour_data(df):
    if df.empty: return df
    one_hour_ago = datetime.now() - timedelta(hours=1)
    return df[df['time_dt'] >= one_hour_ago]

df_recent = get_recent_hour_data(df_all)

def get_user_tags(username):
    if st.session_state['is_guest'] and 'guest_tags' in st.session_state:
        return st.session_state['guest_tags']
    with get_db_connection() as conn:
        res = conn.execute("SELECT tags FROM user_tags WHERE username=?", (username,)).fetchone()
        return res[0].split(",") if res and res[0] else list(DEFAULT_CATEGORIES.keys()) + ["一般國際"]

def save_user_tags(username, tags):
    with get_db_connection() as conn:
        conn.execute("INSERT OR REPLACE INTO user_tags (username, tags) VALUES (?, ?)", (username, ",".join(tags)))
        conn.commit()

# --- 5. 登入管制牆 ---
if not st.session_state['logged_in'] and not st.session_state['is_guest']:
    st.title("全球新聞智能監控系統")
    st.subheader("請選擇進入模式以開啟個性化儀表板")

    col1, col2 = st.columns(2)
    with col1:
        with st.container(border=True):
            st.markdown("### 🔑 會員/自訂用戶登入")
            username_input = st.text_input("使用者名稱", placeholder="請輸入使用者名稱", key="login_user")
            password_input = st.text_input("密碼", type="password", placeholder="******", key="login_pwd")
            if st.button("進入會員系統", use_container_width=True, key="btn_member_login"):
                if username_input.strip():
                    st.session_state['logged_in'] = True
                    st.session_state['is_guest'] = False
                    st.session_state['username'] = username_input.strip()
                    st.rerun()
    with col2:
        with st.container(border=True):
            st.markdown("### 🌐 訪客快捷通道")
            st.write("免帳號密碼快捷登入，即刻查看全球一小時內最新事件地圖。")
            if st.button("🚀 以訪客身份免登入進入", use_container_width=True, type="primary", key="btn_guest_login"):
                st.session_state['is_guest'] = True
                st.session_state['logged_in'] = False
                st.session_state['username'] = "訪客模式 Guest"
                st.session_state['guest_tags'] = list(DEFAULT_CATEGORIES.keys()) + ["一般國際"]
                st.rerun()
    st.stop()

# --- 6. 側邊欄分類複選勾選面板 ---
st.sidebar.title(f"👤 {st.session_state['username']}")

if st.sidebar.button("🔄 手動同步最新新聞", key="side_sync_btn"):
    with st.spinner("正在重新爬取各國新聞..."):
        fetch_all_news()
    st.rerun()

st.sidebar.write("---")
all_available_tags = list(DEFAULT_CATEGORIES.keys()) + ["一般國際"]
saved_tags = get_user_tags(st.session_state['username'])

selected_tags = []
for tag in all_available_tags:
    is_checked = tag in saved_tags
    if st.sidebar.checkbox(f"🔖 {tag}", value=is_checked, key=f"sidebar_fixed_cb_{tag}"):
        selected_tags.append(tag)

if st.session_state['is_guest']:
    st.session_state['guest_tags'] = selected_tags
else:
    if st.sidebar.button("💾 儲存我的勾選設定", key="side_save_btn"):
        save_user_tags(st.session_state['username'], selected_tags)
        st.sidebar.success("訂閱設定已同步！")
        st.rerun()

if st.sidebar.button("🚪 登出/切換模式", key="side_logout_btn"):
    st.session_state['logged_in'] = False
    st.session_state['is_guest'] = False
    st.rerun()

# --- 7. 🔥 頂部大選單導覽列（雙行排版設計，完美區隔系統與分類分頁） ---
st.write("### 🧭 系統主功能面板")

# 第一行：擺放系統內建基礎功能
base_menu = ["🏠 首頁總覽", "⏳ 歷史總時間軸", "📊 數據統計分析", "🔍 關鍵字搜尋"]
if not st.session_state['is_guest']:
    base_menu.append("📢 LINE通知設定")

cols_row1 = st.columns(len(base_menu))
for idx, item_name in enumerate(base_menu):
    if cols_row1[idx].button(item_name, use_container_width=True, key=f"nav_row1_{idx}"):
        st.session_state['current_view'] = item_name

# 第二行：擺放所有從「軍事政治」開始的動態訂閱新聞分頁，做出漂亮分隔
st.write("### 🔖 訂閱新聞分類頻道")
category_menu = [f"🔖 {t}" for t in selected_tags]

if category_menu:
    cols_row2 = st.columns(len(category_menu))
    for idx, item_name in enumerate(category_menu):
        if cols_row2[idx].button(item_name, use_container_width=True, key=f"nav_row2_{idx}"):
            st.session_state['current_view'] = item_name

st.write("---")

# --- 8. 新聞卡片元件（精準修復：點擊移動後立刻重載更新，絕不卡死） ---
def render_native_news_cards(df_target):
    if df_target.empty:
        st.info("💡 該時段或分類目前暫無新聞條目。")
        return

    core_categories = ["軍事政治", "經濟", "科技", "體育", "民生健康", "一般國際"]
    nav_options = ["請選擇要移動至的分頁..."] + [f"🔖 {c}" for c in core_categories]

    for idx, row in df_target.iterrows():
        cat = row['category']
        news_id = row['id']
        theme = CATEGORY_THEMES.get(cat, CATEGORY_THEMES["一般國際"])
        sentiment_text = "正面" if row['sentiment'] > 0.05 else ("負面" if row['sentiment'] < -0.05 else "中性")

        with st.container(border=True):
            col_meta, col_title, col_btn = st.columns([2.5, 7.0, 2.5])
            with col_meta:
                st.markdown(f"**{theme['emoji']} {theme['label']}**")
                st.caption(f"📡 來源: `{row['source']}`")
            with col_title:
                st.markdown(f"#### {row['title_zh']}")
                st.markdown(f"⏱️ `發布時間: {row['time']}` &nbsp;|&nbsp; 📍 區域: **{row['country']}** &nbsp;|&nbsp; 📊 輿情: `{sentiment_text}`")
            with col_btn:
                # 前往原文按鈕
                st.link_button("🔗 前往原文", row['link'], use_container_width=True, key=f"lnk_{idx}_{news_id}")
                st.write("")

                # 移動至選單
                selected_nav = st.selectbox(
                    "移動至 👇",
                    options=nav_options,
                    index=0,
                    key=f"move_sel_{idx}_{news_id}",
                    label_visibility="collapsed"
                )

                # 當點選移動分頁時，即時寫入、強制清空快取，杜絕卡死
                if selected_nav != "請選擇要移動至的分頁...":
                    new_category = selected_nav.replace("🔖 ", "")

                    # 1. 修改資料庫欄位
                    with get_db_connection() as conn:
                        conn.execute("UPDATE monitor_logs SET category = ? WHERE id = ?", (new_category, news_id))
                        conn.commit()

                    # 2. 自動跳轉檢視到目標分頁
                    st.session_state['current_view'] = selected_nav

                    # 3. 強制刷新網頁
                    st.rerun()

# --- 9. 各分頁路由渲染邏輯 ---

# A. 首頁總覽
if st.session_state['current_view'] == "🏠 首頁總覽":
    st.title("🗺️ Leaflet 高階全域互動式焦點地圖")

    if not df_recent.empty:
        df_map_filtered = df_recent[
            (df_recent['category'] != "影音新聞") &
            (df_recent['lat'].notna()) &
            (df_recent['lon'].notna())
        ]
    else:
        df_map_filtered = pd.DataFrame()

    if df_map_filtered.empty:
        st.warning("⏱️ 最近 1 小時內國際新聞台暫無具備精確定位的新聞事件。")
    else:
        m = folium.Map(location=[25.0, 10.0], zoom_start=2, tiles="OpenStreetMap")
        marker_cluster = MarkerCluster().add_to(m)

        for idx, row in df_map_filtered.iterrows():
            theme = CATEGORY_THEMES.get(row['category'], CATEGORY_THEMES["一般國際"])

            popup_html = f"""
            <div style="font-family: Arial, sans-serif; width: 260px; font-size: 13px; line-height: 1.4;">
                <b style="color: #ff4b4b; font-size: 14px;">{theme['emoji']} {row['category']}</b><br>
                <p style="margin: 5px 0; font-weight: bold; color: #333;">{row['title_zh']}</p>
                <hr style="margin: 5px 0; border: 0; border-top: 1px solid #ccc;">
                <small>📡 來源: {row['source']}</small><br>
                <small>⏱️ 時間: {row['time']}</small><br><br>
                <a href="{row['link']}" target="_blank" style="display: inline-block; background-color: #ff4b4b; color: white; padding: 5px 10px; text-decoration: none; border-radius: 4px; font-weight: bold; text-align: center; width: 90%;">前往新聞原文 🔗</a>
            </div>
            """

            folium.Marker(
                location=[row['lat'], row['lon']],
                popup=folium.Popup(popup_html, max_width=300),
                tooltip=row['title_zh'][:20] + "...",
                icon=folium.Icon(color=theme['color'], icon="info-sign")
            ).add_to(marker_cluster)

        map_html = m._repr_html_()
        components.html(map_html, height=650, scrolling=True)

    st.write("---")
    st.write("### 🔔 焦點對應：最近 1 小時內發布的新聞條目")
    render_native_news_cards(df_recent[df_recent['category'] != "影音新聞"])

elif st.session_state['current_view'] == "🎥 影片專區":
    st.title("🎥 全球精選影音與異常反饋專區（不登錄地圖）")
    if not df_all.empty:
        df_videos = df_all[df_all['category'] == "影音新聞"]
        render_native_news_cards(df_videos, is_video_view=True)
    else:
        st.info("💡 目前資料庫中暫無影音新聞或故障回傳。")
# B. ⏳ 歷史總時間軸
elif st.session_state['current_view'] == "⏳ 歷史總時間軸":
    st.title("⏳ 全球歷史即時總時間軸")
    render_native_news_cards(df_all)

# C. 📊 數據統計分析
elif st.session_state['current_view'] == "📊 數據統計分析":
    st.title("📊 全球新聞數據統計分析")
    if df_all.empty:
        st.warning("資料庫內暫無數據可供分析。")
    else:
        col_f1, col_f2 = st.columns([1, 1])
        with col_f1:
            st.write("### 📈 新聞動態抓取走勢線")
            df_trend = df_all.copy()
            df_trend['time_group'] = df_trend['time_dt'].dt.floor('10min').dt.strftime("%Y-%m-%d %H:%M")
            time_trend = df_trend.groupby(['time_group', 'category']).size().reset_index(name='新聞數量')
            time_trend = time_trend.sort_values(by='time_group')
            fig_line = px.line(time_trend, x="time_group", y="新聞數量", color="category", title="趨勢走勢線", markers=True)
            st.plotly_chart(fig_line, use_container_width=True, key="stat_line_chart")

        with col_f2:
            st.write("### ⏱️ 24小時新聞發布頻率線")
            fig_hist = px.histogram(df_all, x="time_dt", color="category", nbins=24, title="24小時發布頻率直方圖")
            st.plotly_chart(fig_hist, use_container_width=True, key="stat_hist_chart")

# D. 🔍 關鍵字搜尋頁
elif st.session_state['current_view'] == "🔍 關鍵字搜尋":
    st.title("🔍 全域新聞關鍵字檢索")
    search_query = st.text_input("輸入要查詢的關鍵字：", placeholder="例如：台積電、晶片、戰爭", key="search_box_input")
    if search_query and not df_all.empty:
        results = df_all[df_all['title_zh'].str.contains(search_query, na=False, case=False)]
        st.write(f"共找到 {len(results)} 筆符合條件的條目：")
        render_native_news_cards(results)
    elif search_query:
        st.info("目前尚無符合該關鍵字的新聞。")

# E. 📢 LINE通知設定
elif st.session_state['current_view'] == "📢 LINE通知設定":
    st.title("📢 LINE Notify 智慧預警推送")
    with get_db_connection() as conn:
        curr_config = conn.execute("SELECT line_token, keywords FROM push_settings WHERE id=1").fetchone()
    display_token = curr_config[0] if curr_config else ""
    display_keywords = curr_config[1] if curr_config else ""

    with st.form("push_form_cfg"):
        token_input = st.text_input("LINE Notify Token", value=display_token, type="password", key="line_tok_input")
        kw_input = st.text_area("追蹤關鍵字 (英文逗號隔開)", value=display_keywords, key=f"line_kw_input")
        if st.form_submit_button("儲存並開啟推播"):
            with get_db_connection() as conn:
                conn.execute("INSERT OR REPLACE INTO push_settings (id, line_token, keywords) VALUES (1, ?, ?)",
                             (token_input, kw_input.replace("，", ",")))
                conn.commit()
            st.success("通知設定更新成功！")

# F. 動態分類專屬獨立時間軸
elif st.session_state['current_view'].startswith("🔖 "):
    target_tag = st.session_state['current_view'].replace("🔖 ", "")
    st.title(f"🔖 分類專屬獨立時間軸：{target_tag}")

    tag_df = df_all[df_all['category'] == target_tag]
    render_native_news_cards(tag_df)
