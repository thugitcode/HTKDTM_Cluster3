from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from .utils import get_nearby_stores, detect_intent_with_llama, search_specific_stores, generate_answer_with_llama
import json
import logging

logger = logging.getLogger('locator')

def index(request):
    return render(request, 'locator/index.html')

def search_stores_api(request):
    try:
        lat = request.GET.get('lat')
        lng = request.GET.get('lng')
        if not lat or not lng:
            return JsonResponse({'status': 'error', 'message': 'Thiếu tọa độ'}, status=400)

        stores = get_nearby_stores(lat, lng)
        
        # Lưu Session
        request.session['current_stores'] = stores
        request.session['user_location'] = {'lat': float(lat), 'lng': float(lng)}
        
        return JsonResponse({'status': 'success', 'stores': stores})
    except Exception as e:
        logger.error(f"Search Error: {e}")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

@csrf_exempt
def chat_api(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            user_msg = data.get('message', '')
            
            # Lấy Context từ Session
            current_stores = request.session.get('current_stores', [])
            user_loc = request.session.get('user_location')

            # BƯỚC 1: Phát hiện ý định
            intent = detect_intent_with_llama(user_msg)
            action_type = "chat"
            
            # BƯỚC 2: Tìm kiếm mới (Nếu cần)
            if intent.get('action') == 'SEARCH' and user_loc:
                keyword = intent.get('keyword')
                logger.info(f"AI Agent: Searching for {keyword}")
                
                new_stores = search_specific_stores(user_loc['lat'], user_loc['lng'], keyword)
                
                if new_stores:
                    request.session['current_stores'] = new_stores
                    current_stores = new_stores
                    action_type = "update_map"
            
            # BƯỚC 3: Trả lời
            ai_reply = generate_answer_with_llama(user_msg, current_stores)
            
            # Lấy quán tốt nhất để gợi ý (nếu có)
            suggested_store = current_stores[0] if current_stores else None
            
            return JsonResponse({
                'status': 'success', 
                'reply': ai_reply,
                'action': action_type,
                'new_data': current_stores,
                'suggested_store': suggested_store
            })
            
        except Exception as e:
            logger.error(f"Chat Error: {e}")
            return JsonResponse({'status': 'error', 'message': "Lỗi xử lý chat."}, status=500)
            
    return JsonResponse({'status': 'error'}, status=405)