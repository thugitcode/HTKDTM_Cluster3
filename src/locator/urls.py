from django.urls import path
from . import views

urlpatterns = [
    # Trang chủ
    path('', views.index, name='index'),
    
    # API Tìm kiếm (đã chạy ổn)
    path('api/search/', views.search_stores_api, name='search_stores_api'),
    
    # API Chatbot (BẠN ĐANG THIẾU HOẶC SAI DÒNG NÀY)
    path('api/chat/', views.chat_api, name='chat_api'),
]