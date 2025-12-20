from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth import get_user_model
import json
from django.core.paginator import Paginator
from django.db.models import Q, Count
from datetime import datetime, timedelta

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
    
def is_admin(user):
    return user.is_authenticated and user.role == 'admin'


@csrf_exempt
def dashboard_stats(request):
    if request.method != 'GET':
        return JsonResponse({
            "status": False,
            "message": "Invalid method"
        }, status=405)
    
    # Check admin authentication
    if not is_admin(request.user):
        return JsonResponse({
            "status": False,
            "message": "Unauthorized. Admin access required."
        }, status=403)
    
    try:
        # Total users
        total_users = User.objects.filter(is_active=True).count()
        
        # Users by role
        role_breakdown = User.objects.filter(is_active=True).values('role').annotate(
            count=Count('role')
        )
        
        # Convert to dict
        roles = {item['role']: item['count'] for item in role_breakdown}
        
        return JsonResponse({
            "status": True,
            "data": {
                "total_users": total_users,
                "users_by_role": {
                    "user": roles.get('user', 0),
                    "organizer": roles.get('organizer', 0),
                    "admin": roles.get('admin', 0)
                },
            }
        }, status=200)
        
    except Exception as e:
        return JsonResponse({
            "status": False,
            "message": f"Error fetching statistics: {str(e)}"
        }, status=500)


@csrf_exempt
def list_users(request):
    if request.method != 'GET':
        return JsonResponse({
            "status": False,
            "message": "Invalid method"
        }, status=405)
    
    # Check admin authentication
    if not is_admin(request.user):
        return JsonResponse({
            "status": False,
            "message": "Unauthorized. Admin access required."
        }, status=403)
    
    try:
        # Start with all users query
        users_query = User.objects.all()
        
        # Filter by role
        role_filter = request.GET.get('role', None)
        if role_filter and role_filter in ['user', 'organizer', 'admin']:
            users_query = users_query.filter(role=role_filter)
        
        # Search by username or display_name
        search_query = request.GET.get('search', '').strip()
        if search_query:
            users_query = users_query.filter(
                Q(username__icontains=search_query) |
                Q(display_name__icontains=search_query) |
                Q(email__icontains=search_query)
            )
        
        # Order by date_joined (newest first)
        users_query = users_query.order_by('-date_joined')
        
        # Pagination
        page = int(request.GET.get('page', 1))
        page_size = min(int(request.GET.get('page_size', 10)), 100)  # Max 100 items per page
        
        paginator = Paginator(users_query, page_size)
        users_page = paginator.get_page(page)
        
        # Serialize user data
        users_data = []
        for user in users_page:
            users_data.append({
                "id": str(user.id),
                "username": user.username,
                "email": user.email,
                "display_name": user.display_name,
                "role": user.role,
                "profile_image": user.profile_image,
                "is_active": user.is_active,
                "date_joined": user.date_joined.isoformat() if user.date_joined else None,
                "last_login": user.last_login.isoformat() if user.last_login else None
            })
        
        return JsonResponse({
            "status": True,
            "data": {
                "users": users_data,
                "pagination": {
                    "current_page": users_page.number,
                    "total_pages": paginator.num_pages,
                    "total_items": paginator.count,
                    "page_size": page_size,
                    "has_next": users_page.has_next(),
                    "has_previous": users_page.has_previous()
                }
            }
        }, status=200)
        
    except ValueError as e:
        return JsonResponse({
            "status": False,
            "message": "Invalid pagination parameters"
        }, status=400)
    except Exception as e:
        return JsonResponse({
            "status": False,
            "message": f"Error fetching users: {str(e)}"
        }, status=500)


@csrf_exempt
def create_organizer(request):
    if request.method != 'POST':
        return JsonResponse({
            "status": False,
            "message": "Invalid method"
        }, status=405)
    
    # Check admin authentication
    if not is_admin(request.user):
        return JsonResponse({
            "status": False,
            "message": "Unauthorized. Admin access required."
        }, status=403)
    
    # Parse JSON body
    try:
        data = json.loads(request.body)
    except Exception as e:
        return JsonResponse({
            "status": False,
            "message": "Invalid JSON body"
        }, status=400)
    
    # Extract fields
    username = data.get('username', '').strip()
    email = data.get('email', '').strip()
    password = data.get('password', '').strip()
    display_name = data.get('display_name', '').strip()
    
    # Validation
    if not username or not email or not password:
        return JsonResponse({
            "status": False,
            "message": "Username, email, and password are required"
        }, status=400)
    
    # Check username uniqueness
    if User.objects.filter(username=username, is_active=True).exists():
        return JsonResponse({
            "status": False,
            "message": "Username already exists"
        }, status=400)
    
    # Check email uniqueness
    if User.objects.filter(email=email, is_active=True).exists():
        return JsonResponse({
            "status": False,
            "message": "Email already exists"
        }, status=400)
    
    # Password strength validation
    if len(password) < 8:
        return JsonResponse({
            "status": False,
            "message": "Password must be at least 8 characters long"
        }, status=400)
    
    # Create organizer here
    try:
        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            display_name=display_name if display_name else username,
            role='organizer'  # organizer
        )
        
        return JsonResponse({
            "status": True,
            "message": "Organizer account created successfully",
            "data": {
                "id": str(user.id),
                "username": user.username,
                "email": user.email,
                "display_name": user.display_name,
                "role": user.role
            }
        }, status=201)
        
    except Exception as e:
        return JsonResponse({
            "status": False,
            "message": f"Failed to create organizer: {str(e)}"
        }, status=500)


@csrf_exempt
def user_detail(request, user_id):
    if request.method != 'GET':
        return JsonResponse({
            "status": False,
            "message": "Invalid method"
        }, status=405)
    
    # Check admin authentication
    if not is_admin(request.user):
        return JsonResponse({
            "status": False,
            "message": "Unauthorized. Admin access required."
        }, status=403)
    
    try:
        # Get user by ID
        user = User.objects.get(id=user_id)
        
        # Data user
        user_data = {
            "id": str(user.id),
            "username": user.username,
            "email": user.email,
            "display_name": user.display_name,
            "role": user.role,
            "profile_image": user.profile_image,
            "is_active": user.is_active,
            "date_joined": user.date_joined.isoformat() if user.date_joined else None,
            "last_login": user.last_login.isoformat() if user.last_login else None,
            
            # Additional statistics (to be implemented with related models)
            # "tournaments_created": user.tournament_set.count() if user.is_organizer() else 0,
            # "tournaments_participated": user.tournamentparticipant_set.count(),
            # "game_accounts_count": user.gameaccount_set.count(),
        }
        
        return JsonResponse({
            "status": True,
            "data": user_data
        }, status=200)
        
    except User.DoesNotExist:
        return JsonResponse({
            "status": False,
            "message": "User not found"
        }, status=404)
    except Exception as e:
        return JsonResponse({
            "status": False,
            "message": f"Error fetching user details: {str(e)}"
        }, status=500)


@csrf_exempt
def delete_user(request, user_id):
    if request.method != 'DELETE':
        return JsonResponse({
            "status": False,
            "message": "Invalid method"
        }, status=405)
    
    # Check admin authentication
    if not is_admin(request.user):
        return JsonResponse({
            "status": False,
            "message": "Unauthorized. Admin access required."
        }, status=403)
    
    try:
        # Get user by ID
        user = User.objects.get(id=user_id)
        
        # Prevent self-deletion
        if user.id == request.user.id:
            return JsonResponse({
                "status": False,
                "message": "Cannot delete your own account"
            }, status=400)
        
        # Delete
        username = user.username
        user.delete()
        
        return JsonResponse({
            "status": True,
            "message": f"User {username} has been deleted successfully"
        }, status=200)
        
    except User.DoesNotExist:
        return JsonResponse({
            "status": False,
            "message": "User not found"
        }, status=404)
    except Exception as e:
        return JsonResponse({
            "status": False,
            "message": f"Error deleting user: {str(e)}"
        }, status=500)