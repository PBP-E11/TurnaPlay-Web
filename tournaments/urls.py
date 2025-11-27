from django.urls import path, include
from tournaments.views import show_main, tournament_create
from . import views

app_name = 'tournaments'

urlpatterns = [
    path('', show_main, name='show_main'),
    # Temporary safe mapping: render main page until TournamentListView is implemented
    path('tournaments/', show_main, name='tournament-list'),
    
    # --- Create tournament (function view) ---
    path('tournaments/create/', tournament_create, name='tournament-create'),
    path('tournaments/<uuid:pk>/', views.tournament_detail, name='tournament-detail'),
    
    path('tournaments/api/', views.tournament_list_json, name='tournament-list-json'),
    path('games/<uuid:game_id>/formats/api/', views.formats_for_game, name='api-game-formats'),

    path('<uuid:pk>/delete/', views.tournament_delete, name='tournament-delete'),
    # Actual update form view
    path('<uuid:pk>/update/', views.tournament_update, name='tournament-update'),
    # Confirmation step shown before allowing the update
    path('<uuid:pk>/update/confirm/', views.tournament_update_confirm, name='tournament-update-confirm'),
]