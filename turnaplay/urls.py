"""
URL configuration for turnaplay project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    # 1. Path for Flutter Auth
    path('auth/', include('flutter_authentication.urls')),
    # 2. Path for the Django Admin
    path('django-admin/', admin.site.urls),
    
    # 3. Unique prefix for each app
    path('accounts/', include('user_account.urls')),
    path('game-accounts/', include('game_account.urls')),
    path('invites/', include('tournament_invite.urls')),
    path('team/', include('tournament_registration.urls')),
    
    # 4. Main app (with the homepage) is LAST
    # This will handle the root URL ('/') and any other paths
    # not matched by the apps above (e.g., /api/tournaments/)
    path('', include('tournaments.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
