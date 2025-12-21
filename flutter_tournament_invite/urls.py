from django.urls import path
from . import views

app_name = "flutter_tournament_invite"

urlpatterns = [
    path("incoming/", views.api_list_incoming, name="incoming"),
    path("outgoing/", views.api_list_outgoing, name="outgoing"),
    path("respond/", views.api_respond_invite, name="respond"),
    path("send/", views.send_invite, name="send"),
    path("cancel/", views.api_cancel_invite, name="cancel"),
    path("new/", views.api_new_invites, name="new"),
]