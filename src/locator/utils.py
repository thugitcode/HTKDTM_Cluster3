import requests
import math
import random
import json
import os
import logging
import ollama
import google.generativeai as genai

# --- CẤU HÌNH ---
logger = logging.getLogger('locator')

try:
    genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
except Exception as e:
    logger.error(f"Gemini Config Error: {e}")

OVERPASS_SERVERS = [
    "https://overpass.nchc.org.tw/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter", 
]

# --- DATA POOLS (FALLBACK) ---
REVIEW_TEMPLATES = {
    'food': ["Đồ ăn ngon, giá ổn.", "Không gian đẹp, check-in tốt.", "Phục vụ hơi chậm xíu.", "Sẽ quay lại lần sau."],
    'service': ["Dịch vụ chuyên nghiệp.", "Nhân viên nhiệt tình.", "Giá hơi cao nhưng chất lượng tốt."],
    'fuel': ["Đổ xăng nhanh.", "Trạm rộng rãi.", "Nhân viên thân thiện."]
}

TAG_MAPPING = {
    'cafe': {'p': ['Cafe muối', 'Bạc xỉu', 'Trà vải'], 'd': 'Góc cafe chill.', 'type': 'Quán Cafe'},
    'restaurant': {'p': ['Món Á', 'Món Âu', 'Đặc sản'], 'd': 'Ẩm thực trọn vị.', 'type': 'Nhà hàng'},
    'fast_food': {'p': ['Gà rán', 'Burger', 'Khoai tây'], 'd': 'Nhanh chóng, tiện lợi.', 'type': 'Đồ ăn nhanh'},
    'convenience': {'p': ['Mì ly', 'Nước ngọt', 'Bánh bao'], 'd': 'Tiện lợi 24/7.', 'type': 'Tiện lợi'},
    'clothes': {'p': ['Áo thun', 'Quần Jeans', 'Váy'], 'd': 'Thời trang xu hướng.', 'type': 'Shop thời trang'},
    'pharmacy': {'p': ['Thuốc tây', 'Khẩu trang', 'Vitamin'], 'd': 'Dược phẩm uy tín.', 'type': 'Nhà thuốc'},
    'fuel': {'p': ['Xăng A95', 'Xăng E5', 'Dầu DO'], 'd': 'Xăng dầu chất lượng.', 'type': 'Trạm xăng'},
    'bank': {'p': ['Giao dịch', 'ATM', 'Tín dụng'], 'd': 'Dịch vụ ngân hàng.', 'type': 'Ngân hàng'},
    'mobile_phone': {'p': ['Sửa màn hình', 'Ép kính', 'Phụ kiện'], 'd': 'Sửa chữa uy tín.', 'type': 'Sửa điện thoại'}
}

# --- AI AGENT FUNCTIONS ---

def detect_intent_with_llama(user_message):
    """
    Phân tích ý định: Tìm kiếm mới hay Chat thường?
    """
    prompt = f"""
    You are a Map Assistant. User says: "{user_message}"
    Task: Does the user want to SEARCH for a place type NOT likely in the current list (e.g. "Find gas", "Where is ATM", "Sửa xe")?
    
    - YES: Return JSON {{ "action": "SEARCH", "keyword": "<osm_tag>" }}
      (Tags: cafe, restaurant, pharmacy, fuel, atm, bank, mobile_phone, hospital, car_repair)
    - NO: Return JSON {{ "action": "CHAT" }}
    
    Reply JSON ONLY.
    """
    
    # 1. Thử Ollama
    try:
        response = ollama.chat(model='llama3', messages=[{'role': 'user', 'content': prompt}])
        content = response['message']['content']
        start = content.find('{')
        end = content.rfind('}') + 1
        return json.loads(content[start:end])
    except Exception as e:
        logger.warning(f"Ollama Intent Error: {e}")

    # 2. Fallback Gemini
    try:
        model = genai.GenerativeModel('gemini-pro')
        response = model.generate_content(prompt)
        return json.loads(response.text.replace('```json', '').replace('```', '').strip())
    except:
        return {"action": "CHAT"}

def generate_answer_with_llama(user_message, stores_context):
    """
    Trả lời câu hỏi tự nhiên, có cảm xúc và trả về ID quán tốt nhất.
    """
    context_list = []
    if not stores_context:
        context_text = "Không tìm thấy địa điểm nào phù hợp."
    else:
        # Lấy 5 quán đầu tiên để AI tập trung tư vấn
        for s in stores_context[:5]:
            context_list.append(f"ID:{s['id']} | Tên:{s['name']} | Cách:{s['distance']:.2f}km | Loại:{s['type']} | Đặc điểm:{s['description']}")
        context_text = "\n".join(context_list)

    prompt = f"""
    Bạn là trợ lý bản đồ thông minh và thân thiện (nói tiếng Việt).
    
    DỮ LIỆU CỬA HÀNG XUNG QUANH:
    {context_text}
    
    CÂU HỎI CỦA KHÁCH: "{user_message}"
    
    YÊU CẦU:
    1. Trả lời tự nhiên, thân thiện như một người bạn địa phương. Đừng quá máy móc.
    2. Dựa vào dữ liệu trên, hãy chọn ra 1 quán phù hợp nhất để gợi ý.
    3. Giải thích ngắn gọn tại sao bạn chọn quán đó (ví dụ: gần nhất, review tốt...).
    4. Cuối cùng, hãy mời người dùng bấm vào thẻ bên dưới để xem đường đi.
    
    OUTPUT FORMAT (JSON ONLY):
    {{
        "reply": "Lời chào và câu trả lời tự nhiên của bạn...",
        "best_store_id": "ID_CỦA_QUÁN_BẠN_CHỌN" (Hoặc null nếu không có quán nào phù hợp)
    }}
    """
    
    try:
        # Ưu tiên Ollama
        response = ollama.chat(model='llama3', messages=[{'role': 'user', 'content': prompt}])
        content = response['message']['content']
    except:
        # Fallback Gemini
        try:
            model = genai.GenerativeModel('gemini-pro')
            response = model.generate_content(prompt)
            content = response.text
        except:
            return {"reply": "Hệ thống AI đang bận, bạn xem danh sách bên dưới nhé.", "best_store_id": None}

    # Parse JSON từ AI
    try:
        start = content.find('{')
        end = content.rfind('}') + 1
        return json.loads(content[start:end])
    except:
        # Nếu AI không trả JSON chuẩn, fallback lấy quán đầu tiên
        first_id = stores_context[0]['id'] if stores_context else None
        return {
            "reply": "Mình tìm thấy địa điểm này gần bạn nhất, bạn xem thử nhé.",
            "best_store_id": first_id
        }

def search_specific_stores(lat, lng, keyword, radius=3000):
    try: lat, lng = float(lat), float(lng)
    except: return []

    query = f"""
        [out:json][timeout:15];
        (
          node["shop"~"{keyword}",i](around:{radius},{lat},{lng});
          node["amenity"~"{keyword}",i](around:{radius},{lat},{lng});
          node["name"~"{keyword}",i](around:{radius},{lat},{lng});
        );
        out 15;
    """
    
    data = fetch_overpass_data(query)
    if not data or 'elements' not in data: return []
    
    elements = data.get('elements', [])
    raw_stores = []
    
    for item in elements:
        item_lat = item.get('lat')
        item_lon = item.get('lon')
        name = item.get('tags', {}).get('name')
        if not item_lat or not item_lon or not name: continue

        # Dùng keyword làm key để sinh dữ liệu giả lập chính xác
        meta = generate_smart_metadata(name, keyword)
        tags = item.get('tags', {})

        raw_stores.append({
            'id': str(item.get('id')),
            'name': name,
            'type': meta['type_display'],
            'category_key': keyword,
            'lat': item_lat,
            'lng': item_lon,
            'distance': calculate_distance(lat, lng, item_lat, item_lon),
            'address': tags.get('addr:street') or "Đang cập nhật địa chỉ",
            'rating': meta['rating'],
            'reviews_count': meta['reviews_count'],
            'open_hour': meta['open_hour'],
            'products': meta['products'],
            'description': meta['description'],
            'tags': meta['tags'],
            'review_list': meta['review_list']
        })
            
    sorted_stores = sorted(raw_stores, key=lambda x: x['distance'])
    return enrich_data_with_ai(sorted_stores)

# --- CORE LOGIC ---

def get_nearby_stores(lat, lng, radius=1500, max_results=12):
    try: lat, lng = float(lat), float(lng)
    except: return []

    query = f"""
        [out:json][timeout:15];
        (
          node["shop"](around:{radius},{lat},{lng});
          node["amenity"~"cafe|restaurant|fast_food|bar|pub|fuel|bank|pharmacy"](around:{radius},{lat},{lng});
        );
        out {max_results};
    """
    
    data = fetch_overpass_data(query)
    if not data or 'elements' not in data:
        return generate_mock_data(lat, lng)
        
    elements = data.get('elements', [])
    raw_stores = []
    
    for item in elements:
        item_lat = item.get('lat')
        item_lon = item.get('lon')
        tags = item.get('tags', {})
        name = tags.get('name')
        if not item_lat or not item_lon or not name: continue

        category_key = tags.get('shop') or tags.get('amenity') or 'unknown'
        meta = generate_smart_metadata(name, category_key)

        raw_stores.append({
            'id': str(item.get('id')), 'name': name, 'type': meta['type_display'], 'category_key': category_key,
            'lat': item_lat, 'lng': item_lon, 'distance': calculate_distance(lat, lng, item_lat, item_lon),
            'address': tags.get('addr:street') or "Đang cập nhật địa chỉ",
            'rating': meta['rating'], 'reviews_count': meta['reviews_count'], 'open_hour': meta['open_hour'],
            'products': meta['products'], 'description': meta['description'], 'tags': meta['tags'], 'review_list': meta['review_list']
        })
            
    sorted_stores = sorted(raw_stores, key=lambda x: x['distance'])
    return enrich_data_with_ai(sorted_stores, limit=8)

def generate_smart_metadata(name, category_key):
    meta = {'rating': round(random.uniform(4.0, 5.0), 1), 'reviews_count': random.randint(10, 150), 'tags': ["Phổ biến"]}
    
    if 'mobile' in category_key or 'phone' in category_key: template = TAG_MAPPING.get('mobile_phone')
    elif 'fuel' in category_key or 'gas' in category_key: template = TAG_MAPPING.get('fuel')
    else: template = TAG_MAPPING.get(category_key)

    if template:
        meta.update({'products': template['p'], 'description': template['d'], 'type_display': template['type']})
        if category_key in ['cafe', 'bar']: meta['open_hour'] = "07:00 - 23:00"
        elif category_key in ['convenience', 'fuel']: meta['open_hour'] = "24/7"
        else: meta['open_hour'] = "08:00 - 21:00"
        pool = 'fuel' if 'fuel' in category_key else ('food' if 'cafe' in category_key else 'service')
        meta['review_list'] = random.sample(REVIEW_TEMPLATES.get(pool, REVIEW_TEMPLATES['service']), 2)
    else:
        meta.update({'products': ["Sản phẩm dịch vụ"], 'description': f"Địa điểm {name}.", 'type_display': "Cửa hàng", 'open_hour': "08:00 - 21:00", 'review_list': ["Dịch vụ tốt."]})
    return meta

def enrich_data_with_ai(stores, limit=8):
    if not stores or not os.getenv("GEMINI_API_KEY"): return stores
    try:
        mini_list = [{"id": s['id'], "n": s['name'], "cat": s['category_key']} for s in stores[:limit]]
        prompt = f"""
        Generate JSON data. Input: {json.dumps(mini_list)}
        Rules: IF 'fuel' -> products=fuel types.
        Output JSON Key=ID: {{ "r": 4.5, "rv": 50, "o": "07:00-22:00", "p": ["Item1", "Item2"], "d": "Desc", "rv_txt": ["Review1", "Review2"] }}
        JSON Only.
        """
        model = genai.GenerativeModel('gemini-pro')
        response = model.generate_content(prompt)
        ai_data = json.loads(response.text.replace('```json', '').replace('```', '').strip())
        for s in stores:
            if str(s['id']) in ai_data:
                d = ai_data[str(s['id'])]
                s.update({'rating': d.get('r', s['rating']), 'reviews_count': d.get('rv', s['reviews_count']), 'open_hour': d.get('o', s['open_hour']), 'products': d.get('p', s['products']), 'description': d.get('d', s['description']), 'review_list': d.get('rv_txt', s['review_list'])})
    except: pass
    return stores

def fetch_overpass_data(query):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Referer': 'https://www.google.com/'
    }
    
    for url in OVERPASS_SERVERS:
        try:
            logger.debug(f"Connecting to: {url}")
            r = requests.get(url, params={'data': query}, headers=headers, timeout=15)
            
            if r.status_code == 200:
                ctype = r.headers.get('Content-Type', '').lower()
                if 'json' in ctype:
                    return r.json()
        except Exception: 
            continue
            
    return None

def calculate_distance(lat1, lon1, lat2, lon2):
    try:
        R = 6371.0 
        dLat = math.radians(float(lat2) - float(lat1))
        dLon = math.radians(float(lon2) - float(lon1))
        a = math.sin(dLat/2)**2 + math.cos(math.radians(float(lat1))) * math.cos(math.radians(float(lat2))) * math.sin(dLon/2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        return R * c
    except: return 0.0

def generate_mock_data(lat, lng):
    bases = [("Highlands Coffee", "Cafe"), ("Phở Cồ", "Nhà hàng"), ("WinMart+", "Tiện lợi"), ("Petrolimex", "Trạm xăng")]
    results = []
    for i, (name, stype) in enumerate(bases):
        key = 'fuel' if 'xăng' in stype else ('cafe' if 'Cafe' in stype else 'restaurant')
        meta = generate_smart_metadata(name, key)
        results.append({
            'id': f"mock_{i}", 'name': name, 'type': stype, 'category_key': key,
            'lat': lat + 0.001*(i+1), 'lng': lng + 0.001*(i+1),
            'distance': 0.1 * (i+1), 'address': "Vị trí giả lập (Mất kết nối API)",
            **meta 
        })
    return sorted(results, key=lambda x: x['distance'])