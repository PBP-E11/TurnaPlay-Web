from django.urls import path
from . import views

app_name = 'flutter_team'

urlpatterns = [
    path('create/', views.create_team, name='create_team'),
    path('details/', views.get_team, name='get_team'),
    path('update/', views.update_team, name='update_team'),
    path('delete/', views.delete_team, name='delete_team'),
    path('member/join/', views.join_member, name='join_member'),
    path('member/update/', views.update_member, name='update_member'),
    path('member/delete/', views.delete_member, name='delete_member'),
]
