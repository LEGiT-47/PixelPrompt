from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('chat/<str:chat_id>/', views.chat_detail, name='chat_detail'),
    path('images/<int:image_id>/', views.image_file, name='image_file'),
    path('images/<int:image_id>/download/', views.image_file, {'download': True}, name='image_download'),
    path('login/', auth_views.LoginView.as_view(template_name='login.html'), name='login'),
    path('register/', views.register, name='register'),
    path('logout/', views.logout_view, name='logout'),
]