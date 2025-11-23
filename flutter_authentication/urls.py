from django.urls import path
from flutter_authentication.views import login

app_name = 'flutter_authentication'

urlpatterns = [
    path('login/', login, name='login'),
]