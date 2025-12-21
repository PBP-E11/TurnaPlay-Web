from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth import get_user_model
import json

User = get_user_model()

@csrf_exempt
def login(request):
    username = request.POST['username']
    password = request.POST['password']
    user = authenticate(username=username, password=password)
    if user is not None:
        if user.is_active:
            auth_login(request, user)
            # Login status successful.
            return JsonResponse({
                "username": user.username,
                "status": True,
                "message": "Login successful!",
                "id": user.id
                # Add other data if you want to send data to Flutter.
            }, status=200)
        else:
            return JsonResponse({
                "status": False,
                "message": "Login failed, account is disabled."
            }, status=401)

    else:
        return JsonResponse({
            "status": False,
            "message": "Login failed, please check your username or password."
        }, status=401)
    
@csrf_exempt
def register(request):
    # Only accept POST for registration
    if request.method != 'POST':
        return JsonResponse({
            "status": False,
            "message": "Invalid request method."
        }, status=400)

    # Parse JSON body
    try:
        data = json.loads(request.body)
    except Exception as e:
        return JsonResponse({
            "status": False,
            "message": "Invalid JSON body."
        }, status=400)

    username = data.get('username')
    email = data.get('email')
    password1 = data.get('password1')
    password2 = data.get('password2')

    # Basic validation
    if not username or not password1 or not password2:
        return JsonResponse({"status": False, "message": "Username and passwords are required."}, status=400)

    if password1 != password2:
        return JsonResponse({"status": False, "message": "Passwords do not match."}, status=400)

    # Check if the username is already taken
    if User.objects.filter(username=username).exists():
        return JsonResponse({"status": False, "message": "Username already exists."}, status=400)

    # Email is required by the custom user model
    if not email:
        return JsonResponse({"status": False, "message": "Email is required for registration."}, status=400)

    # Create the new user. Use manager.create_user if provided, otherwise set password manually.
    try:
        manager = User.objects
        if hasattr(manager, 'create_user'):
            # custom manager expects (username, email, password)
            user = manager.create_user(username=username, email=email, password=password1)
        else:
            # Fallback for models without a create_user manager
            user = User(username=username, email=email)
            user.set_password(password1)
            user.save()
    except Exception as e:
        return JsonResponse({"status": False, "message": f"Failed to create user: {str(e)}"}, status=500)

    return JsonResponse({"username": user.username, "status": 'success', "message": "User created successfully!"}, status=200)
    
@csrf_exempt
def logout(request):
    username = request.user.username
    try:
        auth_logout(request)
        return JsonResponse({
            "username": username,
            "status": True,
            "message": "Logged out successfully!"
        }, status=200)
    except Exception as e:
        return JsonResponse({
            "status": False,
            "message": f"Logout failed: {str(e)}"
        }, status=401)