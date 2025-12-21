from django.urls import path
from . import views

app_name = 'flutter_tournaments'

urlpatterns = [
    path('create-tournament/', views.create_tournament_flutter, name='create_tournament_flutter'),
    path('games/', views.show_games_json, name='show-games-json'),
    path('formats/', views.show_formats_json, name='show-formats-json'),
    path('list/', views.get_tournaments_paginated, name='tournament-list'),
]