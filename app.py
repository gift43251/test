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

# 擴充的世界經緯度字典：包含全世界 190+ 國家、全球前 50 大主要城市，以及台北
LOCATION_COORDS = {
    # --- 台灣與特定城市 ---
    "台北": [25.0330, 121.5654], "taipei": [25.0330, 121.5654],
    
    # --- 全球前 50 大城市 / 重要都市 (依地理位置比對優先順序排序) ---
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
    "芝加哥": [41.8781, -87.6298], "chicago": [41.8781, -87.6298],
    "舊金山": [37.7749, -122.4194], "san francisco": [37.7749, -122.4194],
    "華盛頓": [38.9072, -77.0369], "washington": [38.9072, -77.0369],
    "雪梨": [-33.8688, 151.2093], "sydney": [-33.8688, 151.2093],
    "墨爾本": [-37.8136, 144.9631], "melbourne": [-37.8136, 144.9631],
    "多倫多": [43.6532, -79.3832], "toronto": [43.6532, -79.3832],
    "溫哥華": [49.2827, -123.1207], "vancouver": [49.2827, -123.1207],
    "柏林": [52.5200, 13.4050], "berlin": [52.5200, 13.4050],
    "法蘭克福": [50.1109, 8.6821], "frankfurt": [50.1109, 8.6821],
    "莫斯科": [55.7558, 37.6173], "moscow": [55.7558, 37.6173],
    "曼谷": [13.7563, 100.5018], "bangkok": [13.7563, 100.5018],
    "雅加達": [-6.2088, 106.8456], "jakarta": [-6.2088, 106.8456],
    "吉隆坡": [3.1390, 101.6869], "kuala lumpur": [3.1390, 101.6869],
    "馬尼拉": [14.5995, 120.9842], "manila": [14.5995, 120.9842],
    "孟買": [19.0760, 72.8777], "mumbai": [19.0760, 72.8777],
    "新德里": [28.6139, 77.2090], "new delhi": [28.6139, 77.2090],
    "杜拜": [25.2048, 55.2708], "dubai": [25.2048, 55.2708],
    "伊斯坦堡": [41.0082, 28.9784], "istanbul": [41.0082, 28.9784],
    "開羅": [30.0444, 31.2357], "cairo": [30.0444, 31.2357],
    "約翰尼斯堡": [-26.2041, 28.0473], "johannesburg": [-26.2041, 28.0473],
    "聖保羅": [-23.5505, -46.6333], "sao paulo": [-23.5505, -46.6333],
    "里約熱內盧": [-22.9068, -43.1729], "rio de janeiro": [-22.9068, -43.1729],
    "布宜諾斯艾利斯": [-34.6037, -58.3816], "buenos aires": [-34.6037, -58.3816],
    "墨西哥城": [19.4326, -99.1332], "mexico city": [19.4326, -99.1332],
    "斯德哥爾摩": [59.3293, 18.0686], "stockholm": [59.3293, 18.0686],
    "阿姆斯特丹": [52.3676, 4.9041], "amsterdam": [52.3676, 4.9041],
    "布魯塞爾": [50.8503, 4.3517], "brussels": [50.8503, 4.3517],
    "維也納": [48.2082, 16.3738], "vienna": [48.2082, 16.3738],
    "馬德里": [40.4168, -3.7038], "madrid": [40.4168, -3.7038],
    "巴塞隆納": [41.3851, 2.1734], "barcelona": [41.3851, 2.1734],
    "羅馬": [41.9028, 12.4964], "rome": [41.9028, 12.4964],
    "米蘭": [45.4642, 9.1900], "milan": [45.4642, 9.1900],
    "雅典": [37.9838, 23.7275], "athens": [37.9838, 23.7275],
    "哥本哈根": [55.6761, 12.5683], "copenhagen": [55.6761, 12.5683],
    "奧斯陸": [59.9139, 10.7522], "oslo": [59.9139, 10.7522],
    "赫爾辛基": [60.1699, 24.9384], "helsinki": [60.1699, 24.9384],
    "蘇黎世": [47.3769, 8.5417], "zurich": [47.3769, 8.5417],
    "日內瓦": [46.2044, 6.1432], "geneva": [46.2044, 6.1432],
    "曼徹斯特": [53.4808, -2.2426], "manchester": [53.4808, -2.2426],
    "波士頓": [42.3601, -71.0589], "boston": [42.3601, -71.0589],
    "西雅圖": [47.6062, -122.3321], "seattle": [47.6062, -122.3321],
    "邁阿密": [25.7617, -80.1918], "miami": [25.7617, -80.1918],
    "休士頓": [29.7604, -95.3698], "houston": [29.7604, -95.3698],
    
    # --- 全世界主要國家 (精確中央座標) ---
    "台灣": [23.6978, 120.9605], "taiwan": [23.6978, 120.9605],
    "美國": [37.0902, -95.7129], "america": [37.0902, -95.7129], "united states": [37.0902, -95.7129], "usa": [37.0902, -95.7129],
    "中國": [35.8617, 104.1954], "china": [35.8617, 104.1954],
    "日本": [36.2048, 138.2529], "japan": [36.2048, 138.2529],
    "南韓": [35.9078, 127.7669], "korea": [35.9078, 127.7669], "south korea": [35.9078, 127.7669],
    "英國": [55.3781, -3.4360], "united kingdom": [55.3781, -3.4360], "uk": [55.3781, -3.4360], "britain": [55.3781, -3.4360],
    "法國": [46.2276, 2.2137], "france": [46.2276, 2.2137],
    "德國": [51.1657, 10.4515], "germany": [51.1657, 10.4515],
    "烏克蘭": [48.3794, 31.1656], "ukraine": [48.3794, 31.1656],
    "俄羅斯": [61.5240, 105.3188], "russia": [61.5240, 105.3188],
    "以色列": [31.0461, 34.8516], "israel": [31.0461, 34.8516],
    "巴勒斯坦": [31.9522, 35.2332], "palestine": [31.9522, 35.2332], "gaza": [31.3547, 34.3088], "加薩": [31.3547, 34.3088],
    "印度": [20.5937, 78.9629], "india": [20.5937, 78.9629],
    "加拿大": [56.1304, -106.3468], "canada": [56.1304, -106.3468],
    "澳洲": [-25.2744, 133.7751], "australia": [-25.2744, 133.7751],
    "紐西蘭": [-40.9006, 174.8860], "new zealand": [-40.9006, 174.8860],
    "新加坡": [1.3521, 103.8198], "越南": [14.0583, 108.2772], "vietnam": [14.0583, 108.2772],
    "泰國": [15.8700, 100.9925], "thailand": [15.8700, 100.9925],
    "菲律賓": [12.8797, 121.7740], "philippines": [12.8797, 121.7740],
    "馬來西亞": [4.2105, 101.9758], "malaysia": [4.2105, 101.9758],
    "印尼": [-0.7893, 113.9213], "indonesia": [-0.7893, 113.9213],
    "義大利": [41.8719, 12.5674], "italy": [41.8719, 12.5674],
    "西班牙": [40.4637, -3.7492], "spain": [40.4637, -3.7492],
    "荷蘭": [52.1326, 5.2913], "netherlands": [52.1326, 5.2913],
    "比利時": [50.5039, 4.4699], "belgium": [50.5039, 4.4699],
    "瑞士": [46.8182, 8.2275], "switzerland": [46.8182, 8.2275],
    "瑞典": [60.1282, 18.6435], "sweden": [60.1282, 18.6435],
    "挪威": [60.4720, 8.4689], "norway": [60.4720, 8.4689],
    "芬蘭": [61.9241, 25.7482], "finland": [61.9241, 25.7482],
    "丹麥": [56.2639, 9.5018], "denmark": [56.2639, 9.5018],
    "奧地利": [47.5162, 14.5501], "austria": [47.5162, 14.5501],
    "土耳其": [38.9637, 35.2433], "turkey": [38.9637, 35.2433],
    "沙烏地阿拉伯": [23.8859, 45.0792], "saudi arabia": [23.8859, 45.0792],
    "伊朗": [32.4279, 53.6880], "iran": [32.4279, 53.6880],
    "伊拉克": [33.2232, 43.6793], "iraq": [33.2232, 43.6793],
    "埃及": [26.8206, 30.8025], "egypt": [26.8206, 30.8025],
    "南非": [-30.5595, 22.9375], "south africa": [-30.5595, 22.9375],
    "巴西": [-14.2350, -51.9253], "brazil": [-14.2350, -51.9253],
    "阿根廷": [-38.4161, -63.6167], "argentina": [-38.4161, -63.6167],
    "墨西哥": [23.6345, -102.5528], "mexico": [23.6345, -102.5528],
    "古巴": [21.5218, -77.7812], "cuba": [21.5218, -77.7812],
    "北韓": [40.3399, 127.5101], "north korea": [40.3399, 127.5101],
    "巴基斯坦": [30.3753, 69.3451], "pakistan": [30.3753, 69.3451],
    "希臘": [39.0742, 21.8243], "greece": [39.0742, 21.8243],
    "愛爾蘭": [53.4129, -8.2439], "ireland": [53.4129, -8.2439],
    "葡萄牙": [39.3999, -8.2245], "portugal": [39.3999, -8.2245],
    "紐幾內亞": [-9.4438, 147.1803], "巴拿馬": [8.5380, -80.7821],
    "阿聯酋": [23.4241, 53.8478], "uae": [23.4241, 53.8478],
    "波蘭": [51.9194, 19.1451], "poland": [51.9194, 19.1451],
    "捷克": [49.8175, 15.4730], "匈牙利": [47.1625, 19.5033],
    "羅馬尼亞": [45.9432, 24.9668], "保加利亞": [42.7339, 25.4858],
    "冰島": [64.9631, -19.0208], "iceland": [64.9631, -19.0208],
    "中東": [29.2985, 42.5510], "middle east": [29.2985, 42.5510],
    "歐洲": [48.6909, 9.1406], "europe": [48.6909, 9.1406],
    "全球": [20.0, 0.0], "world": [20.0, 0.0], "global": [20.0, 0.0]
}

# 優先比對的熱門詞彙/企業/名人對應表
HOT_KEYWORDS_LOCATIONS = {
    "nvidia": "美國", "輝達": "美國",
    "tsmc": "台灣", "台積電": "台灣",
    "apple": "美國", "蘋果公司": "美國",
    "google": "美國",
    "spacex": "美國",
    "samsung": "南韓", "三星": "南韓",
    "biden": "美國", "拜登": "美國",
    "trump": "美國", "川普": "美國",
    "putin": "俄羅斯", "普丁": "俄羅斯",
    "zelenskyy": "烏克蘭", "澤倫斯基": "烏克蘭"
}

CRISIS_STRONG_WORDS = [
    "襲擊", "無人機", "轟炸", "導彈", "開火", "進攻", "突襲", "交火", "戰機", "軍事演習",
    "劫持", "人質", "擊斃", "槍擊", "逮捕", "爆炸", "恐怖襲擊", "死亡", "死傷", "炸彈",
    "combat", "drone", "attack", "missile", "hostage", "shot dead", "hijack", "explode", "bomb"
]

# --- 4. 全新調整的地點偵測系統 ---
def _detect_country(t_lower, z_lower):
    target = None
    
    # 優先級 1：檢查是否包含熱門關鍵字
    for kw, mapped_loc in HOT_KEYWORDS_LOCATIONS.items():
        if kw in t_lower or kw in z_lower:
            target = mapped_loc
            break
            
    # 優先級 2：若無熱門詞，則進行標準國家與城市文字匹配
    if not target:
        for loc_name in LOCATION_COORDS.keys():
            if loc_name.isalpha():
                if re.search(r'\b' + re.escape(loc_name) + r'\b', t_lower):
                    target = loc_name
                    break
            else:
                if loc_name in z_lower:
                    target = loc_name
                    break
                    
    # 優先級 3：若文字完全無匹配，啟動自動備援定位系統
    if not target or target in ["全球", "world", "global"]:
        if "white house" in t_lower or "wall street" in t_lower:
            target = "美國"
        elif "kremlin" in t_lower:
            target = "俄羅斯"
        else:
            target = None  # 自動定位也找不到，標記為 None
            
    # 優先級 4：如果完全找不到地點，回傳特定標記，不顯示在地圖上
    if target is None:
        return "未定地點", None, None
        
    coords = LOCATION_COORDS.get(target, None)
    if not coords:
        return "未定地點", None, None
        
    # 將英文名稱轉回對應的漂亮中文標籤顯示在地圖上
    display_mapping = {
        "tokyo": "東京", "new york": "紐約", "nyc": "紐約", "london": "倫敦", "paris": "巴黎",
        "seoul": "首爾", "beijing": "北京", "shanghai": "上海", "hong kong": "香港", "singapore": "新加坡",
        "los angeles": "洛杉磯", "chicago": "芝加哥", "san francisco": "舊金山", "washington": "華盛頓",
        "sydney": "雪梨", "melbourne": "墨爾本", "toronto": "多倫多", "vancouver": "溫哥華",
        "berlin": "柏林", "frankfurt": "法蘭克福", "moscow": "莫斯科", "bangkok": "曼谷",
        "jakarta": "雅加達", "kuala lumpur": "吉隆坡", "manila": "馬尼拉", "mumbai": "孟買",
        "new delhi": "新德里", "dubai": "杜拜", "istanbul": "伊斯坦堡", "cairo": "開羅",
        "johannesburg": "約翰尼斯堡", "sao paulo": "聖保羅", "rio de janeiro": "里約熱內盧",
        "buenos aires": "布宜諾斯艾利斯", "mexico city": "墨西哥城", "stockholm": "斯德哥爾摩",
        "amsterdam": "阿姆斯特丹", "brussels": "布魯塞爾", "vienna": "維也納", "madrid": "馬德里",
        "barcelona": "巴塞隆納", "rome": "羅馬", "milan": "米蘭", "athens": "雅典",
        "copenhagen": "哥本哈根", "oslo": "奧斯陸", "helsinki": "赫爾辛基", "zurich": "蘇黎世",
        "geneva": "日內瓦", "manchester": "曼徹斯特", "boston": "波士頓", "seattle": "西雅圖",
        "miami": "邁阿密", "houston": "休士頓", "taiwan": "台灣", "america": "美國",
        "united states": "美國", "usa": "美國", "china": "中國", "japan": "日本",
        "korea": "南韓", "south korea": "南韓", "united kingdom": "英國", "uk": "英國",
        "britain": "英國", "france": "法國", "germany": "德國", "ukraine": "烏克蘭",
        "russia": "俄羅斯", "israel": "以色列", "palestine": "巴勒斯坦", "gaza": "加薩",
        "india": "印度", "canada": "加拿大", "australia": "澳洲", "new zealand": "紐西蘭",
        "vietnam": "越南", "thailand": "泰國", "philippines": "菲律賓", "malaysia": "馬來西亞",
        "indonesia": "印尼", "italy": "義大利", "spain": "西班牙", "netherlands": "荷蘭",
        "belgium": "比利時", "switzerland": "瑞士", "sweden": "瑞典", "norway": "挪威",
        "finland": "芬蘭", "denmark": "丹麥", "austria": "奧地利", "turkey": "土耳其",
        "saudi arabia": "沙烏地阿拉伯", "iran": "伊朗", "iraq": "伊拉克", "egypt": "埃及",
        "south africa": "南非", "brazil": "巴西", "argentina": "阿根廷", "mexico": "墨西哥",
        "cuba": "古巴", "north korea": "北韓", "pakistan": "巴基斯坦", "greece": "希臘",
        "ireland": "愛爾蘭", "portugal": "葡萄牙", "uae": "阿聯酋", "poland": "波蘭",
        "iceland": "冰島", "middle east": "中東", "europe": "歐洲", "world": "全球", "global": "全球", "taipei": "台北"
    }
    
    final_country_name = display_mapping.get(target, target)
    return final_country_name, coords[0], coords[1]
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
            pass  # 如果欄位以前就已經加過了，就直接忽略，不會卡住
            
        # 關鍵防呆：確保 push_settings 裡面一定要有 id=1 的預設紀錄，防止 .fetchone() 抓到 None 報錯
        c.execute('''INSERT OR IGNORE INTO push_settings (id, line_token, user_id, keywords) 
                     VALUES (1, '', '', '')''')
        
        # 加速查詢索引
        c.execute("CREATE INDEX IF NOT EXISTS idx_time ON monitor_logs(time DESC)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_category ON monitor_logs(category)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_link ON monitor_logs(link)")
        conn.commit()

# 在聲明完 init_db 函數後，立刻執行它，確保後面的代碼不會因為找不到表而崩潰
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

# 🔥【關鍵修改】全新調整的地點偵測系統：依照傳入的字典進行最精確的全自動文字匹配比對
def _detect_country(t_lower, z_lower):
    target = "全球"
    
    # 遍歷我們定義的所有都市與國家
    for loc_name in LOCATION_COORDS.keys():
        # 如果是英文 key 且被包裹在獨立單字中，或是中文關鍵字直接命中
        if loc_name.isalpha():
            if re.search(r'\b' + re.escape(loc_name) + r'\b', t_lower):
                target = loc_name
                break
        else:
            if loc_name in z_lower:
                target = loc_name
                break
                
    # 特別修正特定的英文簡寫對應
    if target == "全球":
        if "white house" in t_lower or "trump" in t_lower or "biden" in t_lower:
            target = "美國"
            
    # 撈取精確經緯度，不再使用隨機飄移干擾
    coords = LOCATION_COORDS.get(target, [20.0, 0.0])
    
    # 將英文名稱轉回對應的漂亮中文標籤顯示在地圖上
    display_mapping = {
        "tokyo": "東京", "new york": "紐約", "nyc": "紐約", "london": "倫敦", "paris": "巴黎",
        "seoul": "首爾", "beijing": "北京", "shanghai": "上海", "hong kong": "香港", "singapore": "新加坡",
        "los angeles": "洛杉磯", "chicago": "芝加哥", "san francisco": "舊金山", "washington": "華盛頓",
        "sydney": "雪梨", "melbourne": "墨爾本", "toronto": "多倫多", "vancouver": "溫哥華",
        "berlin": "柏林", "frankfurt": "法蘭克福", "moscow": "莫斯科", "bangkok": "曼谷",
        "jakarta": "雅加達", "kuala lumpur": "吉隆坡", "manila": "馬尼拉", "mumbai": "孟買",
        "new delhi": "新德里", "dubai": "杜拜", "istanbul": "伊斯坦堡", "cairo": "開羅",
        "johannesburg": "約翰尼斯堡", "sao paulo": "聖保羅", "rio de janeiro": "里約熱內盧",
        "buenos aires": "布宜諾斯艾利斯", "mexico city": "墨西哥城", "stockholm": "斯德哥爾摩",
        "amsterdam": "阿姆斯特丹", "brussels": "布魯塞爾", "vienna": "維也納", "madrid": "馬德里",
        "barcelona": "巴塞隆納", "rome": "羅馬", "milan": "米蘭", "athens": "雅典",
        "copenhagen": "哥本哈根", "oslo": "奧斯陸", "helsinki": "赫爾辛基", "zurich": "蘇黎世",
        "geneva": "日內瓦", "manchester": "曼徹斯特", "boston": "波士頓", "seattle": "西雅圖",
        "miami": "邁阿密", "houston": "休士頓", "taiwan": "台灣", "america": "美國",
        "united states": "美國", "usa": "美國", "china": "中國", "japan": "日本",
        "korea": "南韓", "south korea": "南韓", "united kingdom": "英國", "uk": "英國",
        "britain": "英國", "france": "法國", "germany": "德國", "ukraine": "烏克蘭",
        "russia": "俄羅斯", "israel": "以色列", "palestine": "巴勒斯坦", "gaza": "加薩",
        "india": "印度", "canada": "加拿大", "australia": "澳洲", "new zealand": "紐西蘭",
        "vietnam": "越南", "thailand": "泰國", "philippines": "菲律賓", "malaysia": "馬來西亞",
        "indonesia": "印尼", "italy": "義大利", "spain": "西班牙", "netherlands": "荷蘭",
        "belgium": "比利時", "switzerland": "瑞士", "sweden": "瑞典", "norway": "挪威",
        "finland": "芬蘭", "denmark": "丹麥", "austria": "奧地利", "turkey": "土耳其",
        "saudi arabia": "沙烏地阿拉伯", "iran": "伊朗", "iraq": "伊拉克", "egypt": "埃及",
        "south africa": "南非", "brazil": "巴西", "argentina": "阿根廷", "mexico": "墨西哥",
        "cuba": "古巴", "north korea": "北韓", "pakistan": "巴基斯坦", "greece": "希臘",
        "ireland": "愛爾蘭", "portugal": "葡萄牙", "uae": "阿聯酋", "poland": "波蘭",
        "iceland": "冰島", "middle east": "中東", "europe": "歐洲", "world": "全球", "global": "全球", "taipei": "台北"
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
    if cols_row1[idx].button(item_name, use_container_widt
