from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponseForbidden
from django.views.decorators.http import require_http_methods
from django.db.models import Q, Count
from django.core.paginator import Paginator
from tournaments.models import Tournament, TournamentParticipant
from tournament_registration.models import TournamentRegistration, TeamMember
from game_account.models import GameAccount
from .models import UserAccount
from .forms import RegisterForm, LoginForm, ProfileUpdateForm, CreateOrganizerForm
import json

# ==================== ADMIN DASHBOARD ====================

@login_required
def admin_dashboard(request):
    """Admin dashboard - redirect to manage users by default"""
    if not request.user.is_admin():
        return render(request, '403.html', status=403)
    return redirect('user_account:admin_manage_users')

@login_required
def admin_manage_users(request):
    """Admin page to manage all users"""
    if not request.user.is_admin():
        return render(request, '403.html', status=403)
    # Get admin logged in
    admin = request.user

    # Get filter parameters
    search = request.GET.get('search', '')
    role_filter = request.GET.get('role', '')
    status_filter = request.GET.get('status', '')
    
    # Base queryset
    users = UserAccount.objects.all()
    
    # Apply filters
    if search:
        users = users.filter(
            Q(username__icontains=search) | 
            Q(email__icontains=search) | 
            Q(display_name__icontains=search)
        )
    
    if role_filter:
        users = users.filter(role=role_filter)
    
    if status_filter:
        is_active = status_filter == 'active'
        users = users.filter(is_active=is_active)
    
    # Statistics
    total_users = UserAccount.objects.count()
    
    # Pagination
    paginator = Paginator(users, 10)
    page_number = request.GET.get('page')
    users_page = paginator.get_page(page_number)
    
    context = {
        'admin': admin,
        'users': users_page,
        'total_users': total_users,
        'search': search,
        'role_filter': role_filter,
        'status_filter': status_filter,
    }
    
    return render(request, 'admin/manage_users.html', context)

@login_required
@require_http_methods(["GET", "POST"])
def admin_create_organizer(request):
    """Admin create organizer account"""
    if not request.user.is_admin():
        render(request, '403.html', status=403)
    
    if request.method == 'POST':
        form = CreateOrganizerForm(request.POST)
        
        if form.is_valid():
            user = form.save(commit=False)
            user.role = 'organizer'
            user.save()
            
            messages.success(request, f'Organizer account {user.username} created successfully!')
            return redirect('user_account:admin_manage_users')
    else:
        form = CreateOrganizerForm()
    
    context = {'form': form}
    return render(request, 'admin/create_organizer.html', context)

@login_required
def admin_user_detail(request, user_id):
    """Admin view user details"""
    if not request.user.is_admin():
        render(request, '403.html', status=403)
    
    user = get_object_or_404(UserAccount, id=user_id)
    
    # Get tournaments where user is a participant
    participated_tournaments = Tournament.objects.filter(
        registrations__members__game_account__user=user
    ).distinct().select_related('organizer', 'tournament_format__game')
    
    # Get tournaments organized by this user (if organizer)
    organized_tournaments = Tournament.objects.none()
    if user.role == 'organizer':
        organized_tournaments = Tournament.objects.filter(
            organizer=user
        ).select_related('tournament_format__game')
    
    context = {
        'viewed_user': user,
        'participated_tournaments': participated_tournaments,
        'organized_tournaments': organized_tournaments,
    }
    
    return render(request, 'admin/user_detail.html', context)

@login_required
@require_http_methods(["POST"])
def admin_delete_user(request, user_id):
    """Admin permanently delete user (CASCADE: will delete all their tournaments)"""
    import logging
    import traceback
    
    logger = logging.getLogger(__name__)
    
    if not request.user.is_admin():
        return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)
    
    try:
        user = get_object_or_404(UserAccount, id=user_id)
    except Exception as e:
        logger.error(f'User not found: {str(e)}')
        return JsonResponse({'success': False, 'error': 'User not found'}, status=404)
    
    # Prevent admin from deleting themselves
    if user.id == request.user.id:
        return JsonResponse({'success': False, 'error': 'Cannot delete your own account'}, status=400)
    
    try:
        username = user.username
        user_role = user.role
        
        # Check tournament count before deletion
        tournament_count = 0
        if user_role in ['organizer', 'admin']:
            try:
                tournament_count = Tournament.objects.filter(organizer=user).count()
                logger.info(f'User {username} has {tournament_count} tournaments')
            except Exception as e:
                logger.error(f'Error counting tournaments: {str(e)}')
        
        # Attempt to delete the user
        logger.info(f'Attempting to delete user: {username} (role: {user_role})')
        user.delete()
        logger.info(f'Successfully deleted user: {username}')
        
        # Success message
        if tournament_count > 0:
            message = f'User {username} and their {tournament_count} tournament(s) have been permanently deleted'
        else:
            message = f'User {username} has been permanently deleted'
        
        return JsonResponse({
            'success': True, 
            'message': message
        })
        
    except Exception as e:
        # Detailed error logging
        error_trace = traceback.format_exc()
        logger.error(f'Error deleting user {username}:')
        logger.error(error_trace)
        
        return JsonResponse({
            'success': False, 
            'error': f'Database error: {str(e)}'
        }, status=500)

@login_required
def admin_manage_tournaments(request):
    """Admin page to manage all tournaments"""
    if not request.user.is_admin():
        return HttpResponseForbidden("You don't have permission to access this page.")
    # Get admin logged in
    admin = request.user

    # Get filter parameters
    search = request.GET.get('search', '')
    status_filter = request.GET.get('status', '')

    # Base queryset with related data
    tournaments = Tournament.objects.select_related(
        'organizer',
        'tournament_format__game'
    ).annotate(
        registered_teams_count=Count('registrations', distinct=True)
    )
    
    # Apply filters
    if search:
        tournaments = tournaments.filter(
            Q(tournament_name__icontains=search) | 
            Q(organizer__username__icontains=search) |
            Q(tournament_format__game__name__icontains=search)
        )
    
    # Note: Tournament model tidak memiliki field 'status' berdasarkan models.py yang diberikan
    # Jika ingin filter status, bisa berdasarkan tournament_date
    if status_filter:
        from django.utils import timezone
        today = timezone.localdate()
        
        if status_filter == 'upcoming':
            tournaments = tournaments.filter(tournament_date__gte=today)
        elif status_filter == 'past':
            tournaments = tournaments.filter(tournament_date__lt=today)
        elif status_filter == 'tba':
            tournaments = tournaments.filter(tournament_date__isnull=True)
    
    # Statistics
    total_tournaments = Tournament.objects.count()
    
    # Count tournaments by date (as proxy for active/upcoming)
    from django.utils import timezone
    today = timezone.localdate()
    active_tournaments = Tournament.objects.filter(
        tournament_date__gte=today
    ).count()
    
    # Count unique participants across all tournaments
    total_participants = UserAccount.objects.filter(
        gameaccount__joined_teams__isnull=False
    ).distinct().count()
    
    # Pagination
    paginator = Paginator(tournaments, 10)
    page_number = request.GET.get('page')
    tournaments_page = paginator.get_page(page_number)
    
    context = {
        'admin': admin,
        'tournaments': tournaments_page,
        'total_tournaments': total_tournaments, 
        'active_tournaments': active_tournaments,
        'total_participants': total_participants,
        'search': search,
        'status_filter': status_filter,
    }
    
    return render(request, 'admin/manage_tournaments.html', context)

@login_required
def admin_tournament_detail(request, tournament_id):
    """Admin view tournament details"""
    if not request.user.is_admin():
        return HttpResponseForbidden("You don't have permission to access this page.")
    
    tournament = get_object_or_404(
        Tournament.objects.select_related(
            'organizer', 
            'tournament_format__game'
        ),
        id=tournament_id
    )
    
    # Get all participants with their participation details
    participant_records = TournamentParticipant.objects.filter(
        tournament=tournament
    ).select_related('participant').order_by('-registered_at')
    
    # Get all tournament registrations (teams)
    registrations = TournamentRegistration.objects.filter(
        tournament=tournament
    ).prefetch_related('members__game_account__user')
    
    context = {
        'tournament': tournament,
        'participant_records': participant_records,
        'registrations': registrations,
        'participants_count': participant_records.count(),
    }
    
    return render(request, 'admin/tournament_detail.html', context)

# ==================== AUTHENTICATION ====================
def login_view(request):
    """User login"""
    if request.user.is_authenticated:
        return redirect('tournaments:show_main')
    
    if request.method == 'POST':
        form = LoginForm(request.POST)
        if form.is_valid():
            username_or_email = form.cleaned_data['username_or_email']
            password = form.cleaned_data['password']
            remember_me = form.cleaned_data.get('remember_me', False)
            
            # Try to find user by username or email
            user = None
            if '@' in username_or_email:
                try:
                    user_account = UserAccount.objects.get(email=username_or_email, is_active=True)
                    user = authenticate(request, username=user_account.username, password=password)
                except UserAccount.DoesNotExist:
                    pass
            else:
                user = authenticate(request, username=username_or_email, password=password)
            
            if user is not None:
                login(request, user)
                
                # Handle remember me
                if not remember_me:
                    request.session.set_expiry(0)  # Session expires when browser closes
                
                messages.success(request, f'Welcome back, {user.display_name}!')
                
                # Redirect based on role
                next_url = request.GET.get('next')
                if next_url:
                    return redirect(next_url)
                elif user.is_admin():
                    return redirect('tournaments:show_main')
                else:
                    return redirect('tournaments:show_main')
            else:
                messages.error(request, 'Invalid username/email or password')
    else:
        form = LoginForm()
    
    context = {'form': form}
    return render(request, 'login.html', context)

def register_view(request):
    """User registration - Step 1: Basic info"""
    if request.user.is_authenticated:
        return redirect('user_account:login')
    
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, 'Account created successfully! Please complete your profile.')
            return redirect('user_account:complete_profile')
    else:
        form = RegisterForm()
    
    context = {'form': form}
    return render(request, 'register.html', context)

@login_required
def complete_profile_view(request):
    """User registration - Step 2: Complete profile with avatar"""
    if request.method == 'POST':
        profile_image = request.POST.get('profile_image')
        
        user = request.user
        user.profile_image = profile_image
        user.save()
        
        messages.success(request, 'Profile completed successfully!')
        logout(request)
        return redirect('user_account:login')
    
    context = {
        'avatar_choices': ['avatar1', 'avatar2', 'avatar3']
    }
    return render(request, 'complete_profile.html', context)

@login_required
def logout_view(request):
    """User logout"""
    logout(request)
    messages.success(request, 'You have been logged out successfully.')
    return redirect('user_account:login')

# ==================== USER PROFILE ====================

@login_required
def profile_view(request):
    """User profile page"""
    user = request.user
    
    # Get tournaments where user is a participant
    tournaments = Tournament.objects.filter(
        registrations__members__game_account__user=user
    ).select_related('organizer', 'tournament_format__game')
    context = {
        'user': user,
        'tournaments': tournaments,
    }
    
    return render(request, 'profile.html', context)

@login_required
def update_profile_view(request):
    """Update user profile"""
    if request.method == 'POST':
        form = ProfileUpdateForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Profile updated successfully!')
            return redirect('user_account:profile')
    else:
        form = ProfileUpdateForm(instance=request.user)
    
    context = {'form': form}
    return render(request, 'update_profile.html', context)

@login_required
@require_http_methods(["POST"])
def delete_account_view(request):
    """Soft delete user account"""
    user = request.user
    user.soft_delete()
    logout(request)
    messages.success(request, 'Your account has been deleted successfully.')
    return redirect('user_account:login')
