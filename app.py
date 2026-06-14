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
from geopy.geocoders import Nominatim
from functools import lru_cache
import requests

# --- 1. 登入驗證模組 (寫死帳密) ---
def check_password():
    """傳回 True 代表使用者通過驗證，否則為 False"""
    def password_entered():
        """檢查輸入的帳號密碼是否正確"""
        if (
            st.session_state["username_input"] == "tester1"
            and st.session_state["password_input"] == "donoterror"
        ):
            st.session_state["password_correct"] = True
            st.session_state["username"] = st.session_state["username_input"]
            del st.session_state["password_input"]  # 清除暫存密碼安全
            del st.session_state["username_input"]
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        # 顯示登入表單
        st.title("🔐 全球新聞監控中心 - 系統登入")
        st.text_input("帳號 (Username)", key="username_input")
        st.text_input("密碼 (Password)", type="password", key="password_input", on_change=password_entered)
        if st.button("登入"):
            password_entered()
            st.rerun()
        if "password_correct" in st.session_state and not st.session_state["password_correct"]:
            st.error("❌ 帳號或密碼錯誤，請重新輸入！")
        return False
    elif not st.session_state["password_correct"]:
        # 密碼錯誤重新顯示表單
        st.title("🔐 全球新聞監控中心 - 系統登入")
        st.text_input("帳號 (Username)", key="username_input")
        st.text_input("密碼 (Password)", type="password", key="password_input", on_change=password_entered)
        if st.button("登入"):
            password_entered()
            st.rerun()
        st.error("❌ 帳號或密碼錯誤，請重新輸入！")
        return False
    else:
        # 通過驗證
        return True

# 執行驗證，若未通過則中斷後續程式渲染
if not check_password():
    st.stop()


# --- 2. 全域配置與資料庫設定 ---
st.set_page_config(page_title="全球新聞智慧監控中心", layout="wide")

DB_NAME = 'news_monitor_v15.db' 

NEWS_SOURCES = [
    {"name": "BBC World", "url": "https://feeds.bbci.co.uk/news/world/rss.xml"},
    {"name": "CNN International", "url": "http://rss.cnn.com/rss/edition.rss"},
    {"name": "Reuters News", "url": "https://qz.com/rss"},
    {"name": "AP Top News", "url": "https://bits.blogs.nytimes.com/feed/"},
    {"name": "UDN 聯合國際", "url": "https://udn.com/rssnews/news/1013/7225?ch=udnnews"}
]

DEFAULT_CATEGORIES = {
    "軍事政治": ["military", "war", "russia", "israel", "defense", "election", "ukraine", "conflict", "sanctions", "die", "arrest", "retrial", "airstrike", "biden", "combat", "tactic", "ally", "ceasefire", "invasion", "refugee", "drone", "iran", "kuwait", "戰爭", "選舉", "軍事", "政治", "衝突", "烏克蘭", "俄羅斯", "以色列", "無人機", "襲擊", "科威特", "伊朗", "逮捕"],
    "經濟": ["economy", "inflation", "gdp", "fed", "rate", "finance", "market", "降息", "通膨", "股市", "經濟", "財經", "投資", "交易"],
    "科技": ["tech", "semiconductor", "apple", "google", "gpu", "tsmc", "nasa", "moon", "space", "astronaut", "台積電", "晶片", "科技", "人工智慧", "太空", "登月", "太空人", "電動車"],
    "體育": ["sport", "nba", "fifa", "olympics", "football", "tennis", "rookie", "mvp", "運動", "籃球", "奧運", "體育"],
    "民生健康": ["health", "virus", "climate", "food", "medicine", "symptoms", "desert", "stranded", "病毒", "氣候", "醫療", "健康", "民生", "拋錨", "高溫", "沙漠"]
}

CATEGORY_THEMES = {
    "經濟": {"emoji": "🔵", "label": "【經濟財經】"},
    "科技": {"emoji": "🟢", "label": "【科技創新】"},
    "體育": {"emoji": "🟠", "label": "【體育運動】"},
    "軍事政治": {"emoji": "🔴", "label": "【軍事政治】"},
    "民生健康": {"emoji": "🟣", "label": "【民生健康】"},
    "一般國際": {"emoji": "⚪", "label": "【一般國際】"}
}

COUNTRY_COORDS = {
    "美國大區": [37.0902, -95.7129], 
    "中國大區": [35.8617, 104.1954], 
    "英國大區": [55.3781, -3.4360],
    "台灣大區": [23.6978, 120.9605], 
    "烏克蘭大區": [48.3794, 31.1656], 
    "中東大區": [29.3117, 47.4818], 
    "日本大區": [36.2048, 138.2529], 
    "歐洲大區": [46.2276, 2.2137], 
    "俄羅斯大區": [55.7558, 37.6173],
    "非洲大區": [9.0820, 8.6753] 
}

DETAILED_LOCS = {
    "科威特": [29.3759, 47.9774], "伊朗": [32.4279, 53.6880], "以色列": [31.0461, 34.8516], 
    "加薩": [31.5000, 34.4667], "巴勒斯坦": [31.9522, 35.2332], "耶路撒冷": [31.7683, 35.2137],
    "撒哈拉": [20.0000, 10.0000], "紐約": [40.7128, -74.0060], "華盛頓": [38.9072, -77.0369],
    "莫斯科": [55.7558, 37.6173], "基輔": [50.4501, 30.5234], "東京": [35.6762, 139.6503],
    "台北": [25.0330, 121.5654], "台積電": [24.7820, 120.9950]
}

geolocator = Nominatim(user_agent="news_monitor_geo_v15_turbo")

# --- 3. LINE 官方帳號 Messaging API 推送函式 ---
def send_line_push_notification(title, category, source, link):
    """使用 LINE Messaging API 推送最新新聞給指定用戶"""
    try:
        # 從 Streamlit secrets 讀取金鑰，避免代碼在 GitHub 外洩
        LINE_ACCESS_TOKEN = st.secrets["LINE_CHANNEL_ACCESS_TOKEN"]
        LINE_USER_ID = st.secrets["LINE_USER_ID"]
        
        url = "https://api.line.me/v2/bot/message/push"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {LINE_ACCESS_TOKEN}"
        }
        
        # 封裝官方帳號的推播訊息格式 (Text message)
        theme = CATEGORY_THEMES.get(category, CATEGORY_THEMES["一般國際"])
        message_text = (
            f"🔔【全球新聞智慧監控 - 新聞推送】\n\n"
            f"📌 分類：{theme['emoji']} {category}\n"
            f"📡 來源：{source}\n"
            f"📝 標題：{title}\n\n"
            f"🔗 原文連結：{link}"
        )
        
        payload = {
            "to": LINE_USER_ID,
            "messages": [
                {
                    "type": "text",
                    "text": message_text
                }
            ]
        }
        
        response = requests.post(url, headers=headers, json=payload)
        return response.status_code == 200
    except Exception as e:
        print(f"LINE 推送失敗: {e}")
        return False

def hybrid_news_classifier(title_zh, title_en):
    match_text = (title_en + " " + title_zh).lower()
    scores = {k: 0 for k in DEFAULT_CATEGORIES.keys()}
    for cat, keywords in DEFAULT_CATEGORIES.items():
        for word in keywords:
            if word.lower() in match_text: 
                scores[cat] += match_text.count(word.lower())
    max_cat = max(scores, key=scores.get)
    return max_cat if scores[max_cat] > 0 else "一般國際"

@lru_cache(maxsize=1024)
def get_precise_coords(title_zh, title_en):
    match_text = (title_zh + " " + title_en).lower()
    
    for loc_name, coords in DETAILED_LOCS.items():
        if loc_name in title_zh or loc_name.lower() in match_text:
            return coords[0] + random.uniform(-0.1, 0.1), coords[1] + random.uniform(-0.1, 0.1), loc_name

    if any(k in match_text for k in ["伊朗", "科威特", "kuwait", "iran", "中東", "以色列", "加薩"]):
        base_lat, base_lon = COUNTRY_COORDS["中東大區"]
        return base_lat + random.uniform(-1.0, 1.0), base_lon + random.uniform(-1.0, 1.0), "中東區域"
    elif any(k in match_text for k in ["nasa", "美國", "紐約", "華盛頓", "川普", "拜登", "biden", "trump"]):
        base_lat, base_lon = COUNTRY_COORDS["美國大區"]
        return base_lat + random.uniform(-1.5, 1.5), base_lon + random.uniform(-1.5, 1.5), "美國區域"
    elif any(k in match_text for k in ["撒哈拉", "sahara", "非洲", "沙漠"]):
        base_lat, base_lon = COUNTRY_COORDS["非洲大區"]
        return base_lat + random.uniform(-2.0, 2.0), base_lon + random.uniform(-2.0, 2.0), "非洲區域"
    elif any(k in match_text for k in ["俄羅斯", "莫斯科", "普丁", "russia"]):
        base_lat, base_lon = COUNTRY_COORDS["俄羅斯大區"]
        return base_lat + random.uniform(-1.0, 1.0), base_lon + random.uniform(-1.0, 1.0), "俄羅斯區域"
    elif any(k in match_text for k in ["日本", "東京", "電動車", "tokyo"]):
        base_lat, base_lon = COUNTRY_COORDS["日本大區"]
        return base_lat + random.uniform(-0.5, 0.5), base_lon + random.uniform(-0.5, 0.5), "日本區域"

    try:
        geo_pattern = re.search(r'(在|於|往|在)([高屏台新北烏俄美英日中加巴克法德意伊科朝韓]{2,6})(市|省|縣|國|島)?', title_zh)
        if geo_pattern:
            extracted_loc = geo_pattern.group(2)
            location = geolocator.geocode(extracted_loc, timeout=0.4)
            if location:
                return location.latitude, location.longitude, extracted_loc
    except: pass

    global_keys = list(COUNTRY_COORDS.keys())
    chosen_zone = random.choice(global_keys)
    base_lat, base_lon = COUNTRY_COORDS[chosen_zone]
    return base_lat + random.uniform(-3.0, 3.0), base_lon + random.uniform(-3.0, 3.0), "全球焦點區域"

def get_db_connection():
    return sqlite3.connect(DB_NAME, check_same_thread=False, timeout=15)

def init_db():
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS monitor_logs
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      title_zh TEXT, category TEXT, source TEXT, time TEXT,
                      link TEXT UNIQUE, sentiment REAL, country TEXT, lat REAL, lon REAL, is_video INTEGER DEFAULT 0)''')
        c.execute('''CREATE TABLE IF NOT EXISTS user_tags (username TEXT PRIMARY KEY, tags TEXT)''')
        conn.commit()

def fetch_all_news():
    translator = GoogleTranslator(source='auto', target='zh-TW')
    with get_db_connection() as conn:
        c = conn.cursor()
        for src in NEWS_SOURCES:
            try:
                feed = feedparser.parse(src["url"])
                for entry in feed.entries[:5]: 
                    c.execute("SELECT id FROM monitor_logs WHERE link=?", (entry.link,))
                    if not c.fetchone():
                        link_lower = entry.link.lower()
                        title_lower = entry.title.lower()
                        
                        is_video = 1 if any(k in link_lower or k in title_lower for k in ["video", "/av/", "play", "影音", "🎥"]) else 0
                        sentiment_score = TextBlob(entry.title).sentiment.polarity

                        is_chinese = any('\u4e00' <= char <= '\u9fff' for char in entry.title)
                        if is_chinese:
                            title_zh = entry.title
                            title_en = ""
                        else:
                            title_en = entry.title
                            try: title_zh = translator.translate(entry.title)
                            except: title_zh = entry.title

                        cat = hybrid_news_classifier(title_zh, title_en)
                        exact_lat, exact_lon, final_location = get_precise_coords(title_zh, title_en)
                        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        
                        c.execute('''INSERT INTO monitor_logs
                                     (title_zh, category, source, time, link, sentiment, country, lat, lon, is_video)
                                     VALUES (?,?,?,?,?,?,?,?,?,?)''',
                                  (title_zh, cat, src["name"], now, entry.link, sentiment_score, final_location, exact_lat, exact_lon, is_video))
                        
                        # 新聞寫入資料庫成功的同時，觸發 LINE 官方帳號 Messaging API 推送
                        send_line_push_notification(title_zh, cat, src["name"], entry.link)
                        
            except: pass
        conn.commit()

def reset_database():
    with get_db_connection() as conn:
        conn.execute("DROP TABLE IF EXISTS monitor_logs")
    init_db()

if 'monitor_started' not in st.session_state:
    with st.spinner("極速多陸地地理引擎配置中..."):
        init_db()
        fetch_all_news()
    st.session_state['monitor_started'] = True

# --- 4. 狀態快取與控制 ---
if 'current_view' not in st.session_state: st.session_state['current_view'] = "🏠 首頁總覽"

def load_all_data():
    with get_db_connection() as conn:
        df = pd.read_sql_query("SELECT * FROM monitor_logs ORDER BY time DESC", conn)
        if not df.empty: df['time_dt'] = pd.to_datetime(df['time'])
        return df

df_all = load_all_data()
df_text_only = df_all[df_all['is_video'] == 0] if not df_all.empty else df_all
df_videos_only = df_all[df_all['is_video'] == 1] if not df_all.empty else df_all

# --- 5. 側邊欄與功能面板介面優化 ---
st.sidebar.title(f"👤 {st.session_state['username']}")
if st.sidebar.button("🔄 5秒極速重組與同步新聞", key="side_sync_btn"):
    with st.spinner("清空舊數據，5秒內重新極速同步中..."):
        reset_database()
        fetch_all_news()
    st.rerun()

st.sidebar.write("---")
all_available_tags = list(DEFAULT_CATEGORIES.keys()) + ["一般國際"]
for tag in all_available_tags:
    st.sidebar.checkbox(f"🔖 {tag}", value=True, key=f"sidebar_fixed_cb_{tag}")

st.write("### 🧭 系統主功能面板")
base_menu = ["🏠 首頁總覽", "📺 影音新聞特區", "⏳ 歷史總時間軸", "📊 數據統計分析", "🔍 關鍵字搜尋"]
cols_row1 = st.columns(len(base_menu))
for idx, item_name in enumerate(base_menu):
    if cols_row1[idx].button(item_name, width='stretch', key=f"nav_row1_{idx}"):
        st.session_state['current_view'] = item_name

st.write("### 🔖 訂閱新聞分類頻道")
cols_row2 = st.columns(len(all_available_tags))
for idx, item_name in enumerate(all_available_tags):
    if cols_row2[idx].button(f"🔖 {item_name}", width='stretch', key=f"nav_row2_{idx}"):
        st.session_state['current_view'] = f"🔖 {item_name}"
st.write("---")

# --- 6. 新聞卡片元件 ---
def render_native_news_cards(df_target):
    if df_target.empty:
        st.info("💡 該時段或分類目前暫無新聞條目。")
        return
    for idx, row in df_target.iterrows():
        cat = row['category']
        theme = CATEGORY_THEMES.get(cat, CATEGORY_THEMES["一般國際"])
        sentiment_text = "正面" if row['sentiment'] > 0.05 else ("負面" if row['sentiment'] < -0.05 else "中性")
        with st.container(border=True):
            col_meta, col_title, col_btn = st.columns([2.5, 7.0, 2.5])
            with col_meta:
                st.markdown(f"**{theme['emoji']} {theme['label']}**")
                st.caption(f"📡 來源: `{row['source']}`")
            with col_title:
                st.markdown(f"#### {row['title_zh']}")
                st.markdown(f"⏱️ `發布時間: {row['time']}` &nbsp;|&nbsp; 📍 解析區域: **{row['country']}** &nbsp;|&nbsp; 📊 輿情: `{sentiment_text}`")
            with col_btn:
                html_link = f'<a href="{row["link"]}" target="_blank"><button style="width:100%; padding:8px; background-color:#ffffff; border:1px solid #dcdcdc; border-radius:4px; cursor:pointer; font-weight:bold; color:#31333F;">🔗 前往原文</button></a>'
                st.markdown(html_link, unsafe_allow_html=True)

# --- 7. 路由視圖渲染 ---
if st.session_state['current_view'] == "🏠 首頁總覽":
    st.title("🗺️ 全球即時新聞事件精準地圖")
    if df_all.empty: 
        st.warning("⏱️ 資料庫目前暫無數據，請點擊左側同步。")
    else:
        fig_map = px.scatter_geo(df_all, lat='lat', lon='lon', hover_name='title_zh', 
                                 hover_data={'source': True, 'time': True, 'category': True, 'country': True, 'lat': False, 'lon': False}, 
                                 projection="equirectangular", title="全球最新焦點事件精確分佈圖", color_discrete_sequence=["#ff4b4b"])
        fig_map.update_geos(showcountries=True, countrycolor="lightgray", showcoastlines=True, visible=True)
        fig_map.update_traces(marker=dict(size=11, opacity=0.85))
        fig_map.update_layout(height=600, margin={"r":0,"t":40,"l":0,"b":0})
        st.plotly_chart(fig_map, use_container_width=True, key="main_live_map")
        
        st.write("### 🔔 最新發布新聞動態")
        render_native_news_cards(df_all)

elif st.session_state['current_view'] == "📺 影音新聞特區":
    st.title("📺 全球即時影音新聞快報牆")
    if df_videos_only.empty:
        st.info("💡 目前資料庫尚未擷取到影音新聞。")
    else:
        for idx, row in df_videos_only.iterrows():
            with st.container(border=True):
                col_title, col_btn = st.columns([9.0, 3.0])
                with col_title:
                    st.markdown(f"### 🎥 {row['title_zh']}")
                    st.caption(f"📡 來源: **{row['source']}** &nbsp;|&nbsp; ⏱️ 時間: `{row['time']}` &nbsp;|&nbsp; 📍 區域: **{row['country']}**")
                with col_btn:
                    button_html = f"""
                    <div style="padding-top: 10px;">
                        <a href="{row['link']}" target="_blank" style="text-decoration: none;">
                            <button style="
                                width: 100%;
                                background-color: #FF4B4B;
                                color: white;
                                padding: 10px;
                                border: none;
                                border-radius: 6px;
                                font-weight: bold;
                                cursor: pointer;
                                text-align: center;
                            ">
                                🔗 前往影音原文
                            </button>
                        </a>
                    </div>
                    """
                    st.markdown(button_html, unsafe_allow_html=True)

elif st.session_state['current_view'] == "⏳ 歷史總時間軸":
    st.title("⏳ 全球歷史即時總時間軸")
    render_native_news_cards(df_text_only)

elif st.session_state['current_view'] == "📊 數據統計分析":
    st.title("📊 全球新聞數據統計分析")
    if df_all.empty: st.warning("資料庫內暫無數據。")
    else:
        st.plotly_chart(px.histogram(df_all, x="category", title="各分類新聞總量分佈", color="category"), use_container_width=True)

elif st.session_state['current_view'] == "🔍 關鍵字搜尋":
    st.title("🔍 全域新聞關鍵字檢索")
    search_query = st.text_input("輸入要查詢的關鍵字：", placeholder="例如：科威特、NASA")
    if search_query and not df_all.empty:
        render_native_news_cards(df_all[df_all['title_zh'].str.contains(search_query, na=False, case=False)])

elif st.session_state['current_view'].startswith("🔖 "):
    target_tag = st.session_state['current_view'].replace("🔖 ", "")
    st.title(f"🔖 分類專屬獨立時間軸：{target_tag}")
    if not df_all.empty:
        render_native_news_cards(df_all[df_all['category'] == target_tag])
