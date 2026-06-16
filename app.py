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
    elif "mexico city" in t_lower or "貿易" in z_lower: target = "墨西哥城"

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
            
            # 完全小寫比對，精確過濾 Error 500 等伺服器異常訊息
            t_lower = title_raw.lower()
            if "error 500" in t_lower or "server error" in t_lower or "internal server error" in t_lower: 
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
            # 發生異常時，降級為逐條翻譯，確保某條出錯時其他正常新聞依然有中文
            for orig in group: 
                try:
                    translations[orig] = translator.translate(orig)
                except Exception:
                    translations[orig] = orig
    return translations

def fetch_all_news():
# 其餘 fetch_all_news() 的程式碼保持不變...
