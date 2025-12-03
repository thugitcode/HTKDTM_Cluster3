from django.shortcuts import render
from django.http import JsonResponse
from .utils import get_nearby_stores

def index(request):
    return render(request, 'locator/index.html')

def search_stores_api(request):
    try:
        lat = request.GET.get('lat')
        lng = request.GET.get('lng')
        if not lat or not lng:
            return JsonResponse({'status': 'error', 'message': 'Thiếu tọa độ'}, status=400)

        stores = get_nearby_stores(lat, lng)
        return JsonResponse({'status': 'success', 'stores': stores})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)