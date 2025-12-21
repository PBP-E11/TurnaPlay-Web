from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth import get_user_model
import json
from django.core.paginator import Paginator
from django.db.models import Q, Count
from datetime import datetime, timedelta
from tournament_registration.models import TournamentRegistration
from tournaments.models import Tournament, TournamentFormat, Game
from user_account.models import UserAccount
from django.utils import timezone
from django.views.decorators.http import require_http_methods

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
                "id": user.id,
                # Add other data if you want to send data to Flutter.
                "role": getattr(user, 'role', None),
                "is_admin": getattr(user, 'is_admin', lambda: False)()
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

        # Get tournaments where user is a participant
        participated_tournaments = Tournament.objects.filter(
            registrations__members__game_account__user=user
        ).distinct().select_related('organizer', 'tournament_format__game')
        participated_tournaments_data = []
        for tournament in participated_tournaments:
            # Get all tournament registrations (teams)
            registrations = TournamentRegistration.objects.filter(
                tournament=tournament
            ).prefetch_related('members__game_account__user')

            registrations_data = []
            for registration in registrations:
                # Get team members
                members_data = []
                for member in registration.members.all():
                    members_data.append({
                        "id": str(member.id),
                        "is_leader": member.is_leader,
                        "game_account": {
                            "id": str(member.game_account.id) if member.game_account else None,
                            "ingame_name": member.game_account.ingame_name if member.game_account else None,
                            "user": {
                                "id": str(member.game_account.user.id) if member.game_account and member.game_account.user else None,
                                "username": member.game_account.user.username if member.game_account and member.game_account.user else None,
                                "display_name": member.game_account.user.display_name if member.game_account and member.game_account.user else None,
                            } if member.game_account and member.game_account.user else None
                        } if member.game_account else None
                    })
                
                registrations_data.append({
                    "id": str(registration.id),
                    "team_name": registration.team_name,
                    "created_at": registration.created_at.isoformat() if hasattr(registration, 'created_at') and registration.created_at else None,
                    "members": members_data,
                    "members_count": len(members_data)
                })
            participated_tournaments_data.append({
                "id": str(tournament.id),
                "tournament_name": tournament.tournament_name,
                "description": tournament.description,
                "tournament_date": tournament.tournament_date.isoformat() if tournament.tournament_date else None,
                "prize_pool": tournament.prize_pool,
                "banner": tournament.banner,
                "team_maximum_count": tournament.team_maximum_count,
                "status": tournament.status,
                "participants_count": tournament.participants_count(),
                "registrations": registrations_data,
                "registrations_count": len(registrations_data),
                "created_at": tournament.created_at.isoformat(),
                "updated_at": tournament.updated_at.isoformat(),
                
                # Tournament Format info
                "tournament_format": {
                    "id": str(tournament.tournament_format.id),
                    "name": tournament.tournament_format.name,
                    "team_size": tournament.tournament_format.team_size,
                    "game": {
                        "id": str(tournament.tournament_format.game.id),
                        "name": tournament.tournament_format.game.name
                    }
                },
                
                # Organizer info
                "organizer": {
                    "id": str(tournament.organizer.id) if tournament.organizer else None,
                    "username": tournament.organizer.username if tournament.organizer else None,
                    "display_name": tournament.organizer.display_name if tournament.organizer else None
                } if tournament.organizer else None
            })

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
            "tournaments": participated_tournaments_data,
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
def delete_user(request):
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
    
    try:
        # Get user by ID
        data = json.loads(request.body)
        user_id = data.get("user_id")

        user = User.objects.get(id=user_id)
        
        # Prevent self-deletion
        if user.id == request.user.id:
            return JsonResponse({
                "status": False,
                "message": "Cannot delete your own account"
            }, status=400)
        
        # Delete
        user.delete()
        
        return JsonResponse({
            "status": True,
            "message": 'User deleted successfully'
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

@csrf_exempt
def list_tournaments(request):
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
        # all tournaments query
        tournaments_query = Tournament.objects.select_related(
            'tournament_format',
            'tournament_format__game',
            'organizer'
        ).prefetch_related('participants').all()
        
        # Filter by game
        game_filter = request.GET.get('game', None)
        if game_filter:
            tournaments_query = tournaments_query.filter(
                tournament_format__game_id=game_filter
            )
        
        # Filter by status
        status_filter = request.GET.get('status', None)
        if status_filter:
            today = timezone.localdate()
            
            if status_filter == 'upcoming':
                tournaments_query = tournaments_query.filter(tournament_date__gte=today)
            elif status_filter == 'past':
                tournaments_query = tournaments_query.filter(tournament_date__lt=today)
            elif status_filter == 'tba':
                tournaments_query = tournaments_query.filter(tournament_date__isnull=True)
        
        # Search by tournament name or description
        search_query = request.GET.get('search', '').strip()
        if search_query:
            tournaments = tournaments.filter(
                Q(tournament_name__icontains=search_query) | 
                Q(organizer__username__icontains=search_query) |
                Q(tournament_format__game__name__icontains=search_query)
            )
        
        # Calculate statistics BEFORE pagination        
        total_tournaments = tournaments_query.count()
        today = timezone.localdate()
        active_tournaments = Tournament.objects.filter(
            tournament_date__gte=today
        ).count()

        # Count unique participants across all tournaments
        total_participants = UserAccount.objects.filter(
            gameaccount__joined_teams__isnull=False
        ).distinct().count()
        
        # Pagination
        page = int(request.GET.get('page', 1))
        page_size = min(int(request.GET.get('page_size', 10)), 100)
        
        paginator = Paginator(tournaments_query, page_size)
        tournaments_page = paginator.get_page(page)
        
        # Serialize tournament data
        tournaments_data = []
        for tournament in tournaments_page:
            # Get all tournament registrations (teams)
            registrations = TournamentRegistration.objects.filter(
                tournament=tournament
            ).prefetch_related('members__game_account__user')

            registrations_data = []
            for registration in registrations:
                # Get team members
                members_data = []
                for member in registration.members.all():
                    members_data.append({
                        "id": str(member.id),
                        "is_leader": member.is_leader,
                        "game_account": {
                            "id": str(member.game_account.id) if member.game_account else None,
                            "ingame_name": member.game_account.ingame_name if member.game_account else None,
                            "user": {
                                "id": str(member.game_account.user.id) if member.game_account and member.game_account.user else None,
                                "username": member.game_account.user.username if member.game_account and member.game_account.user else None,
                                "display_name": member.game_account.user.display_name if member.game_account and member.game_account.user else None,
                            } if member.game_account and member.game_account.user else None
                        } if member.game_account else None
                    })
                
                registrations_data.append({
                    "id": str(registration.id),
                    "team_name": registration.team_name,
                    "created_at": registration.created_at.isoformat() if hasattr(registration, 'created_at') and registration.created_at else None,
                    "members": members_data,
                    "members_count": len(members_data)
                })
            tournaments_data.append({
                "id": str(tournament.id),
                "tournament_name": tournament.tournament_name,
                "description": tournament.description,
                "tournament_date": tournament.tournament_date.isoformat() if tournament.tournament_date else None,
                "prize_pool": tournament.prize_pool,
                "banner": tournament.banner,
                "team_maximum_count": tournament.team_maximum_count,
                "status": tournament.status,
                "participants_count": tournament.participants_count(),
                "registrations": registrations_data,
                "registrations_count": len(registrations_data),
                "created_at": tournament.created_at.isoformat(),
                "updated_at": tournament.updated_at.isoformat(),
                
                # Tournament Format info
                "tournament_format": {
                    "id": str(tournament.tournament_format.id),
                    "name": tournament.tournament_format.name,
                    "team_size": tournament.tournament_format.team_size,
                    "game": {
                        "id": str(tournament.tournament_format.game.id),
                        "name": tournament.tournament_format.game.name
                    }
                },
                
                # Organizer info
                "organizer": {
                    "id": str(tournament.organizer.id) if tournament.organizer else None,
                    "username": tournament.organizer.username if tournament.organizer else None,
                    "display_name": tournament.organizer.display_name if tournament.organizer else None
                } if tournament.organizer else None
            })
        
        return JsonResponse({
            "status": True,
            "data": {
                "tournaments": tournaments_data,
                "pagination": {
                    "current_page": tournaments_page.number,
                    "total_pages": paginator.num_pages,
                    "total_items": paginator.count,
                    "page_size": page_size,
                    "has_next": tournaments_page.has_next(),
                    "has_previous": tournaments_page.has_previous()
                },
                "statistics": {
                    "total_tournaments": total_tournaments,
                    "active_tournaments": active_tournaments,
                    "total_participant": total_participants,
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
            "message": f"Error fetching tournaments: {str(e)}"
        }, status=500)


@csrf_exempt
def tournament_detail(request, tournament_id):
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
        # Get tournament with related data
        tournament = get_object_or_404(
            Tournament.objects.select_related(
                'organizer', 
                'tournament_format__game'
            ),
            id=tournament_id
        )
        
        # Get participants data
        participants_data = []
        for participant_record in tournament.participant_records.all():
            participants_data.append({
                "id": str(participant_record.id),
                "user": {
                    "id": str(participant_record.participant.id),
                    "username": participant_record.participant.username,
                    "display_name": participant_record.participant.display_name,
                    "email": participant_record.participant.email,
                    "profile_image": participant_record.participant.profile_image
                },
                "status": participant_record.status,
                "team_name": participant_record.team_name,
                "registered_at": participant_record.registered_at.isoformat()
            })
        
        # Get all tournament registrations (teams)
        registrations = TournamentRegistration.objects.filter(
            tournament=tournament
        ).prefetch_related('members__game_account__user')

        registrations_data = []
        for registration in registrations:
            # Get team members
            members_data = []
            for member in registration.members.all():
                members_data.append({
                    "id": str(member.id),
                    "is_leader": member.is_leader,
                    "game_account": {
                        "id": str(member.game_account.id) if member.game_account else None,
                        "ingame_name": member.game_account.ingame_name if member.game_account else None,
                        "user": {
                            "id": str(member.game_account.user.id) if member.game_account and member.game_account.user else None,
                            "username": member.game_account.user.username if member.game_account and member.game_account.user else None,
                            "display_name": member.game_account.user.display_name if member.game_account and member.game_account.user else None,
                        } if member.game_account and member.game_account.user else None
                    } if member.game_account else None
                })
            
            registrations_data.append({
                "id": str(registration.id),
                "team_name": registration.team_name,
                "created_at": registration.created_at.isoformat() if hasattr(registration, 'created_at') and registration.created_at else None,
                "members": members_data,
                "members_count": len(members_data)
            })

        # Prepare detailed tournament data
        tournament_data = {
            "id": str(tournament.id),
            "tournament_name": tournament.tournament_name,
            "description": tournament.description,
            "tournament_date": tournament.tournament_date.isoformat() if tournament.tournament_date else None,
            "prize_pool": tournament.prize_pool,
            "banner": tournament.banner,
            "team_maximum_count": tournament.team_maximum_count,
            "status": tournament.status,
            "created_at": tournament.created_at.isoformat(),
            "updated_at": tournament.updated_at.isoformat(),
            
            # Tournament Format
            "tournament_format": {
                "id": str(tournament.tournament_format.id),
                "name": tournament.tournament_format.name,
                "team_size": tournament.tournament_format.team_size,
                "game": {
                    "id": str(tournament.tournament_format.game.id),
                    "name": tournament.tournament_format.game.name
                }
            },
            
            # Registration team
            "registrations": registrations_data,
            "registrations_count": len(registrations_data),

            # Organizer
            "organizer": {
                "id": str(tournament.organizer.id) if tournament.organizer else None,
                "username": tournament.organizer.username if tournament.organizer else None,
                "display_name": tournament.organizer.display_name if tournament.organizer else None,
                "email": tournament.organizer.email if tournament.organizer else None,
                "role": tournament.organizer.role if tournament.organizer else None
            } if tournament.organizer else None,
            
            # Participants
            "participants": participants_data,
        }
        
        return JsonResponse({
            "status": True,
            "data": tournament_data
        }, status=200)
        
    except Tournament.DoesNotExist:
        return JsonResponse({
            "status": False,
            "message": "Tournament not found"
        }, status=404)
    except Exception as e:
        return JsonResponse({
            "status": False,
            "message": f"Error fetching tournament details: {str(e)}"
        }, status=500)


@csrf_exempt
def delete_tournament(request):
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
    
    try:
        # Get tournament
        data = json.loads(request.body)
        tournament_id = data.get('tournament_id')
        
        tournament = Tournament.objects.get(id=tournament_id)
        tournament_name = tournament.tournament_name
        
        # Check if tournament has participants
        participant_count = tournament.participants_count()
        
        # Delete tournament
        # This will CASCADE delete all participant records
        tournament.delete()
        
        return JsonResponse({
            "status": True,
            "message": f"Tournament '{tournament_name}' has been deleted successfully",
            "deleted_participants": participant_count
        }, status=200)
        
    except Tournament.DoesNotExist:
        return JsonResponse({
            "status": False,
            "message": "Tournament not found"
        }, status=404)
    except Exception as e:
        return JsonResponse({
            "status": False,
            "message": f"Error deleting tournament: {str(e)}"
        }, status=500)
    
@csrf_exempt
def update_user(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            user_id = data.get('user_id')
            
            user = UserAccount.objects.get(id=user_id)
            
            # Update fields (username tidak diupdate)
            user.email = data.get('email', user.email)
            user.display_name = data.get('display_name', user.display_name)
            user.role = data.get('role', user.role)
            user.is_active = data.get('is_active', user.is_active)
            
            user.save()
            
            return JsonResponse({
                'status': True,
                'message': 'User updated successfully',
                'data': {
                    'id': str(user.id),
                    'username': user.username,
                    'email': user.email,
                    'display_name': user.display_name,
                    'role': user.role,
                    'is_active': user.is_active,
                }
            })
            
        except UserAccount.DoesNotExist:
            return JsonResponse({'status': False, 'message': 'User not found'}, status=404)
        except Exception as e:
            return JsonResponse({'status': False, 'message': str(e)}, status=500)
    
    return JsonResponse({'status': False, 'message': 'Invalid method'}, status=405)


# UPDATE TOURNAMENT
@csrf_exempt
def update_tournament(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            tournament_id = data.get('tournament_id')
            
            tournament = Tournament.objects.get(id=tournament_id)
            
            # Update fields
            tournament.tournament_name = data.get('tournament_name', tournament.tournament_name)
            tournament.description = data.get('description', tournament.description)
            tournament.prize_pool = data.get('prize_pool', tournament.prize_pool)
            tournament.team_maximum_count = data.get('team_maximum_count', tournament.team_maximum_count)
            
            # Update date if provided
            if data.get('tournament_date'):
                tournament.tournament_date = datetime.strptime(
                    data.get('tournament_date'), 
                    '%Y-%m-%d'
                ).date()
            
            tournament.save()
            
            return JsonResponse({
                'status': True,
                'message': 'Tournament updated successfully',
                'data': {
                    'id': str(tournament.id),
                    'tournament_name': tournament.tournament_name,
                    'description': tournament.description,
                    'prize_pool': tournament.prize_pool,
                    'team_maximum_count': tournament.team_maximum_count,
                    'tournament_date': tournament.tournament_date.isoformat() if tournament.tournament_date else None,
                }
            })
            
        except Tournament.DoesNotExist:
            return JsonResponse({'status': False, 'message': 'Tournament not found'}, status=404)
        except Exception as e:
            return JsonResponse({'status': False, 'message': str(e)}, status=500)
    
    return JsonResponse({'status': False, 'message': 'Invalid method'}, status=405)