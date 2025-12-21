from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json
from django.utils.html import strip_tags
from django.apps import apps
from tournaments.models import Tournament, TournamentFormat, Game
from django.utils.dateparse import parse_date
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404

@csrf_exempt
def create_tournament_flutter(request):
    if request.method == 'POST':
        # Verify user is logged in
        if not request.user.is_authenticated:
            return JsonResponse({
                "status": "error", 
                "message": "You must be logged in to create a tournament."
            }, status=401)

        try:
            # Get data from request.POST (standard form-data)
            name = request.POST.get("tournament_name")
            description = request.POST.get("description")
            date_str = request.POST.get("tournament_date")
            prize_pool = request.POST.get("prize_pool")
            banner = request.POST.get("banner")
            team_max = request.POST.get("team_maximum_count")
            format_id = request.POST.get("tournament_format")

            # Validate required fields
            if not all([name, description, date_str, prize_pool, team_max, format_id]):
                return JsonResponse({"status": "error", "message": "Missing fields"})
            
            # Fetch related format
            t_format = TournamentFormat.objects.get(id=format_id)

            # Create the Tournament
            tournament = Tournament(
                organizer=request.user,
                tournament_name=name,
                description=description,
                tournament_date=parse_date(date_str),
                prize_pool=int(prize_pool),        # Convert String to Int
                team_maximum_count=int(team_max),  # Convert String to Int
                tournament_format=t_format,
                banner=banner if banner else None
            )
            tournament.save()

            return JsonResponse({"status": "success", "message": "Tournament created successfully!"})

        except TournamentFormat.DoesNotExist:
            return JsonResponse({"status": "error", "message": "Invalid Tournament Format selected."})
        except ValueError:
            return JsonResponse({"status": "error", "message": "Invalid number format for Prize Pool or Team Count."})
        except Exception as e:
            return JsonResponse({"status": "error", "message": str(e)})

    return JsonResponse({"status": "error", "message": "Invalid method"}, status=405)


@csrf_exempt
def edit_tournament_flutter(request, tournament_id):
    if request.method == 'POST':
        # Verify user is logged in
        if not request.user.is_authenticated:
            return JsonResponse({
                "status": "error",
                "message": "You must be logged in to edit a tournament."
            }, status=401)

        # Get the tournament
        tournament = get_object_or_404(Tournament, id=tournament_id)

        # Permission check
        is_admin = request.user.is_staff
        is_organizer = hasattr(request.user, 'is_organizer') and request.user.is_organizer()
        is_owner = (tournament.organizer == request.user)
        if not (is_admin or (is_organizer and is_owner)):
            return JsonResponse({
                "status": "error",
                "message": "You do not have permission to edit this tournament."
            }, status=403)

        try:
            # Get data from request.POST
            name = request.POST.get("tournament_name")
            description = request.POST.get("description")
            date_str = request.POST.get("tournament_date")
            prize_pool = request.POST.get("prize_pool")
            banner = request.POST.get("banner")
            team_max = request.POST.get("team_maximum_count")
            format_id = request.POST.get("tournament_format")

            # Update fields if provided
            if name:
                tournament.tournament_name = name
            if description:
                tournament.description = description
            if date_str:
                tournament.tournament_date = parse_date(date_str)
            if prize_pool:
                tournament.prize_pool = int(prize_pool)
            if banner:
                tournament.banner = banner
            if team_max:
                tournament.team_maximum_count = int(team_max)
            if format_id:
                t_format = TournamentFormat.objects.get(id=format_id)
                tournament.tournament_format = t_format

            tournament.save()

            return JsonResponse({"status": "success", "message": "Tournament updated successfully!"})

        except TournamentFormat.DoesNotExist:
            return JsonResponse({"status": "error", "message": "Invalid Tournament Format selected."})
        except ValueError:
            return JsonResponse({"status": "error", "message": "Invalid number format for Prize Pool or Team Count."})
        except Exception as e:
            return JsonResponse({"status": "error", "message": str(e)})

    return JsonResponse({"status": "error", "message": "Invalid method"}, status=405)


@csrf_exempt
def delete_tournament_flutter(request, tournament_id):
    if request.method == 'POST':
        # Verify user is logged in
        if not request.user.is_authenticated:
            return JsonResponse({
                "status": "error",
                "message": "You must be logged in to delete a tournament."
            }, status=401)

        # Get the tournament
        tournament = get_object_or_404(Tournament, id=tournament_id)

        # Permission check
        is_admin = request.user.is_staff
        is_organizer = hasattr(request.user, 'is_organizer') and request.user.is_organizer()
        is_owner = (tournament.organizer == request.user)
        if not (is_admin or (is_organizer and is_owner)):
            return JsonResponse({
                "status": "error",
                "message": "You do not have permission to delete this tournament."
            }, status=403)

        try:
            tournament.delete()
            return JsonResponse({"status": "success", "message": "Tournament deleted successfully!"})

        except Exception as e:
            return JsonResponse({"status": "error", "message": str(e)})

    return JsonResponse({"status": "error", "message": "Invalid method"}, status=405)


def show_games_json(request):
    games = Game.objects.all()
    data = [
        {
            'id': str(game.id),  # Convert UUID to string
            'name': game.name,
        }
        for game in games
    ]
    return JsonResponse(data, safe=False)

def show_formats_json(request):
    formats = TournamentFormat.objects.select_related('game').all() # Optimize query
    data = [
        {
            'id': str(fmt.id),
            'game_id': str(fmt.game.id), # REQUIRED by Flutter app
            'name': fmt.name,
            'team_size': fmt.team_size,  # REQUIRED by Flutter app
            'description': getattr(fmt, 'description', ''),
        }
        for fmt in formats
    ]
    return JsonResponse(data, safe=False)

def get_tournaments_paginated(request):
    # Get 'page' parameter from query string, default to 1
    page_number = request.GET.get('page', 1)
    
    # Fetch active tournaments (using your custom manager logic if available)
    # Ordered by creation date or date
    tournaments = Tournament.objects.all().order_by('-created_at')
    
    # Paginator: 20 items per page
    paginator = Paginator(tournaments, 20)
    page_obj = paginator.get_page(page_number)
    
    # Serialize data
    data = []
    for t in page_obj:
        data.append({
            "id": str(t.id),
            "organizer_id": str(t.organizer.id) if t.organizer else None,
            "tournament_format_id": str(t.tournament_format.id),
            "tournament_name": t.tournament_name,
            "description": t.description,
            "tournament_date": t.tournament_date.isoformat() if t.tournament_date else None,
            "prize_pool": t.prize_pool,
            "banner": t.banner,
            "team_maximum_count": t.team_maximum_count,
            "created_at": t.created_at.isoformat(),
            "updated_at": t.updated_at.isoformat(),
            "is_active": t.is_active if hasattr(t, 'is_active') else True, # Handle annotation if missing
            "status": t.status,
            "participants_count": t.participants_count(),
        })
    
    return JsonResponse({
        "tournament": data,  # Key matches Flutter model
        "has_next": page_obj.has_next(),
        "next_page_number": page_obj.next_page_number() if page_obj.has_next() else None
    })

def search_tournaments(request):
    """
    Search tournaments by name.
    GET /api/tournaments/search/?q=<query>
    """
    query = request.GET.get('q', '').strip()
    
    if not query:
        return JsonResponse({
            "tournaments": [],
            "count": 0
        })
    
    # Case-insensitive search on tournament_name only
    tournaments = Tournament.objects.filter(
        tournament_name__icontains=query
    ).order_by('-created_at')
    
    # Serialize data (same structure as paginated list)
    data = []
    for t in tournaments:
        data.append({
            "id": str(t.id),
            "organizer_id": str(t.organizer.id) if t.organizer else None,
            "tournament_format_id": str(t.tournament_format.id),
            "tournament_name": t.tournament_name,
            "description": t.description,
            "tournament_date": t.tournament_date.isoformat() if t.tournament_date else None,
            "prize_pool": t.prize_pool,
            "banner": t.banner,
            "team_maximum_count": t.team_maximum_count,
            "created_at": t.created_at.isoformat(),
            "updated_at": t.updated_at.isoformat(),
            "is_active": t.is_active if hasattr(t, 'is_active') else True,
            "status": t.status,
            "participants_count": t.participants_count(),
        })
    
    return JsonResponse({
        "tournaments": data,
        "count": len(data)
    })