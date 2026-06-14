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

COUNTRY_COORDS = {
    "美國": [37.0902, -95.7129], "中國": [35.8617, 104.1954], "英國": [55.3781, -3.4360],
    "台灣": [23.6978, 120.9605], "烏克蘭": [48.3794, 31.1656], "中東": [32.4279, 53.6880],
    "日本": [36.2048, 138.2529], "歐洲": [48.6909, 9.1406], "全球": [20.0, 0.0]
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
        
        # 強制幫舊的資料表追加 user_id 欄位，防止舊資料庫報錯
        try:
            c.execute("ALTER TABLE push_settings ADD COLUMN user_id TEXT;")
        except sqlite3.OperationalError:
            pass  # 如果欄位以前就已經加過了，就直接忽略，不會卡住
        
        # 加速查詢索引
        c.execute("CREATE INDEX IF NOT EXISTS idx_time ON monitor_logs(time DESC)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_category ON monitor_logs(category)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_link ON monitor_logs(link)")
        conn.commit()

# 🔥【關鍵修復】在聲明完 init_db 函數後，立刻執行它，確保後面的代碼不會因為找不到表而崩潰
init_db()

# --- 4. 新聞抓取與 LINE 推播 ---
def send_line_push(channel_access_token, user_id, message_text):
    """透過 LINE Messaging API 發送主動推播訊息"""
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
    if "美國" in z_lower or "川普" in z_lower or "白宮" in z_lower or re.search(r'\btrump\b|\bamerica\b|\bwashington\b|\bwhite\s+house\b|\busa\b', t_lower):
        target = "美國"
    elif "台灣" in z_lower or "台積電" in z_lower or re.search(r'\btaiwan\b', t_lower):
        target = "台灣"
    elif "烏克蘭" in z_lower or re.search(r'\bukraine\b', t_lower):
        target = "烏克蘭"
    elif "中國" in z_lower or re.search(r'\bchina\b', t_lower):
        target = "中國"
    elif "英國" in z_lower or re.search(r'\buk\b|\bbritain\b|\blondon\b', t_lower):
        target = "英國"
    elif "日本" in z_lower or re.search(r'\bjapan\b', t_lower):
        target = "日本"
    elif "中東" in z_lower or "以色列" in z_lower or "加薩" in z_lower or re.search(r'\bisrael\b|\bgaza\b', t_lower):
        target = "中東"
    elif "歐洲" in z_lower or re.search(r'\beurope\b', t_lower):
        target = "歐洲"
    elif re.search(r'\bus\b', t_lower):
        target = "美國"
    else:
        target = "全球"

    base_lat, base_lon = COUNTRY_COORDS[target]
    offset = 0.8 if target != "全球" else 5
    rand_lat = base_lat + random.uniform(-offset, offset)
    rand_lon = base_lon + random.uniform(-offset, offset)
    return target, rand_lat, rand_lon

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
        existing_links = set(
            row[0] for row in conn.execute("SELECT link FROM monitor_logs").fetchall()
        )

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
            '''INSERT OR IGNORE INTO monitor_logs
               (title_zh, category, source, time, link, sentiment, country, lat, lon)
               VALUES (?,?,?,?,?,?,?,?,?)''',
            rows_to_insert
        )
        conn.commit()

    try:
        with get_db_connection() as conn:
            push_cfg = conn.execute("SELECT line_token, user_id, keywords FROM push_settings WHERE id=1").fetchone()
        
        if push_cfg and push_cfg[0] and push_cfg[1] and push_cfg[2]:
            token, user_id, keywords_str = push_cfg
            user_keywords = [k.strip() for k in keywords_str.split(",") if k.strip()]
            
            for title_zh, _, link_raw, source_name in all_processed:
                for kw in user_keywords:
                    if kw.lower() in title_zh.lower():
                        alert_msg = f"📢 智能預警：偵測到關鍵字【{kw}】相關新聞！\n\n📰 標題：{title_zh}\n📡 來源：{source_name}\n🔗 原文連結：{link_raw}"
                        send_line_push(token, user_id, alert_msg)
                        break
    except Exception:
        pass

# --- 5. 背景排程 ---
@st.cache_resource
def start_scheduler():
    scheduler = BackgroundScheduler(timezone="Asia/Taipei")
    scheduler.add_job(fetch_all_news, 'interval', minutes=5, id='news_fetch',
                      max_instances=1, coalesce=True)
    scheduler.start()
    return scheduler

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
        df = pd.read_sql_query(
            "SELECT * FROM monitor_logs WHERE time >= ? ORDER BY time DESC",
            conn, params=(one_hour_ago,)
        )
    if not df.empty:
        df['time_dt'] = pd.to_datetime(df['time'])
    return df

@st.cache_data(ttl=60)
def query_category_data(category_name):
    with get_db_connection() as conn:
        df = pd.read_sql_query(
            "SELECT * FROM monitor_logs WHERE category = ? ORDER BY time DESC",
            conn, params=(category_name,)
        )
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
    st.subheader("請選擇進入模式以開啟個性化儀表板")

    col1, col2 = st.columns(2)
    with col1:
        with st.container(border=True):
            st.markdown("### 🔑 會員/自訂用戶登入")
            username_input = st.text_input("使用者名稱", placeholder="請輸入使用者名稱", key="login_user")
            password_input = st.text_input("密碼", type="password", placeholder="******", key="login_pwd")
            
            if st.button("進入會員系統", use_container_width=True, key="btn_member_login"):
                if username_input.strip() == "tester1" and password_input == "donoterror":
                    st.session_state['logged_in'] = True
                    st.session_state['is_guest'] = False
                    st.session_state['username'] = username_input.strip()
                    st.session_state['current_view'] = "🏠 首頁總覽"
                    st.success("登入成功！正在載入系統...")
                    time.sleep(0.5)
                    st.rerun()
                elif not username_input.strip() or not password_input:
                    st.error("❌ 請輸入完整的帳號與密碼！")
                else:
                    st.error("❌ 帳號或密碼錯誤，請重新輸入！")
                        
    with col2:
        with st.container(border=True):
            st.markdown("### 🌐 訪客快捷通道")
            st.write("免帳號密碼快捷登入，即刻查看全球一小時內最新事件地圖。")
            if st.button("🚀 以訪客身份免登入進入", use_container_width=True, type="primary", key="btn_guest_login"):
                st.session_state['is_guest'] = True
                st.session_state['logged_in'] = False
                st.session_state['username'] = "訪客模式 Guest"
                st.session_state['guest_tags'] = list(DEFAULT_CATEGORIES.keys()) + ["一般國際"]
                st.session_state['current_view'] = "🏠 首頁總覽"
                st.rerun()
    st.stop()

# --- 10. 側邊欄 ---
st.sidebar.title(f"👤 {st.session_state['username']}")

if st.sidebar.button("🔄 手動同步最新新聞", key="side_sync_btn"):
    with st.spinner("正在重新爬取各國新聞..."):
        fetch_all_news()
    st.cache_data.clear()
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
    st.session_state['username'] = ""
    st.session_state['current_view'] = "🏠 首頁總覽"
    if 'guest_tags' in st.session_state:
        del st.session_state['guest_tags']
    if 'monitor_started' in st.session_state:
        del st.session_state['monitor_started']
    st.rerun()


# --- 11. 導覽列 ---
def set_view(view_name):
    st.session_state['current_view'] = view_name

st.write("### 🧭 系統主功能面板")
base_menu = ["🏠 首頁總覽", "🎬 影片專區", "⏳ 歷史總時間軸", "📊 數據統計分析", "🔍 關鍵字搜尋"]

if not st.session_state.get('is_guest', False):
    base_menu.append("📢 LINE通知設定")

cols_row1 = st.columns(len(base_menu))
for idx, item_name in enumerate(base_menu):
    is_active = st.session_state['current_view'] == item_name
    btn_type = "primary" if is_active else "secondary"
    if cols_row1[idx].button(item_name, use_container_width=True, key=f"nav_row1_{idx}", type=btn_type):
        set_view(item_name)
        st.rerun()

st.write("### 🔖 訂閱新聞分類頻道")
category_menu = [f"🔖 {t}" for t in selected_tags]

if category_menu:
    cols_row2 = st.columns(len(category_menu))
    for idx, item_name in enumerate(category_menu):
        is_active = st.session_state['current_view'] == item_name
        btn_type = "primary" if is_active else "secondary"
        if cols_row2[idx].button(item_name, use_container_width=True, key=f"nav_row2_{idx}", type=btn_type):
            set_view(item_name)
            st.rerun()


# --- 12. 新聞卡片元件 ---
def render_native_news_cards(df_target):
    if df_target is None or df_target.empty:
        st.info("💡 該時段或分類目前暫無新聞條目。")
        return

    core_categories = ["軍事政治", "經濟", "科技", "體育", "民生健康", "一般國際"]
    nav_options = ["請選擇要移動至的分頁..."] + [f"🔖 {c}" for c in core_categories]

    for i, (_, row) in enumerate(df_target.iterrows()):
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
                st.link_button("🔗 前往原文", row['link'], use_container_width=True, key=f"lnk_{i}_{news_id}")
                st.write("")

                selected_nav = st.selectbox(
                    "移動至 👇",
                    options=nav_options,
                    index=0,
                    key=f"move_sel_{i}_{news_id}",
                    label_visibility="collapsed"
                )

                if selected_nav != "請選擇要移動至的分頁...":
                    new_category = selected_nav.replace("🔖 ", "")
                    with get_db_connection() as conn:
                        conn.execute("UPDATE monitor_logs SET category = ? WHERE id = ?", (new_category, news_id))
                        conn.commit()
                    st.cache_data.clear()
                    st.session_state['current_view'] = selected_nav
                    st.rerun()


# --- 13. 各分頁路由渲染邏輯 ---
current = st.session_state['current_view']

# A. 首頁總覽
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
            color = theme.get("color", "gray")

            popup_html = f"""
            <div style='font-family: sans-serif; min-width: 200px;'>
                <h4>{theme['emoji']} {row['category']}</h4>
                <p><b>{row['title_zh']}</b></p>
                <small>📡 來源: {row['source']}<br>⏱️ 時間: {row['time']}</small><br><br>
                <a href='{row['link']}' target='_blank'
                   style='display:inline-block; padding:5px 10px; background-color:#ff4b4b;
                          color:white; text-decoration:none; border-radius:4px;'>前往原文</a>
            </div>
            """
            folium.CircleMarker(
                location=[row['lat'], row['lon']],
                radius=8,
                popup=folium.Popup(popup_html, max_width=300),
                color=color,
                fill=True,
                fill_color=color,
                fill_opacity=0.7
            ).add_to(m)

        st_folium(m, width="100%", height=600, key="main_live_map_folium")
        st.write("---")
        st.write("### 🔔 焦點對應：最近 1 小時內發布的新聞條目")
        render_native_news_cards(df_recent)

# B. 影片專區
elif current == "🎬 影片專區":
    st.title("🎬 24小時即時新聞影音專區")
    st.markdown("系統自動偵測並彙整爬蟲抓取到的最新影音與動態新聞。")
    
    df_news = query_all_data()
    
    if not df_news.empty:
        video_keywords = ["影片", "影音", "直播", "live", "video", "視頻", "播報"]
        df_videos = df_news[df_news['title_zh'].str.lower().str.contains('|'.join(video_keywords), na=False)]
        
        if not df_videos.empty:
            st.subheader(f"📹 最新偵測到的影音新聞 (共 {len(df_videos)} 則)")
            
            for i in range(0, len(df_videos), 2):
                v_col1, v_col2 = st.columns(2)
                
                with v_col1:
                    row1 = df_videos.iloc[i]
                    st.markdown(f"### 🔴 {row1['title_zh']}")
                    st.caption(f"📡 來源：{row1['source']} | 📅 時間：{row1['time']} | 🏷️ 分類：{row1['category']}")
                    st.link_button("🌐 前往觀看影音新聞", row1['link'], use_container_width=True)
                
                if i + 1 < len(df_videos):
                    with v_col2:
                        row2 = df_videos.iloc[i+1]
                        st.markdown(f"### 🔴 {row2['title_zh']}")
                        st.caption(f"📡 來源：{row2['source']} | 📅 時間：{row2['time']} | 🏷️ 分類：{row2['category']}")
                        st.link_button("🌐 前往觀看影音新聞", row2['link'], use_container_width=True)
                
                st.write("---")
        else:
            st.info("ℹ️ 目前資料庫中暫時沒有偵測到包含影音關鍵字的新聞。")
    else:
        st.warning("⚠️ 目前資料庫內尚無新聞資料。")
        
# C. 歷史總時間軸
elif current == "⏳ 歷史總時間軸":
    st.title("⏳ 全球歷史即時總時間軸")
    df_all = query_all_data()
    render_native_news_cards(df_all)

# D. 數據統計分析
elif current == "📊 數據統計分析":
    st.title("📊 全球新聞數據統計分析")
    df_all = query_all_data()
    if df_all.empty:
        st.warning("資料庫內暫無數據可供分析。")
    else:
        col_f1, col_f2 = st.columns([1, 1])
        
        with col_f1:
            st.write("### 🍩 各類別新聞佔比")
            category_counts = df_all['category'].value_counts().reset_index()
            category_counts.columns = ['category', 'count']
            fig_pie = px.pie(category_counts, names='category', values='count', 
                             title="各類別發布比例", hole=0.4)
            st.plotly_chart(fig_pie, use_container_width=True, key="stat_pie_chart")
            
        with col_f2:
            st.write("### 📈 新聞動態抓取走勢線")
            df_trend = df_all.copy()
            df_trend['time_group'] = df_trend['time_dt'].dt.floor('10min').dt.strftime("%Y-%m-%d %H:%M")
            time_trend = df_trend.groupby(['time_group', 'category']).size().reset_index(name='新聞數量')
            time_trend = time_trend.sort_values(by='time_group')
            fig_line = px.line(time_trend, x="time_group", y="新聞數量", color="category", title="趨勢走勢線", markers=True)
            st.plotly_chart(fig_line, use_container_width=True, key="stat_line_chart")
            
        st.write("---")
        st.write("### ⏱️ 24小時新聞發布頻率線")
        fig_hist = px.histogram(df_all, x="time_dt", color="category", nbins=24, title="24小時發布頻率直方圖")
        st.plotly_chart(fig_hist, use_container_width=True, key="stat_hist_chart")

# E. 關鍵字搜尋
elif current == "🔍 關鍵字搜尋":
    st.title("🔍 全域新聞關鍵字檢索")
    search_query = st.text_input("輸入要查詢的關鍵字：", placeholder="例如：台積電、晶片、戰爭", key="search_box_input")
    df_all = query_all_data()
    if search_query and not df_all.empty:
        results = df_all[df_all['title_zh'].str.contains(search_query, na=False, case=False)]
        st.write(f"共找到 {len(results)} 筆符合條件的條目：")
        results = results.copy()
        render_native_news_cards(results)
    elif search_query:
        st.info("目前尚無符合該關鍵字的新聞。")

# F. LINE通知設定
elif current == "📢 LINE通知設定":
    st.title("📢 LINE 官方帳號 智慧預警推送")
    st.markdown("由於 LINE Notify 已停止服務，系統已全面升級為 LINE 官方帳號（Messaging API）主動預警推播機制。")
    st.info("💡 提醒：請確保您的手機 LINE 已將該官方帳號加為好友，否則系統將無法成功推送訊息。")
    
    with get_db_connection() as conn:
        curr_config = conn.execute("SELECT line_token, user_id, keywords FROM push_settings WHERE id=1").fetchone()
    
    display_token = curr_config[0] if curr_config else ""
    display_uid = curr_config[1] if curr_config else ""
    display_keywords = curr_config[2] if curr_config else ""

    with st.form("push_form_cfg"):
        st.markdown("### 🛠️ 憑證連線設定")
        token_input = st.text_input(
            "Channel Access Token", 
            value=display_token, 
            type="password", 
            key="line_tok_input",
            help="請填入 LINE Developers 後台，該官方帳號的 Messaging API 頁籤中的 Channel access token"
        )
        
        uid_input = st.text_input(
            "接收者 User ID (Your user ID)", 
            value=display_uid, 
            type="password", 
            key="line_uid_input",
            help="請填入您個人在 LINE Developers 後台看到的 Your user ID（注意：此非一般聊天用的 LINE ID）"
        )
        
        st.markdown("### 🔍 預警關鍵字設定")
        kw_input = st.text_area(
            "追蹤關鍵字 (請以半形英文逗號隔開)", 
            value=display_keywords, 
            key="line_kw_input",
            placeholder="例如：台積電,晶片,戰爭,降息"
        )
        
        if st.form_submit_button("儲存並開啟推播", use_container_width=True):
            if not token_input.strip() or not uid_input.strip():
                st.error("❌ 儲存失敗！Channel Access Token 與 接收者 User ID 皆不能為空！")
            else:
                processed_keywords = kw_input.replace("，", ",")
                with get_db_connection() as conn:
                    conn.execute(
                        "INSERT OR REPLACE INTO push_settings (id, line_token, user_id, keywords) VALUES (1, ?, ?, ?)",
                        (token_input.strip(), uid_input.strip(), processed_keywords)
                    )
                    conn.commit()
                st.success("🎉 LINE 官方帳號智慧推播設定更新成功！下一輪抓取新聞時將自動比對關鍵字。")

# G. 動態分類專屬時間軸
elif current.startswith("🔖 "):
    target_tag = current.replace("🔖 ", "")
    st.title(f"🔖 分類專屬獨立時間軸：{target_tag}")
    tag_df = query_category_data(target_tag)
    if tag_df.empty:
        st.info(f"目前尚無 【{target_tag}】 的相關新聞。")
    else:
        render_native_news_cards(tag_df)
