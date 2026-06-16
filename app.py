import streamlit as st
import feedparser
from deep_translator import GoogleTranslator
from textblob import TextBlob
import sqlite3
import pandas as pd
import requests
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
st.set_page_config(page_title="全球新聞智慧监控中心", layout="wide")

# 更換資料庫名稱（v12），徹底刷洗掉舊資料
DB_NAME = 'news_monitor_v12.db'

NEWS_SOURCES = [
    {"name": "BBC World", "url": "https://feeds.bbci.co.uk/news/world/rss.xml"},
    {"name": "CNN International", "url": "http://rss.cnn.com/rss/edition.rss"},
    {"name": "Reuters News", "url": "https://qz.com/rss"},
    {"name": "AP Top News", "url": "https://bits.blogs.nytimes.com/feed/"},
    {"name": "UDN 聯合國際", "url": "https://udn.com/rssnews/news/1013/7225?ch=udnnews"}
]

# 嚴格擴充：每類別達 50 個以上高頻中英文關鍵字
DEFAULT_CATEGORIES = {
    "軍事政治": [
        "military", "war", "russia", "israel", "defense", "election", "ukraine", "conflict", "sanctions", "die", 
        "arrest", "retrial", "airstrike", "biden", "combat", "tactic", "ally", "ceasefire", "invasion", "refugee",
        "pentagon", "nato", "kremlin", "gaza", "hamas", "missile", "weapon", "army", "navy", "troops",
        "protest", "parliament", "diplomat", "treaty", "minister", "president", "bureaucracy", "regime", "coup", "rebel",
        "戰爭", "選舉", "軍事", "政治", "衝突", "烏克蘭", "俄羅斯", "以色列", "國防", "制裁", 
        "空襲", "停火", "入侵", "難民", "五角大廈", "北約", "加薩", "哈瑪斯", "飛彈", "武器", 
        "陸軍", "海軍", "空軍", "抗議", "國會", "外交", "條約", "總理", "總統", "政權", "政變", "叛軍"
    ],
    "經濟": [
        "economy", "inflation", "gdp", "fed", "rate", "finance", "trade", "tariff", "recession", "currency",
        "stock", "market", "nasdaq", "dow", "bitcoin", "crypto", "deficit", "subsidy", "export", "import",
        "merger", "acquisition", "bankruptcy", "revenue", "profit", "fiscal", "imf", "banking", "bond", "commodity",
        "降息", "通膨", "股市", "經濟", "財經", "貿易", "關稅", "衰退", "貨幣", "匯率", 
        "納斯達克", "道瓊", "比特幣", "加密貨幣", "赤字", "補貼", "出口", "進口", "併購", "破產", 
        "營收", "利潤", "財政", "國際貨幣基金", "銀行", "債券", "大宗商品", "升息", "微觀經濟", "宏觀經濟"
    ],
    "科技": [
        "tech", "semiconductor", "apple", "google", "gpu", "tsmc", "nvidia", "nasa", "ai", "intelligence",
        "chip", "microsoft", "amazon", "openai", "chatgpt", "software", "hardware", "quantum", "cyber", "security",
        "hacker", "robot", "automation", "cloud", "telecom", "5g", "smartphone", "battery", "ev", "tesla",
        "space", "satellite", "rocket", "algorithm", "database", "innovation", "patent", "metaverse", "biotech", "startup",
        "晶片", "科技", "人工智慧", "輝達", "航太", "半導體", "蘋果", "谷歌", "微軟", "亞馬遜", 
        "網頁", "軟體", "硬體", "量子", "網路安全", "駭客", "機器人", "自動化", "雲端", "電信", 
        "智慧型手機", "電池", "電動車", "特斯拉", "太空", "衛星", "火箭", "演算法", "資料庫", "創新", 
        "專利", "元宇宙", "生物科技", "新創", "台積電", "聯發科", "鴻海", "網際網路"
    ],
    "體育": [
        "sport", "nba", "fifa", "olympics", "football", "tennis", "rookie", "mvp", "veteran", "blowout", 
        "comeback", "upside", "momentum", "athletics", "blank", "edge", "basketball", "soccer", "baseball", "stadium",
        "coach", "championship", "tournament", "trophy", "medal", "f1", "racing", "marathon", "fitness", "athlete",
        "score", "league", "wimbledon", "superbowl", "golf", "badminton", "volleyball", "gymnastics", "swim", "player",
        "運動", "籃球", "奧運", "體育", "足球", "棒球", "體育場", "教練", "總冠軍", "錦標賽", 
        "獎盃", "獎牌", "賽車", "馬拉松", "健身", "運動員", "得分", "聯賽", "溫網", "超級盃", 
        "高爾夫", "羽球", "排球", "體操", "游泳", "球員", "逆轉", "季後賽", "選秀", "自由球員"
    ],
    "民生健康": [
        "health", "virus", "climate", "food", "medicine", "symptoms", "chronic", "acute", "diagnosis", "side effects", 
        "immunity", "metabolism", "nutrient", "diet", "sedentary", "cancer", "flu", "hypertension", "diabetes", "vaccine",
        "hospital", "doctor", "therapy", "outbreak", "pandemic", "healthcare", "agriculture", "livestock", "weather", "storm",
        "flood", "drought", "warming", "carbon", "emission", "pollution", "ecology", "famine", "water", "nutrition",
        "病毒", "氣候", "醫療", "健康", "民生", "症狀", "慢性", "急性", "診斷", "副作用", 
        "免疫", "代謝", "營養", "飲食", "久坐", "癌症", "流感", "高血壓", "糖尿病", "疫苗", 
        "醫院", "醫生", "治療", "爆發", "大流行", "農業", "畜牧", "天氣", "暴風雨", "洪水", 
        "乾旱", "暖化", "碳排放", "污染", "生態", "飢荒", "水資源", "卡路里", "肥胖", "心理健康"
    ]
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
    # 主要國家
    "美國": [37.0902, -95.7129], "中國": [35.8617, 104.1954], "英國": [55.3781, -3.4360],
    "台灣": [23.6978, 120.9605], "烏克蘭": [48.3794, 31.1656], "中東": [32.4279, 53.6880],
    "日本": [36.2048, 138.2529], "歐洲": [48.6909, 9.1406], "南韓": [35.9078, 127.7669],
    "加拿大": [56.1304, -106.3468], "澳洲": [-25.2744, 133.7751], "印度": [20.5937, 78.9629],
    "德國": [51.1657, 10.4515], "法國": [46.2276, 2.2137], "新加坡": [1.3521, 103.8198],
    "俄羅斯": [61.5240, 105.3188], "以色列": [31.0461, 34.8516], "巴西": [-14.2350, -51.9253],
    "南非": [-30.5595, 22.9375], "菲律賓": [12.8797, 121.7740], "越南": [14.0583, 108.2772],
    "泰國": [15.8700, 100.9925], "馬來西亞": [4.2105, 101.9758], "印尼": [-0.7893, 113.9213],
    "義大利": [41.8719, 12.5674], "西班牙": [40.4637, -3.7492], "墨西哥": [23.6345, -102.5528],
    "沙烏地阿拉伯": [23.8859, 45.0792], "瑞士": [46.8182, 8.2275], "荷蘭": [52.1326, 5.2913],
    
    # 50 大國際城市核心座標
    "紐約": [40.7128, -74.0060], "洛杉磯": [34.0522, -118.2437], "舊金山": [37.7749, -122.4194],
    "華盛頓": [38.9072, -77.0369], "芝加哥": [41.8781, -87.6298], "西雅圖": [47.6062, -122.3321],
    "波士頓": [42.3601, -71.0589], "休士頓": [29.7604, -95.3698], "倫敦": [51.5074, -0.1278],
    "巴黎": [48.8566, 2.3522], "柏林": [52.5200, 13.4050], "法蘭克福": [50.1109, 8.6821],
    "東京": [35.6762, 139.6503], "大阪": [34.6937, 135.5022], "首爾": [37.5665, 126.9780],
    "北京": [39.9042, 116.4074], "上海": [31.2304, 121.4737], "深圳": [22.5431, 114.0579],
    "香港": [22.3193, 114.1694], "台北": [25.0330, 121.5654], "新竹": [24.8138, 120.9675],
    "新加坡市": [1.3521, 103.8198], "雪梨": [-33.8688, 151.2093], "墨爾本": [-37.8136, 144.9631],
    "新德里": [28.6139, 77.2090], "孟買": [19.0760, 72.8777], "杜拜": [25.2048, 55.2708],
    "曼谷": [13.7563, 100.5018], "馬尼拉": [14.5995, 120.9842], "雅加達": [-6.2088, 106.8456],
    "吉隆坡": [3.1390, 101.6869], "胡志明市": [10.8231, 106.6297], "多倫多": [43.6532, -79.3832],
    "溫哥戶": [49.2827, -123.1207], "羅馬": [41.9028, 12.4964], "馬德里": [40.4168, -3.7038],
    "莫斯科": [55.7558, 37.6173], "基輔": [50.4501, 30.5234], "開羅": [30.0444, 31.2357],
    "伊斯坦堡": [41.0082, 28.9784], "利雅德": [24.7136, 46.6753], "耶路撒冷": [31.7683, 35.2137],
    "斯德哥爾摩": [59.3293, 18.0686], "哥本哈根": [55.6761, 12.5683], "蘇黎世": [47.3769, 8.5417],
    "布魯塞爾": [50.8503, 4.3517], "維也納": [48.2082, 16.3738], "雅典": [37.9838, 23.7275],
    "聖保羅": [-23.5505, -46.6333], "布宜諾斯艾利斯": [-34.6037, -58.3816], "墨西哥城": [19.4326, -99.1332]
}

# --- 2. 純關鍵字分類器 (完全移除了 AI 模型以實現秒級分類) ---
def hybrid_news_classifier(title_zh, title_en):
    match_text = (title_en + " " + title_zh).lower()
    
    # 統計每個分類的關鍵字命中次數
    scores = {k: 0 for k in DEFAULT_CATEGORIES.keys()}
    for cat, keywords in DEFAULT_CATEGORIES.items():
        for word in keywords:
            if word.lower() in match_text:
                scores[cat] += match_text.count(word.lower())

    max_keyword_cat = max(scores, key=scores.get)
    max_keyword_score = scores[max_keyword_cat]

    # 有命中任一關鍵字則直接分配該分類，無任何命中則無條件歸入「一般國際」
    if max_keyword_score > 0:
        return max_keyword_cat
    
    return "一般國際"

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
                     (id INTEGER PRIMARY KEY, line_token TEXT, keywords TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS sent_notifications
                     (link TEXT PRIMARY KEY)''')
        c.execute("CREATE INDEX IF NOT EXISTS idx_time ON monitor_logs(time DESC)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_category ON monitor_logs(category)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_link ON monitor_logs(link)")
        conn.commit()

def send_line_messaging_api(channel_access_token, user_id, message_text):
    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {channel_access_token}"
    }
    payload = {"to": user_id, "messages": [{"type": "text", "text": message_text}]}
    try:
        response = requests.post(url, json=payload, headers=headers)
        return response.status_code == 200
    except Exception:
        return False

# --- 4. 精確地理關鍵字過濾定位系統 ---
def _detect_country(t_lower, z_lower):
    target = None
    
    if "nvidia" in t_lower or "輝達" in z_lower or "nasa" in t_lower or "apple" in t_lower or "google" in t_lower or "openai" in t_lower or "microsoft" in t_lower or re.search(r'\bfed\b', t_lower) or "聯準會" in z_lower or "wall street" in t_lower or "華爾街" in z_lower:
        target = "美國"
    elif "tsmc" in t_lower or "台積電" in z_lower or "聯發科" in z_lower or "foxconn" in t_lower or "鴻海" in z_lower:
        target = "台灣"
    elif "samsung" in t_lower or "三星" in z_lower or "hyundai" in t_lower:
        target = "南韓"
    elif "asml" in t_lower or "艾司摩爾" in z_lower:
        target = "荷蘭"
    elif "toyota" in t_lower or "豐田" in z_lower or "sony" in t_lower or "索尼" in z_lower:
        target = "日本"
    elif "華為" in z_lower or "huawei" in t_lower or "byd" in t_lower or "比亞迪" in z_lower or "tencent" in t_lower or "騰訊" in z_lower or "alibaba" in t_lower or "阿里巴巴" in z_lower:
        target = "中國"
        
    elif "new york" in t_lower or "紐約" in z_lower: target = "紐約"
    elif "los angeles" in t_lower or "洛杉磯" in z_lower: target = "洛杉磯"
    elif "san francisco" in t_lower or "舊金山" in z_lower: target = "舊金山"
    elif "washington" in t_lower or "華盛頓" in z_lower: target = "華盛頓"
    elif "chicago" in t_lower or "芝加哥" in z_lower: target = "芝加哥"
    elif "seattle" in t_lower or "西雅圖" in z_lower: target = "西雅圖"
    elif "boston" in t_lower or "波士頓" in z_lower: target = "波士頓"
    elif "houston" in t_lower or "休士頓" in z_lower: target = "休士頓"
    elif "london" in t_lower or "倫敦" in z_lower: target = "倫敦"
    elif "paris" in t_lower or "巴黎" in z_lower: target = "巴黎"
    elif "berlin" in t_lower or "柏林" in z_lower: target = "柏林"
    elif "frankfurt" in t_lower or "法蘭克福" in z_lower: target = "法蘭克福"
    elif "tokyo" in t_lower or "東京" in z_lower: target = "東京"
    elif "osaka" in t_lower or "大阪" in z_lower: target = "大阪"
    elif "seoul" in t_lower or "首爾" in z_lower: target = "首爾"
    elif "beijing" in t_lower or "北京" in z_lower: target = "北京"
    elif "shanghai" in t_lower or "上海" in z_lower: target = "上海"
    elif "shenzhen" in t_lower or "深圳" in z_lower: target = "深圳"
    elif "hong kong" in t_lower or "香港" in z_lower: target = "香港"
    elif "taipei" in t_lower or "台北" in z_lower: target = "台北"
    elif "hsinchu" in t_lower or "新竹" in z_lower: target = "新竹"
    elif "sydney" in t_lower or "雪梨" in z_lower: target = "雪梨"
    elif "melbourne" in t_lower or "墨爾本" in z_lower: target = "墨爾本"
    elif "new delhi" in t_lower or "新德里" in z_lower: target = "新德里"
    elif "mumbai" in t_lower or "孟買" in z_lower: target = "孟買"
    elif "dubai" in t_lower or "杜拜" in z_lower: target = "杜拜"
    elif "bangkok" in t_lower or "曼谷" in z_lower: target = "曼谷"
    elif "manila" in t_lower or "馬尼拉" in z_lower: target = "馬尼拉"
    elif "jakarta" in t_lower or "雅加達" in z_lower: target = "雅加達"
    elif "kuala lumpur" in t_lower or "吉隆坡" in z_lower: target = "吉隆坡"
    elif "ho chi minh" in t_lower or "胡志明" in z_lower: target = "胡志明市"
    elif "toronto" in t_lower or "多倫多" in z_lower: target = "多倫多"
    elif "vancouver" in t_lower or "溫哥華" in z_lower: target = "溫哥華"
    elif "rome" in t_lower or "羅馬" in z_lower: target = "羅馬"
    elif "madrid" in t_lower or "馬德里" in z_lower: target = "馬德里"
    elif "moscow" in t_lower or "莫斯科" in z_lower: target = "莫斯科"
    elif "kyiv" in t_lower or "基輔" in z_lower: target = "基輔"
    elif "cairo" in t_lower or "開羅" in z_lower: target = "開羅"
    elif "istanbul" in t_lower or "伊斯坦堡" in z_lower: target = "伊斯坦堡"
    elif "riyadh" in t_lower or "利雅德" in z_lower: target = "利雅德"
    elif "jerusalem" in t_lower or "耶路撒冷" in z_lower: target = "耶路撒冷"
    elif "stockholm" in t_lower or "斯德哥爾摩" in z_lower: target = "斯德哥爾摩"
    elif "copenhagen" in t_lower or "哥本哈根" in z_lower: target = "哥本哈根"
    elif "zurich" in t_lower or "蘇黎世" in z_lower: target = "蘇黎世"
    elif "brussels" in t_lower or "布魯塞爾" in z_lower: target = "布魯塞爾"
    elif "vienna" in t_lower or "維也納" in z_lower: target = "維也納"
    elif "athens" in t_lower or "雅典" in z_lower: target = "雅典"
    elif "sao paulo" in t_lower or "聖保羅" in z_lower: target = "聖保羅"
    elif "buenos aires" in t_lower or "布宜諾斯艾利斯" in z_lower: target = "布宜諾斯艾利斯"
    elif "mexico city" in t_lower or "墨西哥城" in z_lower: target = "墨西哥城"

    elif "台灣" in z_lower or re.search(r'\btaiwan\b', t_lower): target = "台灣"
    elif "美國" in z_lower or "白宮" in z_lower or re.search(r'\bamerica\b|\bwhite\s+house\b|\busa\b|\bunited\s+states\b', t_lower): target = "美國"
    elif "烏克蘭" in z_lower or re.search(r'\bukraine\b', t_lower): target = "烏克蘭"
    elif "中國" in z_lower or re.search(r'\bchina\b', t_lower): target = "中國"
    elif "英國" in z_lower or re.search(r'\buk\b|\bbritain\b|\bunited\s+kingdom\b', t_lower): target = "英國"
    elif "日本" in z_lower or re.search(r'\bjapan\b', t_lower): target = "日本"
    elif "南韓" in z_lower or "韓國" in z_lower or re.search(r'\bkorea\b', t_lower): target = "南韓"
    elif "加拿大" in z_lower or re.search(r'\bcanada\b', t_lower): target = "加拿大"
    elif "澳洲" in z_lower or re.search(r'\baustralia\b', t_lower): target = "澳洲"
    elif "印度" in z_lower or re.search(r'\bindia\b', t_lower): target = "印度"
    elif "德國" in z_lower or re.search(r'\bgermany\b', t_lower): target = "德國"
    elif "法國" in z_lower or re.search(r'\bfrance\b', t_lower): target = "法國"
    elif "俄羅斯" in z_lower or re.search(r'\brussia\b', t_lower): target = "俄羅斯"
    elif "新加坡" in z_lower or re.search(r'\bsingapore\b', t_lower): target = "新加坡"
    elif "中東" in z_lower or "加薩" in z_lower or re.search(r'\bgaza\b', t_lower): target = "中東"
    elif "以色列" in z_lower or re.search(r'\bisrael\b', t_lower): target = "以色列"
    elif "巴西" in z_lower or re.search(r'\bbrazil\b', t_lower): target = "巴西"
    elif "南非" in z_lower or re.search(r'\bsouth\s+africa\b', t_lower): target = "南非"
    elif "菲律賓" in z_lower or re.search(r'\bphilippines\b', t_lower): target = "菲律賓"
    elif "越南" in z_lower or re.search(r'\bvietnam\b', t_lower): target = "越南"
    elif "泰國" in z_lower or re.search(r'\bthailand\b', t_lower): target = "泰國"
    elif "馬來西亞" in z_lower or re.search(r'\bmalaysia\b', t_lower): target = "馬來西亞"
    elif "印尼" in z_lower or re.search(r'\bindonesia\b', t_lower): target = "印尼"
    elif "義大利" in z_lower or re.search(r'\bitaly\b', t_lower): target = "義大利"
    elif "西班牙" in z_lower or re.search(r'\bspain\b', t_lower): target = "西班牙"
    elif "墨西哥" in z_lower or re.search(r'\bmexico\b', t_lower): target = "墨西哥"
    elif "沙烏地" in z_lower or re.search(r'\bsaudi\b', t_lower): target = "沙烏地阿拉伯"
    elif "瑞士" in z_lower or re.search(r'\bswitzerland\b', t_lower): target = "瑞士"
    elif "荷蘭" in z_lower or re.search(r'\bnetherlands\b', t_lower): target = "荷蘭"
    elif "歐洲" in z_lower or re.search(r'\beurope\b', t_lower): target = "歐洲"

    if target is None:
        return None, None, None

    base_lat, base_lon = COUNTRY_COORDS[target]
    offset = 0.4
    rand_lat = base_lat + random.uniform(-offset, offset)
    rand_lon = base_lon + random.uniform(-offset, offset)
    return target, rand_lat, rand_lon

def _fetch_source_raw(src):
    results = []
    try:
        feed = feedparser.parse(src["url"], request_headers={"User-Agent": "Mozilla/5.0 (compatible; NewsBot/1.0)"})
        for entry in feed.entries[:12]:
            title_raw = getattr(entry, 'title', '').strip()
            link_raw = getattr(entry, 'link', '').strip()
            if not title_raw or not link_raw: continue
            
            t_lower = title_raw.lower()
            if "error 500" in t_lower or "server error" in t_lower or "internal server error" in t_lower: 
                continue
                
            results.append((title_raw, link_raw, src["name"]))
    except Exception:
        pass  # 👈 檢查這裡！上一個函式的 except 不能漏掉或縮排錯誤
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
                try:
                    translations[orig] = translator.translate(orig)
                except Exception:
                    translations[orig] = orig
    return translations
def fetch_all_news():
    all_raw = []
    with ThreadPoolExecutor(max_workers=len(NEWS_SOURCES)) as executor:
        futures = [executor.submit(_fetch_source_raw, src) for src in NEWS_SOURCES]
        for future in as_completed(futures):
            all_raw.extend(future.result())

    if not all_raw: return

    with get_db_connection() as conn:
        existing_links = set(row[0] for row in conn.execute("SELECT link FROM monitor_logs").fetchall())

    new_entries = [(t, l, s) for t, l, s in all_raw if l not in existing_links]
    
    if new_entries:
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
            config = conn.execute("SELECT line_token, keywords FROM push_settings WHERE id=1").fetchone()
            if config and config[0]:
                saved_credentials = config[0].split("|||")
                if len(saved_credentials) == 2:
                    channel_access_token = saved_credentials[0].strip()
                    my_user_id = saved_credentials[1].strip()
                    keywords = [kw.strip().lower() for kw in config[1].split(",") if kw.strip()]
                    if keywords:
                        recent_news = conn.execute("SELECT title_zh, source, link FROM monitor_logs ORDER BY time DESC LIMIT 10").fetchall()
                        for title_zh, source_name, link_raw in recent_news:
                            already_sent = conn.execute("SELECT 1 FROM sent_notifications WHERE link = ?", (link_raw,)).fetchone()
                            if not already_sent and any(kw in title_zh.lower() for kw in keywords):
                                msg = f"\n🔔 【新聞預警】\n📰 標題: {title_zh}\n📡 來源: {source_name}\n🔗 連結: {link_raw}"
                                success = send_line_messaging_api(channel_access_token, my_user_id, msg)
                                if success:
                                    conn.execute("INSERT OR IGNORE INTO sent_notifications (link) VALUES (?)", (link_raw,))
                                    conn.commit()
    except Exception:
        pass

# --- 5. 背景排程 ---
@st.cache_resource
def start_scheduler():
    scheduler = BackgroundScheduler(timezone="Asia/Taipei")
    scheduler.add_job(fetch_all_news, 'interval', minutes=5, id='news_fetch', max_instances=1, coalesce=True)
    scheduler.start()
    return scheduler

# --- 6. 資料庫查詢函數 ---
@st.cache_data(ttl=60)
def query_all_data():
    with get_db_connection() as conn:
        df = pd.read_sql_query("SELECT * FROM monitor_logs ORDER BY time DESC", conn)
    if not df.empty: df['time_dt'] = pd.to_datetime(df['time'])
    return df

@st.cache_data(ttl=30)
def query_recent_hour_data():
    one_hour_ago = (datetime.now() - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
    with get_db_connection() as conn:
        df = pd.read_sql_query("SELECT * FROM monitor_logs WHERE time >= ? ORDER BY time DESC", conn, params=(one_hour_ago,))
    if not df.empty: df['time_dt'] = pd.to_datetime(df['time'])
    return df

@st.cache_data(ttl=60)
def query_category_data(category_name):
    with get_db_connection() as conn:
        df = pd.read_sql_query("SELECT * FROM monitor_logs WHERE category = ? ORDER BY time DESC", conn, params=(category_name,))
    if not df.empty: df['time_dt'] = pd.to_datetime(df['time'])
    return df

def get_user_tags(username):
    if st.session_state.get('is_guest') and 'guest_tags' in st.session_state: return st.session_state['guest_tags']
    with get_db_connection() as conn:
        res = conn.execute("SELECT tags FROM user_tags WHERE username=?", (username,)).fetchone()
    return res[0].split(",") if res and res[0] else list(DEFAULT_CATEGORIES.keys()) + ["一般國際"]

def save_user_tags(username, tags):
    with get_db_connection() as conn:
        conn.execute("INSERT OR REPLACE INTO user_tags (username, tags) VALUES (?, ?)", (username, ",".join(tags)))
        conn.commit()

# --- 7. 初始化 ---
init_db()
if 'monitor_started' not in st.session_state:
    start_scheduler()
    threading.Thread(target=fetch_all_news, daemon=True).start()
    st.session_state['monitor_started'] = True

# --- 8. Session State 初始化 ---
if 'logged_in' not in st.session_state: st.session_state['logged_in'] = False
if 'username' not in st.session_state: st.session_state['username'] = ""
if 'is_guest' not in st.session_state: st.session_state['is_guest'] = False
if 'current_view' not in st.session_state: st.session_state['current_view'] = "🏠 首頁總覽"

# --- 9. 登入管制牆 ---
if not st.session_state['logged_in'] and not st.session_state['is_guest']:
    st.title("全球新聞智能監控系統")
    col1, col2 = st.columns(2)
    with col1:
        with st.container(border=True):
            st.markdown("### 🔑 會員/自訂用戶登入")
            username_input = st.text_input("使用者名稱", placeholder="請輸入使用者名稱", key="login_user")
            st.text_input("密碼", type="password", placeholder="******", key="login_pwd")
            if st.button("進入會員系統", use_container_width=True, key="btn_member_login"):
                if username_input.strip():
                    st.session_state['logged_in'] = True
                    st.session_state['username'] = username_input.strip()
                    st.session_state['current_view'] = "🏠 首頁總覽"
                    st.rerun()
    with col2:
        with st.container(border=True):
            st.markdown("### 🌐 訪客快捷通道")
            if st.button("🚀 以訪客身份免登入進入", use_container_width=True, type="primary", key="btn_guest_login"):
                st.session_state['is_guest'] = True
                st.session_state['username'] = "訪客模式 Guest"
                st.session_state['guest_tags'] = list(DEFAULT_CATEGORIES.keys()) + ["一般國際"]
                st.session_state['current_view'] = "🏠 首頁總覽"
                st.rerun()
    st.stop()

# --- 10. 側邊欄 ---
st.sidebar.title(f"👤 {st.session_state['username']}")
if st.sidebar.button("🔄 手動同步最新新聞", key="side_sync_btn"):
    with st.spinner("正在重新爬取各國新聞..."): fetch_all_news()
    st.cache_data.clear()
    st.rerun()

st.sidebar.write("---")
all_available_tags = list(DEFAULT_CATEGORIES.keys()) + ["一般國際"]
saved_tags = get_user_tags(st.session_state['username'])

selected_tags = []
for tag in all_available_tags:
    if st.sidebar.checkbox(f"🔖 {tag}", value=tag in saved_tags, key=f"sidebar_fixed_cb_{tag}"):
        selected_tags.append(tag)

if st.sidebar.button("💾 儲存我的勾選設定", key="side_save_btn") and not st.session_state['is_guest']:
    save_user_tags(st.session_state['username'], selected_tags)
    st.sidebar.success("訂閱設定已同步！")
    st.rerun()

if st.sidebar.button("🚪 登出/切換模式", key="side_logout_btn"):
    st.session_state['logged_in'] = False
    st.session_state['is_guest'] = False
    st.session_state['current_view'] = "🏠 首頁總覽"
    st.rerun()

# --- 11. 導覽列 ---
st.write("### 🧭 系統主功能面板")
base_menu = ["🏠 首頁總覽", "🎬 影片專區", "⏳ 歷史總時間軸", "📊 數據統計分析", "🔍 關鍵字搜尋"]
if not st.session_state['is_guest']: base_menu.append("📢 LINE通知設定")

cols_row1 = st.columns(len(base_menu))
for idx, item_name in enumerate(base_menu):
    if cols_row1[idx].button(item_name, use_container_width=True, key=f"nav_row1_{idx}", type="primary" if st.session_state['current_view'] == item_name else "secondary"):
        st.session_state['current_view'] = item_name
        st.rerun()

category_menu = [f"🔖 {t}" for t in selected_tags]
if category_menu:
    st.write("### 🔖 訂閱新聞分類頻道")
    cols_row2 = st.columns(len(category_menu))
    for idx, item_name in enumerate(category_menu):
        if cols_row2[idx].button(item_name, use_container_width=True, key=f"nav_row2_{idx}", type="primary" if st.session_state['current_view'] == item_name else "secondary"):
            st.session_state['current_view'] = item_name
            st.rerun()

st.write("---")

# --- 12. 新聞卡片元件 ---
def render_native_news_cards(df_target):
    if df_target is None or df_target.empty:
        st.info("💡 目前暫無新聞條目。(後台正在同步中，請數秒後刷新頁面)")
        return

    core_categories = ["軍事政治", "經濟", "科技", "體育", "民生健康", "一般國際"]
    nav_options = ["請選擇要移動至的分頁..."] + [f"🔖 {c}" for c in core_categories]

    for i, (_, row) in enumerate(df_target.iterrows()):
        cat = row['category']
        news_id = row['id']
        theme = CATEGORY_THEMES.get(cat, CATEGORY_THEMES["一般國際"])
        sentiment_text = "正面" if row['sentiment'] > 0.05 else ("負面" if row['sentiment'] < -0.05 else "中性")
        display_country = row['country'] if row['country'] else "未辨識出精確地點"

        with st.container(border=True):
            col_meta, col_title, col_btn = st.columns([2.5, 7.0, 2.5])
            with col_meta:
                st.markdown(f"**{theme['emoji']} {theme['label']}**")
                st.caption(f"📡 來源: `{row['source']}`")
            with col_title:
                st.markdown(f"#### {row['title_zh']}")
                st.markdown(f"⏱️ `發布時間: {row['time']}` &nbsp;|&nbsp; 📍 區域: **{display_country}** &nbsp;|&nbsp; 📊 輿情: `{sentiment_text}`")
            with col_btn:
                st.link_button("🔗 前往原文", row['link'], use_container_width=True, key=f"lnk_{i}_{news_id}")
                st.write("")
                selected_nav = st.selectbox("移動至 👇", options=nav_options, index=0, key=f"move_sel_{i}_{news_id}", label_visibility="collapsed")
                if selected_nav != "請選擇要移動至的分頁...":
                    with get_db_connection() as conn:
                        conn.execute("UPDATE monitor_logs SET category = ? WHERE id = ?", (selected_nav.replace("🔖 ", ""), news_id))
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
        df_map_ready = df_recent.dropna(subset=['country', 'lat', 'lon'])
        df_map_ready = df_map_ready[df_map_ready['country'] != 'None']
        
        m = folium.Map(location=[25.0, 15.0], zoom_start=2, tiles="OpenStreetMap")

        for _, row in df_map_ready.iterrows():
            cat = row['category']
            theme = CATEGORY_THEMES.get(cat, CATEGORY_THEMES["一般國際"])
            color = theme.get("color", "gray")

            popup_html = f"""
            <div style='font-family: sans-serif; min-width: 200px;'>
                <h4>{theme['emoji']} {row['category']}</h4>
                <p><b>{row['title_zh']}</b></p>
                <small>📡 來源: {row['source']}<br>📍 定位點: {row['country']}<br>⏱️ 時間: {row['time']}</small><br><br>
                <a href='{row['link']}' target='_blank' style='display:inline-block; padding:5px 10px; background-color:#ff4b4b; color:white; text-decoration:none; border-radius:4px;'>前往原文</a>
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

        st_folium(m, width="100%", height=600, key="main_live_map_folium_v12")
        st.write("---")
        st.write("### 🔔 焦點對應：最近 1 小時內發布的新聞條目")
        render_native_news_cards(df_recent)

# B. 影片專區
elif current == "🎬 影片專區":
    st.title("🎬 即時新聞影音連結專區")
    
    # 從資料庫中讀取最新新聞
    df_all = query_all_data()
    
    if df_all.empty:
        st.info("💡 目前暫無新聞資料。")
    else:
        # 取出最新的 10 則新聞，純呈現連結
        video_news = df_all.head(10)
        
        for idx, row in video_news.iterrows():
            with st.container(border=True):
                # 建立左邊文字、右邊按鈕的乾淨排版
                col_txt, col_lnk = st.columns([8, 2])
                with col_txt:
                    st.markdown(f"📌 **{row['title_zh']}**")
                    st.caption(f"📡 來源: `{row['source']}` | ⏱️ 時間: {row['time']}")
                with col_lnk:
                    # 只提供點擊跳轉的連結按鈕，不載入任何影片畫面
                    st.link_button("🌐 開啟影片連結", row['link'], use_container_width=True, key=f"video_link_{idx}")                           
# C. 歷史總時間軸
elif current == "⏳ 歷史總時間軸":
    st.title("⏳ 全球歷史即時總時間軸")
    render_native_news_cards(query_all_data())

# D. 數據統計分析
elif current == "📊 數據統計分析":
    st.title("📊 全球新聞數據統計分析")
    df_all = query_all_data()
    if df_all.empty: st.warning("資料庫內暫無數據可供分析。")
    else:
        col_f1, col_f2 = st.columns([1, 1])
        with col_f1:
            category_counts = df_all['category'].value_counts().reset_index()
            category_counts.columns = ['category', 'count']
            st.plotly_chart(px.pie(category_counts, names='category', values='count', title="各類別發布比例", hole=0.4), use_container_width=True, key="stat_pie_chart")
        with col_f2:
            df_trend = df_all.copy()
            df_trend['time_group'] = df_trend['time_dt'].dt.floor('10min').dt.strftime("%Y-%m-%d %H:%M")
            time_trend = df_trend.groupby(['time_group', 'category']).size().reset_index(name='新聞數量')
            st.plotly_chart(px.line(time_trend.sort_values(by='time_group'), x="time_group", y="新聞數量", color="category", title="趨勢走勢線", markers=True), use_container_width=True, key="stat_line_chart")

# E. 關鍵字搜尋
elif current == "🔍 關鍵字搜尋":
    st.title("🔍 全域新聞關鍵字檢索")
    search_query = st.text_input("輸入要查詢的關鍵字：", placeholder="例如：台積電、晶片", key="search_box_input")
    df_all = query_all_data()
    if search_query and not df_all.empty:
        render_native_news_cards(df_all[df_all['title_zh'].str.contains(search_query, na=False, case=False)])

# F. LINE 通知設定頁面
elif current == "📢 LINE通知設定":
    st.title("📢 LINE 官方帳號智慧預警推送")
    with get_db_connection() as conn: curr_config = conn.execute("SELECT line_token, keywords FROM push_settings WHERE id=1").fetchone()
    display_token, display_userid = "", ""
    if curr_config and curr_config[0] and "|||" in curr_config[0]: display_token, display_userid = curr_config[0].split("|||")
    with st.form("push_form_cfg"):
        token_input = st.text_input("1. Channel Access Token", value=display_token, type="password", key="line_tok_input")
        userid_input = st.text_input("2. Your User ID", value=display_userid, key="line_uid_input")
        kw_input = st.text_area("3. 追蹤關鍵字", value=curr_config[1] if curr_config else "", key="line_kw_input")
        if st.form_submit_button("儲存並開啟智慧推播"):
            if token_input.strip() and userid_input.strip():
                with get_db_connection() as conn:
                    conn.execute("INSERT OR REPLACE INTO push_settings (id, line_token, keywords) VALUES (1, ?, ?)", (f"{token_input.strip()}|||{userid_input.strip()}", kw_input.replace("，", ",")))
                    conn.commit()
                st.success("🎉 LINE 通知設定更新成功！")

# G. 動態分類專屬時間軸
elif current.startswith("🔖 "):
    target_tag = current.replace("🔖 ", "")
    st.title(f"🔖 分類專屬獨立時間軸：{target_tag}")
    render_native_news_cards(query_category_data(target_tag))
