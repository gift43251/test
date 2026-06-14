import streamlit as st
import feedparser
import requests
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
import folium
from streamlit_folium import st_folium
from concurrent.futures import ThreadPoolExecutor, as_completed
from apscheduler.schedulers.background import BackgroundScheduler

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

DEFAULT_CATEGORIES = {
    "軍事政治": ["military", "war", "russia", "israel", "defense", "election", "ukraine", "conflict", "sanctions", "die", "arrest", "retrial", "airstrike", "biden", "combat", "tactic", "ally", "ceasefire", "invasion", "refugee", "戰爭", "選舉", "軍事", "政治", "衝突", "烏克蘭", "俄羅斯", "以色列"],
    "經濟": ["economy", "inflation", "gdp", "fed", "rate", "finance", "降息", "通膨", "股市", "經濟", "財經"],
    "科技": ["tech", "semiconductor", "apple", "google", "gpu", "tsmc", "spaceX", "nvidia", "台積電", "晶片", "科技", "人工智慧"],
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

LOCATION_COORDS = {
    "台北": [25.0330, 121.5654], "taipei": [25.0330, 121.5654],
    "東京": [35.6762, 139.6503], "tokyo": [35.6762, 139.6503],
    "紐約": [40.7128, -74.0060], "new york": [40.7128, -74.0060], "nyc": [40.7128, -74.0060],
    "倫敦": [51.5074, -0.1278], "london": [51.5074, -0.1278],
    "巴黎": [48.8566, 2.3522], "paris": [48.8566, 2.3522],
    "首爾": [37.5665, 126.9780], "seoul": [37.5665, 126.9780],
    "北京": [39.9042, 116.4074], "beijing": [39.9042, 116.4074],
    "上海": [31.2304, 121.4737], "shanghai": [31.2304, 121.4737],
    "香港": [22.3193, 114.1694], "hong kong": [22.3193, 114.1694],
    "新加坡": [1.3521, 103.8198], "singapore": [1.3521, 103.8198],
    "洛杉磯": [34.0522, -118.2437], "los angeles": [34.0522, -118.2437],
    "台灣": [23.6978, 120.9605], "taiwan": [23.6978, 120.9605],
    "美國": [37.0902, -95.7129], "america": [37.0902, -95.7129], "united states": [37.0902, -95.7129], "usa": [37.0902, -95.7129],
    "中國": [35.8617, 104.1954], "china": [35.8617, 104.1954],
    "日本": [36.2048, 138.2529], "japan": [36.2048, 138.2529],
    "烏克蘭": [48.3794, 31.1656], "ukraine": [48.3794, 31.1656],
    "俄羅斯": [61.5240, 105.3188], "russia": [61.5240, 105.3188],
    "以色列": [31.0461, 34.8516], "israel": [31.0461, 34.8516],
    "全球": [20.0, 0.0], "world": [20.0, 0.0], "global": [20.0, 0.0]
}

CRISIS_STRONG_WORDS = [
    "襲擊", "無人機", "轟炸", "導彈", "開火", "進攻", "突襲", "交火", "戰機", "軍事演習",
    "劫持", "人質", "擊斃", "槍擊", "逮捕", "爆炸", "恐怖襲擊", "死亡", "死傷", "炸彈",
    "combat", "drone", "attack", "missile", "hostage", "shot dead", "hijack", "explode", "bomb"
]

# --- 2. AI 分類器 ---
@st.cache_resource(show_spinner=False)
def load_classifier():
    try:
        from transformers import pipeline as hf_pipeline
        return hf_pipeline("zero-shot-classification", model="vicgalle/xlm-roberta-large-xnli-anli")
    except Exception:
        return None

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
    except Exception:
        return "一般國際"

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

# --- 3. 資料庫 ---
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
                     (id INTEGER PRIMARY KEY, line_token TEXT, user_id TEXT, keywords TEXT)''')
        try:
            c.execute("ALTER TABLE push_settings ADD COLUMN user_id TEXT;")
        except sqlite3.OperationalError:
            pass 
        c.execute('''INSERT OR IGNORE INTO push_settings (id, line_token, user_id, keywords) 
                     VALUES (1, '', '', '')''')
        c.execute("CREATE INDEX IF NOT EXISTS idx_time ON monitor_logs(time DESC)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_category ON monitor_logs(category)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_link ON monitor_logs(link)")
        conn.commit()

init_db()

# --- 4. 新聞抓取與 LINE 推播 ---
def send_line_push(channel_access_token, user_id, message_text):
    if not channel_access_token or not user_id:
        return None
    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {channel_access_token}"
    }
    payload = {
        "to": user_id,
        "messages": [{"type": "text", "text": message_text}]
    }
    try:
        response = requests.post(url, json=payload, headers=headers)
        return response.status_code
    except Exception:
        return None

def _detect_country(t_lower, z_lower):
    target = "全球"
    for loc_name in LOCATION_COORDS.keys():
        if loc_name.isalpha():
            if re.search(r'\b' + re.escape(loc_name) + r'\b', t_lower):
                target = loc_name
                break
        else:
            if loc_name in z_lower:
                target = loc_name
                break
                
    if target == "全球":
        if "white house" in t_lower or "trump" in t_lower or "biden" in t_lower:
            target = "美國"
            
    coords = LOCATION_COORDS.get(target, [20.0, 0.0])
    
    display_mapping = {
        "tokyo": "東京", "new york": "紐約", "london": "倫敦", "paris": "巴黎",
        "taiwan": "台灣", "america": "美國", "china": "中國", "japan": "日本", "world": "全球"
    }
    final_country_name = display_mapping.get(target, target)
    return final_country_name, coords[0], coords[1]

def _fetch_source_raw(src):
    results = []
    try:
        feed = feedparser.parse(
            src["url"],
            request_headers={"User-Agent": "Mozilla/5.0 (compatible; NewsBot/1.0)"}
        )
        for entry in feed.entries[:12]:
            title_raw = getattr(entry, 'title', '').strip()
            link_raw = getattr(entry, 'link', '').strip()
            if not title_raw or not link_raw:
                continue
            if "error 500" in title_raw.lower() or "server error" in title_raw.lower():
                continue
            results.append((title_raw, link_raw, src["name"]))
    except Exception:
        pass
    return results

def _translate_batch(titles_en, translator, batch_size=8):
    translations = {}
    groups = [titles_en[i:i+batch_size] for i in range(0, len(titles_en), batch_size)]
    for group in groups:
        combined = " ||| ".join(group)
        try:
            translated = translator.translate(combined)
            parts = [p.strip() for p in translated.split("|||")]
            for j, orig in enumerate(group):
                translations[orig] = parts[j] if j < len(parts) else orig
        except Exception:
            for orig in group:
                translations[orig] = orig
    return translations

def fetch_all_news():
    all_raw = []
    with ThreadPoolExecutor(max_workers=len(NEWS_SOURCES)) as executor:
        futures = [executor.submit(_fetch_source_raw, src) for src in NEWS_SOURCES]
        for future in as_completed(futures):
            all_raw.extend(future.result())

    if not all_raw:
        return

    with get_db_connection() as conn:
        existing_links = set(row[0] for row in conn.execute("SELECT link FROM monitor_logs").fetchall())

    new_entries = [(t, l, s) for t, l, s in all_raw if l not in existing_links]
    if not new_entries:
        return

    translator = GoogleTranslator(source='auto', target='zh-TW')
    to_translate = []
    chinese_ready = []

    for title_raw, link_raw, source_name in new_entries:
        is_chinese = any('\u4e00' <= char <= '\u9fff' for char in title_raw)
        if is_chinese:
            chinese_ready.append((title_raw, "", link_raw, source_name))
        else:
            to_translate.append((title_raw, link_raw, source_name))

    translation_map = {}
    if to_translate:
        translation_map = _translate_batch([t[0] for t in to_translate], translator)

    translated_entries = []
    for title_en, link_raw, source_name in to_translate:
        title_zh = translation_map.get(title_en, title_en)
        translated_entries.append((title_zh, title_en, link_raw, source_name))

    all_processed = chinese_ready + translated_entries
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rows_to_insert = []
    
    for title_zh, title_en, link_raw, source_name in all_processed:
        cat = hybrid_news_classifier(title_zh, title_en)
        sentiment_score = TextBlob(title_en if title_en else title_zh).sentiment.polarity
        country, rand_lat, rand_lon = _detect_country(title_en.lower(), title_zh.lower())
        rows_to_insert.append((title_zh, cat, source_name, now, link_raw, sentiment_score, country, rand_lat, rand_lon))

    with get_db_connection() as conn:
        conn.executemany(
            '''INSERT OR IGNORE INTO monitor_logs (title_zh, category, source, time, link, sentiment, country, lat, lon)
               VALUES (?,?,?,?,?,?,?,?,?)''', rows_to_insert
        )
        conn.commit()

# --- 5. 背景排程 ---
@st.cache_resource
def start_scheduler():
    scheduler = BackgroundScheduler(timezone="Asia/Taipei")
    scheduler.add_job(fetch_all_news, 'interval', minutes=5, id='news_fetch', max_instances=1, coalesce=True)
    scheduler.start()
    return scheduler

start_scheduler()

# --- 6. 資料庫查詢函數 ---
@st.cache_data(ttl=60)
def query_all_data():
    with get_db_connection() as conn:
        df = pd.read_sql_query("SELECT * FROM monitor_logs ORDER BY time DESC", conn)
    if not df.empty:
        df['time_dt'] = pd.to_datetime(df['time'])
    return df

@st.cache_data(ttl=30)
def query_recent_hour_data():
    one_hour_ago = (datetime.now() - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
    with get_db_connection() as conn:
        df = pd.read_sql_query("SELECT * FROM monitor_logs WHERE time >= ? ORDER BY time DESC", conn, params=(one_hour_ago,))
    if not df.empty:
        df['time_dt'] = pd.to_datetime(df['time'])
    return df

def get_user_tags(username):
    if st.session_state.get('is_guest') and 'guest_tags' in st.session_state:
        return st.session_state['guest_tags']
    with get_db_connection() as conn:
        res = conn.execute("SELECT tags FROM user_tags WHERE username=?", (username,)).fetchone()
    return res[0].split(",") if res and res[0] else list(DEFAULT_CATEGORIES.keys()) + ["一般國際"]

def save_user_tags(username, tags):
    with get_db_connection() as conn:
        conn.execute("INSERT OR REPLACE INTO user_tags (username, tags) VALUES (?, ?)", (username, ",".join(tags)))
        conn.commit()

# --- 8. Session State 初始化 ---
if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False
if 'username' not in st.session_state:
    st.session_state['username'] = ""
if 'is_guest' not in st.session_state:
    st.session_state['is_guest'] = False
if 'current_view' not in st.session_state:
    st.session_state['current_view'] = "🏠 首頁總覽"

# --- 9. 登入管制牆 ---
if not st.session_state['logged_in'] and not st.session_state['is_guest']:
    st.title("全球新聞智能監控系統")
    col1, col2 = st.columns(2)
    with col1:
        with st.container(border=True):
            st.markdown("### 🔑 會員登入")
            username_input = st.text_input("使用者名稱", key="login_user")
            password_input = st.text_input("密碼", type="password", key="login_pwd")
            if st.button("進入會員系統", use_container_width=True):
                if username_input.strip() == "tester1" and password_input == "donoterror":
                    st.session_state['logged_in'] = True
                    st.session_state['username'] = username_input.strip()
                    st.rerun()
    with col2:
        with st.container(border=True):
            st.markdown("### 🌐 訪客快捷通道")
            if st.button("🚀 以訪客身份免登入進入", use_container_width=True, type="primary"):
                st.session_state['is_guest'] = True
                st.session_state['username'] = "訪客模式 Guest"
                st.session_state['guest_tags'] = list(DEFAULT_CATEGORIES.keys()) + ["一般國際"]
                st.rerun()
    st.stop()

# --- 10. 側邊欄 ---
st.sidebar.title(f"👤 {st.session_state['username']}")
saved_tags = get_user_tags(st.session_state['username'])
selected_tags = []
for tag in list(DEFAULT_CATEGORIES.keys()) + ["一般國際"]:
    if st.sidebar.checkbox(f"🔖 {tag}", value=tag in saved_tags, key=f"sb_{tag}"):
        selected_tags.append(tag)

if st.sidebar.button("🚪 登出", use_container_width=True):
    st.session_state['logged_in'] = False
    st.session_state['is_guest'] = False
    st.rerun()

# --- 11. 導覽列 ---
base_menu = ["🏠 首頁總覽", "📊 數據統計分析", "🔍 關鍵字搜尋"]
cols = st.columns(len(base_menu))
for idx, item in enumerate(base_menu):
    if cols[idx].button(item, use_container_width=True, type="primary" if st.session_state['current_view'] == item else "secondary"):
        st.session_state['current_view'] = item
        st.rerun()

# --- 12. 新聞卡片元件 ---
def render_native_news_cards(df_target):
    if df_target is None or df_target.empty:
        st.info("💡 目前暫無新聞條目。")
        return
    for i, (_, row) in enumerate(df_target.iterrows()):
        with st.container(border=True):
            col_title, col_btn = st.columns([9, 3])
            with col_title:
                st.markdown(f"#### {row['title_zh']}")
                st.caption(f"來源: {row['source']} | 時間: {row['time']} | 區域: {row['country']}")
            with col_btn:
                st.link_button("🔗 原文連結", row['link'], use_container_width=True)

# --- 13. 路由渲染邏輯 ---
current = st.session_state['current_view']

if current == "🏠 首頁總覽":
    st.title("🗺️ 全球即時新聞事件地圖 (最近 1 小時)")
    df_recent = query_recent_hour_data()

    if df_recent.empty:
        st.warning("⏱️ 最近 1 小時內國際新聞台暫無新發布事件。")
    else:
        m = folium.Map(location=[20.0, 0.0], zoom_start=2, tiles="OpenStreetMap")
        for _, row in df_recent.iterrows():
            if pd.isna(row['lat']) or pd.isna(row['lon']):
                continue
            cat = row['category']
            theme = CATEGORY_THEMES.get(cat, CATEGORY_THEMES["一般國際"])
            
            popup_html = f"<a href='{row['link']}' target='_blank'>{row['title_zh']}</a>"
            folium.CircleMarker(
                location=[row['lat'], row['lon']],
                radius=8,
                popup=folium.Popup(popup_html, max_width=300),
                color=theme['color'],
                fill=True,
                fill_color=theme['color']
            ).add_to(m)
            
        st_folium(m, width=1200, height=500)
        st.subheader("📰 即時新聞清單")
        render_native_news_cards(df_recent)

elif current == "📊 數據統計分析":
    st.title("📊 數據統計分析")
    df_all = query_all_data()
    if not df_all.empty:
        fig = px.pie(df_all, names='category', title='新聞分類比例')
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("暫無可用數據進行統計。")

elif current == "🔍 關鍵字搜尋":
    st.title("🔍 關鍵字搜尋")
    search_query = st.text_input("輸入關鍵字搜尋新聞標題：")
    if search_query:
        df_all = query_all_data()
        if not df_all.empty:
            df_filtered = df_all[df_all['title_zh'].str.contains(search_query, case=False, na=False)]
            render_native_news_cards(df_filtered)
