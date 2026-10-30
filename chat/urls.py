from django.urls import path
from django.contrib.auth import views as auth_views
from . import views
from .forms import LoginForm

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('chat/<str:chat_id>/', views.chat_detail, name='chat_detail'),
    path('images/<int:image_id>/', views.serve_image, name='serve_image'),
    path('images/<int:image_id>/delete/', views.delete_image, name='delete_image'),
    path('chats/<int:chat_id>/rename/', views.rename_chat, name='rename_chat'),
    path('chats/<int:chat_id>/clear/', views.clear_chat, name='clear_chat'),
    path('chats/<int:chat_id>/delete/', views.delete_chat, name='delete_chat'),
    path('login/', auth_views.LoginView.as_view(
        template_name='login.html',
        authentication_form=LoginForm,
    ), name='login'),
    path('register/', views.register, name='register'),
    path('logout/', views.logout_view, name='logout'),
]