import json
import uuid
import traceback
from django.http import JsonResponse, HttpResponse, HttpRequest
from django.views.decorators.http import require_POST
from django.core.exceptions import ValidationError
from django.db import DatabaseError, transaction
from django.views.decorators.csrf import csrf_exempt
from tournament_registration.models import TournamentRegistration, TeamMember
from user_account.models import UserAccount
from game_account.models import GameAccount
from tournaments.models import Tournament

ERR_NOT_AUTHENTICATED = 6900
ERR_NOT_AUTHORIZED = 6901
ERR_MALFORMED_DATA = 6902
ERR_EXISTS = 6903
ERR_NOT_FOUND = 6904
ERR_UNEXPECTED_ERROR = 6905
STATUS_CODE = {
    ERR_NOT_AUTHENTICATED: 401,
    ERR_NOT_AUTHORIZED: 403,
    ERR_MALFORMED_DATA: 400,
    ERR_EXISTS: 400,
    ERR_NOT_FOUND: 404,
    ERR_UNEXPECTED_ERROR: 500,
}

class JsonResponseWithStatusCode(JsonResponse):
    def __init__(self, *args, status_code: int = 200, **kwargs):
        super().__init__(*args, **kwargs)
        self.status_code = status_code

def success(data: dict, status_code: int = 200) -> HttpResponse:
    return JsonResponseWithStatusCode({
        'success': True,
        'data': data,
    }, status_code = status_code)

def reject(error_message: str, error_code: int) -> HttpResponse:
    return JsonResponseWithStatusCode({
        'success': False,
        'error_code': error_code,
        'error_message': error_message,
    }, status_code = STATUS_CODE[error_code])

def api_login_required(_F):
    def wrapper(request: HttpRequest, *args, **kwargs) -> HttpResponse:
        if not request.user.is_authenticated:
            return reject('Not authenticated', ERR_NOT_AUTHENTICATED)
        return _F(request, *args, **kwargs)

    return wrapper

class RejectException(Exception):
    def __init__(self, error_message: str, error_code: int):
        super().__init__(error_message)

        self.error_message = error_message
        self.error_code = error_code

def exception_wrapper(_F):
    def wrapper(request: HttpRequest, *args, **kwargs) -> HttpResponse:
        try:
            return _F(request, *args, **kwargs)
        except RejectException as e:
            return reject(e.error_message, e.error_code)
        except:
            traceback.print_exc()
            return reject('Unexpected server error', ERR_UNEXPECTED_ERROR)

    return wrapper

@csrf_exempt
@require_POST
@api_login_required
@exception_wrapper
def create_team(request: HttpRequest) -> HttpResponse:
    """ 
    Accepts POST JSON data
    Requires login
    {
        "tournament_id": <uuid>,
        "leader_game_account_id": <uuid>,
        "team_name": <str>,
    }

    On success returns
    {
        "success": true,
        "data": {
            "team_id": <uuid>
        }
    }
    """
    try:
        data: dict = json.loads(request.body)
        tournament_id: uuid.UUID = uuid.UUID(data['tournament_id'])
        leader_game_account_id: uuid.UUID = uuid.UUID(data['leader_game_account_id'])
        team_name: str = data['team_name']
    except (KeyError, ValueError, json.JSONDecodeError):
        raise RejectException('Malformed data', ERR_MALFORMED_DATA)

    if not isinstance(team_name, str):
        raise RejectException('Malformed data', ERR_MALFORMED_DATA)

    try:
        tournament: Tournament = Tournament.objects.get(pk=tournament_id)
    except Tournament.DoesNotExist:
        raise RejectException('Tournament does not exist', ERR_NOT_FOUND)

    try:
        game_account: GameAccount = GameAccount.objects.get(pk=leader_game_account_id)
    except GameAccount.DoesNotExist:
        raise RejectException('Game Account does not exist', ERR_NOT_FOUND)

    if game_account.user != request.user:
        raise RejectException('Game Account does not belong to user', ERR_NOT_AUTHORIZED)

    if Tournament.objects.filter(pk=tournament.id, registrations__members__game_account__user=request.user).exists():
        raise RejectException('User is already in a team', ERR_EXISTS)

    if TournamentRegistration.objects.filter(tournament=tournament_id, team_name=team_name).exists():
        raise RejectException('Team name already exists', ERR_EXISTS)

    instance: TournamentRegistration = TournamentRegistration(tournament=tournament, team_name=team_name)
    instance.full_clean()
    with transaction.atomic():
        instance.save()
        team_member: TeamMember = TeamMember(game_account=game_account, team=instance, is_leader=True)
        team_member.full_clean()
        team_member.save()

    return success({'team_id': str(instance.id)})

@csrf_exempt
@require_POST
@api_login_required
@exception_wrapper
def get_team(request: HttpRequest) -> HttpResponse:
    """ 
    Accepts POST
    {
        "team_id": <uuid>
    }
    OR
    {
        "user_account_id": <uuid>,
        "tournament_id": <uuid>
    }
    OR
    {
        "tournament_id": <uuid>
    }

    On success returns
    {
        "success": true,
        "data": {
            "team_id": <uuid>,
            "tournament_id": <uuid>,
            "team_name": <str>,
            "is_user_leader": <bool>,
            "members": [
                {
                    "game_account_id": <uuid>,
                    "game_account_name": <str>,
                    "user_account_name": <str>,
                    "team_id": <uuid>,
                    "is_leader": True // Appears only once
                }
            ]
        }
    }

    404 is guaranteed if user is not in a team
    """
    try:
        data: dict = json.loads(request.body)
        team_id: uuid.UUID | None = uuid.UUID(data.get('team_id')) if data.get('team_id') is not None else None
        user_account_id: uuid.UUID | None = uuid.UUID(data.get('user_account_id')) if data.get('user_account_id') is not None else None
        tournament_id: uuid.UUID | None = uuid.UUID(data.get('tournament_id')) if data.get('tournament_id') is not None else None
    except (KeyError, ValueError, json.JSONDecodeError):
        raise RejectException('Malformed data', ERR_MALFORMED_DATA)

    if team_id is None and user_account_id is None and tournament_id is None:
        raise RejectException('Missing parameter(s)', ERR_MALFORMED_DATA)

    if team_id is not None and (user_account_id is not None or tournament_id is not None):
        raise RejectException('Query of team_id is mutually exclusive with (user_account_id, tournament_id)', ERR_MALFORMED_DATA)

    if team_id is not None:
        try:
            team: TournamentRegistration = TournamentRegistration.objects.get(pk=team_id)
        except TournamentRegistration.DoesNotExist:
            raise RejectException('Team does not exist', ERR_NOT_FOUND)
    elif tournament_id is not None:
        try:
            tournament: Tournament = Tournament.objects.get(pk=tournament_id)
        except Tournament.DoesNotExist:
            raise RejectException('Tournament does not exist', ERR_NOT_FOUND)
        if user_account_id is not None:
            try:
                user_account: UserAccount = UserAccount.objects.get(pk=user_account_id)
            except UserAccount.DoesNotExist:
                raise RejectException('User does not exist', ERR_NOT_FOUND)
        else:
            user_account = request.user

        try:
            team: TournamentRegistration = TournamentRegistration.objects.get(members__game_account__user=user_account, tournament=tournament)
        except TournamentRegistration.DoesNotExist:
            raise RejectException('No match found', ERR_NOT_FOUND)

    member_data = []
    leader: TeamMember = TeamMember.objects.get(team=team, is_leader=True)
    member_data.append({
        "game_account_id": leader.game_account.id,
        "game_account_name": leader.game_account.ingame_name,
        "user_account_name": leader.game_account.user.username,
        "team_id": str(team.id),
        "is_leader": True,
    })
    [
        member_data.append({
            "game_account_id": member.game_account.id,
            "game_account_name": member.game_account.ingame_name,
            "user_account_name": member.game_account.user.username,
            "team_id": str(team.id),
            "is_leader": False,
        })
        for member in TeamMember.objects.filter(team=team, is_leader=False)
    ]

    return success({
        "team_id": team.id,
        "tournament_id": team.tournament.id,
        "team_name": team.team_name,
        "user_id": request.user.id,
        "is_user_leader": _is_user_team_leader(request.user, team),
        "is_user_in_team": TeamMember.objects.filter(team=team, game_account__user=request.user).exists(),
        "members": member_data,
    })

@csrf_exempt
@require_POST
@api_login_required
@exception_wrapper
def update_team(request: HttpRequest) -> HttpResponse:
    """ 
    Accepts POST JSON data
    Requires login
    Must be leader of team
    {
        "team_id": <uuid>,
        "team_name": <str>
    }

    On success returns
    {
        "success": true,
        "data": {
            "team_id": <uuid>,
            "team_name": <str>
        }
    }
    """
    try:
        data: dict = json.loads(request.body)
        team_id: uuid.UUID = uuid.UUID(data['team_id'])
        team_name: str = data['team_name']
    except (KeyError, ValueError, json.JSONDecodeError):
        raise RejectException('Malformed data', ERR_MALFORMED_DATA)

    if not isinstance(team_name, str):
        raise RejectException('Malformed data', ERR_MALFORMED_DATA)

    try:
        team: TournamentRegistration = TournamentRegistration.objects.get(pk=team_id)
    except TournamentRegistration.DoesNotExist:
        raise RejectException('Team does not exist', ERR_NOT_FOUND)

    if not _is_user_team_leader(request.user, team):
        raise RejectException('User is not team leader', ERR_NOT_AUTHORIZED)

    team.team_name = team_name
    team.full_clean()
    team.save()

    return success({"team_id": team.id, "team_name": team_name})

@csrf_exempt
@require_POST
@api_login_required
@exception_wrapper
def delete_team(request: HttpRequest) -> HttpResponse:
    """ 
    Accepts POST
    Must be leader of team
    {
        "team_id": <uuid>
    }

    On success returns
    {
        "success": true,
        "data": {}
    }
    """
    try:
        team_id: uuid.UUID = uuid.UUID(json.loads(request.body)["team_id"])
    except (KeyError, ValueError, json.JSONDecodeError):
        raise RejectException('Malformed Data', ERR_MALFORMED_DATA)

    try:
        team: TournamentRegistration = TournamentRegistration.objects.get(pk=team_id)
    except TournamentRegistration.DoesNotExist:
        raise RejectException('Team does not exist', ERR_NOT_FOUND)

    if not _is_user_team_leader(request.user, team):
        raise RejectException('User is not team leader', ERR_NOT_AUTHORIZED)

    team.delete()
    return success({})

@csrf_exempt
@require_POST
@api_login_required
@exception_wrapper
def join_member(request: HttpRequest) -> HttpResponse:
    pass

@csrf_exempt
@require_POST
@api_login_required
@exception_wrapper
def update_member(request: HttpRequest) -> HttpResponse:
    """
    Accepts POST
    Requires login
    Must part of team
    {
        "team_id": <uuid>,
        "game_account_id": <uuid>
    }

    On success returns
    {
        "success": true,
        "data": {
            "team_id": <uuid>,
            "game_account_id": <uuid>
        }
    }
    """
    try:
        data: dict = json.loads(request.body)
        team_id: uuid.UUID = uuid.UUID(data['team_id'])
        game_account_id: uuid.UUID = uuid.UUID(data['game_account_id'])
    except (KeyError, ValueError, json.JSONDecodeError):
        raise RejectException('Malformed Data', ERR_MALFORMED_DATA)

    try:
        team: TournamentRegistration = TournamentRegistration.objects.get(pk=team_id)
    except TournamentRegistration.DoesNotExist:
        raise RejectException('Team does not exist', ERR_NOT_FOUND)

    try:
        game_account: GameAccount = GameAccount.objects.get(pk=game_account_id)
    except GameAccount.DoesNotExist:
        raise RejectException('Game Account does not exist', ERR_NOT_FOUND)

    if game_account.user != request.user:
        raise RejectException('Game Account does not belong to user', ERR_NOT_AUTHORIZED)

    try:
        team_member: TeamMember = TeamMember.objects.get(team=team, game_account=game_account)
    except TeamMember.DoesNotExist:
        raise RejectException('User is not part of this team', ERR_NOT_FOUND)

    team_member.game_account = game_account
    team_member.full_clean()
    team_member.save()
    return success({"team_id": team.id, "game_account_id": game_account.id})

@csrf_exempt
@require_POST
@api_login_required
@exception_wrapper
def delete_member(request: HttpRequest) -> HttpResponse:
    """
    Accepts POST
    Requires login
    Must NOT be leader
    Must be part of team
    {
        "team_id": <uuid>
    }

    On success returns {
        "success": true,
        "data": {}
    }
    """
    try:
        team_id: uuid.UUID = uuid.UUID(json.loads(request.body)["team_id"])
    except (KeyError, ValueError, json.JSONDecodeError):
        raise RejectException('Malformed Data', ERR_MALFORMED_DATA)

    try:
        team: TournamentRegistration = TournamentRegistration.objects.get(pk=team_id)
    except TournamentRegistration.DoesNotExist:
        raise RejectException('Team does not exist', ERR_NOT_FOUND)

    try:
        team_member: TeamMember = TeamMember.objects.get(
            team=team,
            game_account__user=request.user,
        )
    except TeamMember.DoesNotExist:
        raise RejectException('User is not part of this team', ERR_NOT_FOUND)

    if _is_user_team_leader(request.user, team):
        raise RejectException('User is team leader', ERR_NOT_AUTHORIZED)

    team_member.delete()
    return success({})

# Mksh karla :>
def _is_user_team_leader(user: UserAccount, team: TournamentRegistration) -> bool:
    """
    Cek apakah 'user' adalah leader dari 'team' tersebut.
    Berdasar model TeamMember: is_leader=True dan GameAccount.user == user
    """
    return TeamMember.objects.filter(
        team=team,
        is_leader=True,
        game_account__user=user,
    ).exists()
