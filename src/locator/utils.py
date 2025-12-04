import requests
import math
import random
import json
import os
import logging
import google.generativeai as genai
import ollama  # Thư viện giao tiếp Llama 3 Local

# --- CẤU HÌNH LOGGER ---
logger = logging.getLogger('locator')

# Cấu hình Gemini (Dự phòng)
try:
    genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
except Exception as e:
    logger.error(f"Lỗi cấu hình Gemini: {e}")

OVERPASS_SERVERS = [
    "https://overpass.nchc.org.tw/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter", 
]

# --- 1. KHO REVIEW & TAG MAPPING (GIỮ NGUYÊN) ---
REVIEW_TEMPLATES = {
    'food': ["Đồ ăn ngon, giá ổn.", "Không gian đẹp, check-in tốt.", "Phục vụ hơi chậm xíu.", "Sẽ quay lại lần sau."],
    'service': ["Dịch vụ chuyên nghiệp.", "Nhân viên nhiệt tình.", "Giá hơi cao nhưng chất lượng tốt."],
    'fuel': ["Đổ xăng nhanh.", "Trạm rộng rãi.", "Nhân viên thân thiện."]
}

CATEGORY_GROUP = {
    'cafe': 'drink', 'coffee_shop': 'drink', 'tea': 'drink', 'bubble_tea': 'drink', 'bar': 'drink', 'pub': 'drink',
    'restaurant': 'food', 'fast_food': 'food', 'food_court': 'food', 'bistro': 'food',
    'supermarket': 'shopping', 'convenience': 'shopping', 'clothes': 'shopping', 'fashion': 'shopping', 'electronics': 'shopping',
    'pharmacy': 'service', 'hairdresser': 'service', 'bank': 'service', 'hotel': 'service',
    'fuel': 'fuel'
}

TAG_MAPPING = {
    'cafe': {'p': ['Cafe muối', 'Bạc xỉu', 'Trà vải'], 'd': 'Góc cafe chill.', 'type': 'Quán Cafe'},
    'restaurant': {'p': ['Món Á', 'Món Âu', 'Đặc sản'], 'd': 'Ẩm thực trọn vị.', 'type': 'Nhà hàng'},
    'fast_food': {'p': ['Gà rán', 'Burger', 'Khoai tây'], 'd': 'Nhanh chóng, tiện lợi.', 'type': 'Đồ ăn nhanh'},
    'convenience': {'p': ['Mì ly', 'Nước ngọt', 'Bánh bao'], 'd': 'Tiện lợi 24/7.', 'type': 'Tiện lợi'},
    'clothes': {'p': ['Áo thun', 'Quần Jeans', 'Váy'], 'd': 'Thời trang xu hướng.', 'type': 'Shop thời trang'},
    'pharmacy': {'p': ['Thuốc tây', 'Khẩu trang', 'Vitamin'], 'd': 'Dược phẩm uy tín.', 'type': 'Nhà thuốc'},
    'fuel': {'p': ['Xăng A95', 'Xăng E5', 'Dầu DO'], 'd': 'Xăng dầu chất lượng.', 'type': 'Trạm xăng'},
    'bank': {'p': ['Giao dịch', 'ATM', 'Tín dụng'], 'd': 'Dịch vụ ngân hàng.', 'type': 'Ngân hàng'}
}

# --- CÁC HÀM CŨ (GIỮ NGUYÊN LOGIC) ---

def get_nearby_stores(lat, lng, radius=1500, max_results=12):
    try:
        lat, lng = float(lat), float(lng)
        logger.info(f"Bắt đầu tìm kiếm cửa hàng tại tọa độ: {lat}, {lng}")
    except ValueError: 
        return []

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
            'id': str(item.get('id')),
            'name': name,
            'type': meta['type_display'],
            'category_key': category_key,
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
    return enrich_data_with_gemini_strict(sorted_stores, limit=8)

def generate_smart_metadata(name, category_key):
    meta = {
        'rating': round(random.uniform(4.0, 5.0), 1),
        'reviews_count': random.randint(10, 150),
        'open_hour': "08:00 - 22:00",
        'tags': ["Phổ biến"]
    }
    
    template = TAG_MAPPING.get(category_key)
    if template:
        meta['products'] = template['p']
        meta['description'] = template['d']
        meta['type_display'] = template['type']
        if category_key in ['cafe', 'bar', 'pub']: meta['open_hour'] = "07:00 - 23:00"
        elif category_key in ['convenience', 'fuel']: meta['open_hour'] = "24/7"
        else: meta['open_hour'] = "08:00 - 21:00"
        pool = 'fuel' if category_key == 'fuel' else ('food' if category_key in ['cafe', 'restaurant'] else 'service')
        meta['review_list'] = random.sample(REVIEW_TEMPLATES.get(pool, REVIEW_TEMPLATES['service']), 2)
    else:
        meta['products'] = ["Sản phẩm dịch vụ"]
        meta['description'] = f"Địa điểm {name}."
        meta['type_display'] = category_key.capitalize()
        meta['open_hour'] = "08:00 - 21:00"
        meta['review_list'] = ["Dịch vụ tốt."]
    return meta

def enrich_data_with_gemini_strict(stores, limit=8):
    if not stores or not os.getenv("GEMINI_API_KEY"): return stores
    try:
        mini_list = [{"id": s['id'], "n": s['name'], "cat": s['category_key']} for s in stores[:limit]]
        prompt = f"""
        Role: Vietnam Local Guide. Generate JSON. Input: {json.dumps(mini_list)}
        STRICT RULES:
        1. IF cat='fuel' -> Reviews about gasoline. Products: Fuel types.
        2. IF cat='pharmacy' -> Reviews about medicine.
        Output Key: ID. Fields: r(rating), rv(reviews count), o(open hour), p(products list), d(desc), rv_txt(list 2 reviews).
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
    headers = {'User-Agent': 'Mozilla/5.0'}
    for url in OVERPASS_SERVERS:
        try:
            r = requests.get(url, params={'data': query}, headers=headers, timeout=15)
            if r.status_code == 200 and 'json' in r.headers.get('Content-Type', ''): return r.json()
        except: continue
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
    # Mock data
    return []

# --- CÁC HÀM MỚI: CHATBOT AGENT (LLAMA 3) ---
# Các hàm này phục vụ cho API Chat, không ảnh hưởng API Search cũ

def detect_intent_with_llama(user_message):
    """
    Phân tích ý định: Người dùng muốn CHAT hay TÌM KIẾM?
    """
    try:
        prompt = f"""
        You are an AI Map Assistant. User message: "{user_message}"
        
        Task: Analyze if the user wants to SEARCH/FIND a specific place/service type that might not be visible.
        
        - YES (e.g. "Find gas", "Where is pharmacy", "Sửa xe ở đâu", "Tìm quán phở"): 
          Return JSON: {{ "action": "SEARCH", "keyword": "<english_osm_tag>" }}
          (Tags: cafe, restaurant, pharmacy, fuel, atm, bank, mobile_phone, hospital, car_repair)
          
        - NO (e.g. "Hello", "Is it close?", "Suggest a place", "Thanks"): 
          Return JSON: {{ "action": "CHAT" }}
          
        Reply ONLY JSON. No markdown.
        """
        
        response = ollama.chat(model='llama3', messages=[{'role': 'user', 'content': prompt}])
        content = response['message']['content']
        start = content.find('{')
        end = content.rfind('}') + 1
        return json.loads(content[start:end])
    except Exception as e:
        logger.error(f"Llama Intent Error: {e}")
        return {"action": "CHAT"}

def generate_answer_with_llama(user_message, stores_context):
    """
    Trả lời câu hỏi dựa trên ngữ cảnh (RAG)
    """
    try:
        context_text = ""
        if not stores_context:
            context_text = "Không tìm thấy cửa hàng nào gần đây."
        else:
            # Lấy 10 quán đầu tiên làm context
            for i, s in enumerate(stores_context[:10]):
                context_text += f"{i+1}. {s['name']} ({s['type']}) - {s['distance']:.2f}km. Rating: {s['rating']}. Mở: {s['open_hour']}. Mô tả: {s['description']}\n"

        prompt = f"""
        Bạn là trợ lý ảo bản đồ thông minh (nói tiếng Việt).
        
        DỮ LIỆU CỬA HÀNG XUNG QUANH:
        {context_text}
        
        CÂU HỎI CỦA KHÁCH: "{user_message}"
        
        YÊU CẦU:
        1. Trả lời ngắn gọn, thân thiện, tự nhiên.
        2. Gợi ý quán tốt nhất từ dữ liệu trên (dựa vào khoảng cách, rating).
        3. Nếu tìm thấy quán phù hợp, hãy nêu tên và lý do.
        """
        
        response = ollama.chat(model='llama3', messages=[{'role': 'user', 'content': prompt}])
        return response['message']['content']
    except Exception as e:
        logger.error(f"Llama Answer Error: {e}")
        return "Xin lỗi, hệ thống AI đang bận. Vui lòng thử lại sau."

def search_specific_stores(lat, lng, keyword, radius=2000):
    """
    Tìm kiếm cửa hàng theo từ khóa cụ thể (Dùng cho Agent)
    """
    try: lat, lng = float(lat), float(lng)
    except: return []

    # Query tìm kiếm theo từ khóa
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

        # Dùng keyword làm category key để sinh dữ liệu fallback
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
            
    return sorted(raw_stores, key=lambda x: x['distance'])