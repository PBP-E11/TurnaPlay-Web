from django.urls import path
from . import views

app_name = 'flutter_user_account'

urlpatterns = [
    path('login/', views.login, name='login'),
    path('register/', views.register, name='register'),
    path('logout/', views.logout, name='logout'),
    # Dashboard Admin - User
    path('dashboard/stats/', views.dashboard_stats, name='dashboard_stats'),
    path('dashboard/users/',  views.list_users, name='list_users'),
    path('dashboard/users/create-organizer/',  views.create_organizer, name='create_organizer'),
    path('dashboard/users/<uuid:user_id>/',  views.user_detail, name='user_detail'),
    path('dashboard/users/delete/',  views.delete_user, name='delete_user'),
    path('dashboard/users/update/', views.update_user, name='update_user'),
    # Dashboard Admin - Tournaments
    path('dashboard/tournaments/', views.list_tournaments, name='list_tournaments'),
    path('dashboard/tournaments/<uuid:tournament_id>/', views.tournament_detail, name='tournament_detail'),
    path('dashboard/tournaments/delete/', views.delete_tournament, name='delete_tournament'),

    path('get_user_tournaments/', views.get_user_tournaments, name='get_user_tournaments'),
    path('dashboard/tournaments/update/', views.update_tournament, name='update_tournament'),
]