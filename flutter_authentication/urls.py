from django.urls import path
from flutter_authentication.views import login, register

app_name = 'flutter_authentication'

urlpatterns = [
    path('login/', login, name='login'),
    path('register/', register, name='register'),
]