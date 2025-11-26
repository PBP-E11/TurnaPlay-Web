from django.urls import path, include
from . import views

app_name = 'tournament_invite'

urlpatterns = [
    # pages
    path('', views.invite_list, name='invite-list'),
    path('create/', views.create_invite, name='create-invite'),

    # ajax poll
    path('check/', views.check_new_invite, name='check-new-invite'),

    # JSON API (AJAX)
    path('api/accept/', views.api_accept_invite, name='api-accept'),
    path('api/reject/', views.api_reject_invite, name='api-reject'),
    path('api/cancel/', views.api_cancel_invite, name='api-cancel'),   
]