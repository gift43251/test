import feedparser
import requests
from deep_translator import GoogleTranslator
from textblob import TextBlob
import sqlite3
import pandas as pd
from datetime import datetime
import re
import random
from transformers import pipeline as hf_pipeline
from concurrent.futures import ThreadPoolExecutor, as_completed

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
    "科技": ["tech", "semiconductor", "apple", "google", "gpu", "tsmc", "台積電", "晶片", "科技", "人工智慧"],
    "體育": ["sport", "nba", "fifa", "olympics", "football", "tennis", "rookie", "mvp", "veteran", "blowout", "comeback", "upside", "momentum", "athletics", "blank", "edge", "運動", "籃球", "奧運", "體育"],
    "民生健康": ["health", "virus", "climate", "food", "medicine", "symptoms", "chronic", "acute", "diagnosis", "side effects", "immunity", "metabolism", "nutrient", "diet", "sedentary", "cancer", "flu", "hypertension", "diabetes", "病毒", "氣候", "醫療", "健康", "民生"]
}

COUNTRY_COORDS = {
    "美國": [37.0902, -95.7129], "中國": [35.8617, 104.1954], "英國": [55.3781, -3.4360],
    "台灣": [23.6978, 120.9605], "烏克蘭": [48.3794, 31.1656], "中東": [32.4279, 53.6880],
    "日本": [36.2048, 138.2529], "歐洲": [48.6909, 9.1406], "全球": [20.0, 0.0]
}

CRISIS_STRONG_WORDS = ["襲擊", "無人機", "轟炸", "導彈", "開火", "進攻", "突襲", "交火", "戰機", "軍事演習", "劫持", "人質", "擊斃", "槍擊", "逮捕", "爆炸", "恐怖襲擊", "死亡", "死傷", "炸彈", "combat", "drone", "attack", "missile", "hostage", "shot dead", "hijack", "explode", "bomb"]

def call_ai_arbitrator(title_zh, clf):
    try:
        candidate_labels = ["military and geopolitics conflict", "economy and finance market", "technology and science innovations", "sports news", "health and lifestyle medicine", "general international news"]
        result = clf(title_zh, candidate_labels)
        mapping = {
            "military and geopolitics conflict": "軍事政治", "economy and finance market": "經濟",
            "technology and science innovations": "科技", "sports news": "體育",
            "health and lifestyle medicine": "民生健康", "general international news": "一般國際"
        }
        return mapping.get(result['labels'][0], "一般國際")
    except: return "一般國際"

def hybrid_news_classifier(title_zh, title_en, clf):
    match_text = (title_en + " " + title_zh).lower()
    if any(sw in match_text for sw in CRISIS_STRONG_WORDS) and clf is not None:
        return call_ai_arbitrator(title_zh, clf)
    scores = {k: 0 for k in DEFAULT_CATEGORIES.keys()}
    for cat, keywords in DEFAULT_CATEGORIES.items():
        for word in keywords:
            if word.lower() in match_text: scores[cat] += match_text.count(word.lower())
    max_cat = max(scores, key=scores.get)
    if scores[max_cat] == 0:
        return call_ai_arbitrator(title_zh, clf) if clf is not None else "一般國際"
    return max_cat

def send_line_push(token, user_id, msg):
    if not token or not user_id: return
    url = "https://api.line.me/v2/bot/message/push"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}
    payload = {"to": user_id, "messages": [{"type": "text", "text": msg}]}
    try: requests.post(url, json=payload, headers=headers)
    except: pass

def _detect_country(t_lower, z_lower):
    if "美國" in z_lower or "川普" in z_lower or re.search(r'\btrump\b|\bamerica\b', t_lower): target = "美國"
    elif "台灣" in z_lower or "台積電" in z_lower or re.search(r'\btaiwan\b', t_lower): target = "台灣"
    elif "烏克蘭" in z_lower or re.search(r'\bukraine\b', t_lower): target = "烏克蘭"
    elif "中國" in z_lower or re.search(r'\bchina\b', t_lower): target = "中國"
    else: target = "全球"
    base_lat, base_lon = COUNTRY_COORDS[target]
    offset = 0.8 if target != "全球" else 5
    return target, base_lat + random.uniform(-offset, offset), base_lon + random.uniform(-offset, offset)

def _fetch_source_raw(src):
    results = []
    try:
        feed = feedparser.parse(src["url"], request_headers={"User-Agent": "Mozilla/5.0"})
        for entry in feed.entries[:12]:
            t, l = getattr(entry, 'title', '').strip(), getattr(entry, 'link', '').strip()
            if t and l and "error" not in t.lower(): results.append((t, l, src["name"]))
    except: pass
    return results

def main():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS monitor_logs (id INTEGER PRIMARY KEY AUTOINCREMENT, title_zh TEXT, category TEXT, source TEXT, time TEXT, link TEXT UNIQUE, sentiment REAL, country TEXT, lat REAL, lon REAL)")
    
    # 讀取網頁端寫入的 LINE 設定
    push_cfg = c.execute("SELECT line_token, user_id, keywords FROM push_settings WHERE id=1").fetchone()
    
    all_raw = []
    with ThreadPoolExecutor(max_workers=5) as ex:
        futures = [ex.submit(_fetch_source_raw, src) for src in NEWS_SOURCES]
        for f in as_completed(futures): all_raw.extend(f.result())
        
    if not all_raw: return
    
    existing = set(r[0] for r in c.execute("SELECT link FROM monitor_logs").fetchall())
    new_entries = [r for r in all_raw if r[1] not in existing]
    if not new_entries: return

    translator = GoogleTranslator(source='auto', target='zh-TW')
    clf = hf_pipeline("zero-shot-classification", model="vicgalle/xlm-roberta-large-xnli-anli")
    
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    for title_raw, link_raw, source_name in new_entries:
        is_ch = any('\u4e00' <= char <= '\u9fff' for char in title_raw)
        title_zh = title_raw if is_ch else translator.translate(title_raw)
        title_en = "" if is_ch else title_raw
        
        cat = hybrid_news_classifier(title_zh, title_en, clf)
        sentiment = TextBlob(title_en if title_en else title_zh).sentiment.polarity
        country, lat, lon = _detect_country(title_en.lower(), title_zh.lower())
        
        # 寫入資料庫
        c.execute("INSERT OR IGNORE INTO monitor_logs (title_zh, category, source, time, link, sentiment, country, lat, lon) VALUES (?,?,?,?,?,?,?,?,?)",
                  (title_zh, cat, source_name, now, link_raw, sentiment, country, lat, lon))
        
        # 智慧預警比對
        if push_cfg and push_cfg[0] and push_cfg[1] and push_cfg[2]:
            token, uid, kw_str = push_cfg
            kws = [k.strip() for k in kw_str.split(",") if k.strip()]
            for kw in kws:
                if kw.lower() in title_zh.lower():
                    msg = f"📢 智能預警：偵測到關鍵字【{kw}】！\n\n📰 標題：{title_zh}\n📡 來源：{source_name}\n🔗 連結：{link_raw}"
                    send_line_push(token, uid, msg)
                    break
    conn.commit()
    conn.close()

if __name__ == "__main__":
    main()
