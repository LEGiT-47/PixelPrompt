from django.urls import path
from django.contrib.auth import views as auth_views
from . import views
from .forms import LoginForm

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('chat/', views.chat_home, name='chat_home'),
    path('chat/<int:chat_id>/', views.chat_detail, name='chat_detail'),
    path('chat/<int:chat_id>/rename/', views.rename_chat, name='rename_chat'),
    path('chat/<int:chat_id>/delete/', views.delete_chat, name='delete_chat'),
    path('chat/<int:chat_id>/clear/', views.clear_chat, name='clear_chat'),
    path('login/', auth_views.LoginView.as_view(template_name='login.html'), name='login'),
    path('register/', views.register, name='register'),
    path('logout/', views.logout_view, name='logout'),
]
from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('chat/<str:chat_id>/', views.chat_detail, name='chat_detail'),
    path('login/', auth_views.LoginView.as_view(template_name='login.html', authentication_form=LoginForm), name='login'),
    path('register/', views.register, name='register'),
    path('logout/', views.logout_view, name='logout'),
]
    path('images/<int:image_id>/', views.image_file, name='image_file'),
    path('images/<int:image_id>/download/', views.image_file, {'download': True}, name='image_download'),
    path('login/', auth_views.LoginView.as_view(template_name='login.html'), name='login'),
    path('register/', views.register, name='register'),
    path('logout/', views.logout_view, name='logout'),
]
