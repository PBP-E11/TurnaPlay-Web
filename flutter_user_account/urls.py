from django.urls import path
from . import views

app_name = 'flutter_user_account'

urlpatterns = [
    path('login/', views.login, name='login'),
    path('register/', views.register, name='register'),
    # Dashboard Admin
    path('dashboard/stats/', views.dashboard_stats, name='dashboard_stats'),
    path('dashboard/users/',  views.list_users, name='list_users'),
    path('dashboard/users/create-organizer/',  views.create_organizer, name='create_organizer'),
    path('dashboard/users/<uuid:user_id>/',  views.user_detail, name='user_detail'),
    path('dashboard/users/<uuid:user_id>/delete/',  views.delete_user, name='delete_user'),
]