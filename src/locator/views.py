from django.shortcuts import render
from django.http import JsonResponse
from .utils import get_nearby_stores
import logging

# Khởi tạo logger
logger = logging.getLogger('locator')

def index(request):
    return render(request, 'locator/index.html')

def search_stores_api(request):
    try:
        lat = request.GET.get('lat')
        lng = request.GET.get('lng')
        
        # Log IP và Request
        ip = request.META.get('REMOTE_ADDR')
        logger.info(f"API Search request từ IP {ip} với tọa độ: {lat}, {lng}")

        if not lat or not lng:
            logger.warning("Request thiếu tọa độ")
            return JsonResponse({'status': 'error', 'message': 'Thiếu tọa độ'}, status=400)

        stores = get_nearby_stores(lat, lng)
        return JsonResponse({'status': 'success', 'stores': stores})

    except Exception as e:
        logger.critical(f"Lỗi Server nghiêm trọng trong views: {str(e)}", exc_info=True)
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)