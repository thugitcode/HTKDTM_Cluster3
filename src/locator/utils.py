import requests
import math
import random
import json
import os
import logging
import google.generativeai as genai

# --- CẤU HÌNH LOGGER ---
logger = logging.getLogger('locator')

# Cấu hình Gemini
try:
    genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
except Exception as e:
    logger.error(f"Lỗi cấu hình Gemini: {e}")

OVERPASS_SERVERS = [
    "https://overpass.nchc.org.tw/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter", 
]

# --- 1. KHO REVIEW THEO NGÀNH HÀNG (QUAN TRỌNG) ---
REVIEW_TEMPLATES = {
    'food': ["Đồ ăn ngon, giá ổn.", "Không gian đẹp, check-in tốt.", "Phục vụ hơi chậm xíu.", "Sẽ quay lại lần sau."],
    'service': ["Dịch vụ chuyên nghiệp.", "Nhân viên nhiệt tình.", "Giá hơi cao nhưng chất lượng tốt."],
    'fuel': ["Đổ xăng nhanh.", "Trạm rộng rãi.", "Nhân viên thân thiện."]
}

# Mapping Category -> Review Type
CATEGORY_GROUP = {
    'cafe': 'drink', 'coffee_shop': 'drink', 'tea': 'drink', 'bubble_tea': 'drink', 'bar': 'drink', 'pub': 'drink',
    'restaurant': 'food', 'fast_food': 'food', 'food_court': 'food', 'bistro': 'food',
    'supermarket': 'shopping', 'convenience': 'shopping', 'clothes': 'shopping', 'fashion': 'shopping', 'electronics': 'shopping',
    'pharmacy': 'service', 'hairdresser': 'service', 'bank': 'service', 'hotel': 'service',
    'fuel': 'fuel'
}

# Mapping Dữ liệu chi tiết (Sản phẩm & Mô tả)
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

def get_nearby_stores(lat, lng, radius=1500, max_results=12):
    try:
        lat, lng = float(lat), float(lng)
        logger.info(f"Bắt đầu tìm kiếm cửa hàng tại tọa độ: {lat}, {lng}")
    except ValueError: 
        logger.warning(f"Tọa độ không hợp lệ: {lat}, {lng}")
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
        logger.warning("API Overpass thất bại hoặc rỗng -> Chuyển sang Mock Data")
        return generate_mock_data(lat, lng)
        
    elements = data.get('elements', [])
    logger.info(f"API trả về {len(elements)} địa điểm thô.")
    
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
    if not stores or not os.getenv("GEMINI_API_KEY"):
        logger.info("Bỏ qua AI (Không có Key hoặc danh sách rỗng)")
        return stores

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

        for store in stores:
            sid = str(store['id'])
            if sid in ai_data:
                d = ai_data[sid]
                store.update({
                    'rating': d.get('r', store['rating']),
                    'reviews_count': d.get('rv', store['reviews_count']),
                    'open_hour': d.get('o', store['open_hour']),
                    'products': d.get('p', store['products']),
                    'description': d.get('d', store['description']),
                    'review_list': d.get('rv_txt', store['review_list'])
                })
        logger.info("Đã làm giàu dữ liệu bằng AI thành công.")
    except Exception as e:
        logger.error(f"Lỗi AI Enrichment: {e}")
        pass
    return stores

def fetch_overpass_data(query):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Referer': 'https://www.google.com/'
    }
    
    for url in OVERPASS_SERVERS:
        try:
            logger.debug(f"Thử kết nối: {url}")
            r = requests.get(url, params={'data': query}, headers=headers, timeout=15)
            
            if r.status_code == 200:
                ctype = r.headers.get('Content-Type', '').lower()
                if 'json' in ctype:
                    logger.info(f"Kết nối thành công tới {url}")
                    return r.json()
                else:
                    logger.warning(f"Server {url} trả về {ctype} (không phải JSON)")
            else:
                logger.warning(f"Lỗi HTTP {r.status_code} từ {url}")
                
        except Exception as e: 
            logger.warning(f"Ngoại lệ khi gọi {url}: {e}")
            continue
            
    logger.error("Tất cả server Overpass đều thất bại.")
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
    logger.info("Đang tạo Mock Data...")
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