from django.urls import path
from . import api_views

app_name = "tournament_invite_api"

urlpatterns = [
    path("incoming/", api_views.api_list_incoming, name="incoming"),
    path("outgoing/", api_views.api_list_outgoing, name="outgoing"),
    path("respond/", api_views.api_respond_invite, name="respond"),
]