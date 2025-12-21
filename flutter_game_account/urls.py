from django.urls import path
from . import views

app_name = 'flutter_game_account'

urlpatterns = [
    path('', views.game_accounts_list_create, name='gameaccount-list-create'),
    path('<uuid:pk>/', views.GameAccountDetail.as_view(), name='gameaccount-detail'),
    path('games/', views.games_list, name='game-list'),
]