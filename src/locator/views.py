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

        # 1. Search Default
        stores = get_nearby_stores(lat, lng)
        
        # 2. Save Session
        request.session['current_stores'] = stores
        request.session['user_location'] = {'lat': float(lat), 'lng': float(lng)}
        
        return JsonResponse({'status': 'success', 'stores': stores})

    except Exception as e:
        logger.error(f"Search API Error: {e}")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

@csrf_exempt
def chat_api(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            user_msg = data.get('message', '')
            
            # Load Context
            current_stores = request.session.get('current_stores', [])
            user_loc = request.session.get('user_location')

            # 1. DETECT INTENT
            intent = detect_intent_with_llama(user_msg)
            action_type = "chat"
            
            # 2. SEARCH NEW (If needed)
            if intent.get('action') == 'SEARCH' and user_loc:
                keyword = intent.get('keyword')
                new_stores = search_specific_stores(user_loc['lat'], user_loc['lng'], keyword)
                
                if new_stores:
                    request.session['current_stores'] = new_stores
                    current_stores = new_stores
                    action_type = "update_map"
            
            # 3. GENERATE ANSWER (Returns JSON {reply, best_store_id})
            ai_result = generate_answer_with_llama(user_msg, current_stores)
            
            # Extract Data
            reply_text = ai_result.get('reply', 'Hệ thống bận.')
            best_store_id = ai_result.get('best_store_id')

            # Find Best Store Object
            suggested_store = None
            if best_store_id:
                for s in current_stores:
                    if s['id'] == best_store_id:
                        suggested_store = s
                        break
            
            return JsonResponse({
                'status': 'success', 
                'reply': reply_text,
                'action': action_type,
                'new_data': current_stores,
                'suggested_store': suggested_store
            })
            
        except Exception as e:
            logger.error(f"Chat API Error: {e}")
            return JsonResponse({'status': 'error', 'message': "Lỗi xử lý chat."}, status=500)
            
    return JsonResponse({'status': 'error'}, status=405)