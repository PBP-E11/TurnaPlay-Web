import json
from django.http import JsonResponse, HttpRequest, HttpResponseBadRequest
from django.shortcuts import get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt

from .models import TournamentInvite
from game_account.models import GameAccount
from tournament_registration.models import TournamentRegistration, TeamMember
from .views import _invite_queryset_for_user, _recompute_team_status
from django.core.exceptions import ValidationError

def _serialize_invite(invite: TournamentInvite) -> dict:
    t = invite.tournament_registration.tournament
    fmt = getattr(t, "tournament_format", None)
    game = getattr(fmt, "game", None)

    return {
        "id": str(invite.id),
        "status": invite.status,
        "created_at": invite.created_at.isoformat(),
        "tournament": {
            "id": str(t.id),
            "name": getattr(t, "tournament_name", ""),
            "game": getattr(game, "name", None),
        },
        "team": {
            "id": str(invite.tournament_registration.id),
            "name": invite.tournament_registration.team_name,
        },
    }

@login_required
@require_http_methods(["GET"])
def api_list_incoming(request: HttpRequest) -> JsonResponse:
    incoming, _ = _invite_queryset_for_user(request.user)

    status = request.GET.get("status")
    if status in {"pending", "accepted", "rejected"}:
        incoming = incoming.filter(status=status)

    data = [_serialize_invite(inv) for inv in incoming.order_by("-created_at")]
    return JsonResponse({"ok": True, "invites": data})

@login_required
@require_http_methods(["GET"])
def api_list_outgoing(request: HttpRequest) -> JsonResponse:
    _, outgoing = _invite_queryset_for_user(request.user)

    status = request.GET.get("status")
    if status in {"pending", "accepted", "rejected"}:
        outgoing = outgoing.filter(status=status)

    data = [_serialize_invite(inv) for inv in outgoing.order_by("-created_at")]
    return JsonResponse({"ok": True, "invites": data})

@login_required
@require_http_methods(["POST"])
@csrf_exempt
def api_respond_invite(request: HttpRequest) -> JsonResponse:
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except Exception:
        return HttpResponseBadRequest("Bad JSON")

    invite_id = payload.get("invite_id")
    action = payload.get("action")  # "accept" / "reject"
    game_account_id = payload.get("game_account_id")

    if not invite_id or action not in {"accept", "reject"}:
        return HttpResponseBadRequest("Missing or invalid parameters")

    invite = get_object_or_404(
        TournamentInvite,
        pk=invite_id,
        user_account=request.user,
    )

    if invite.status != invite.Status.PENDING:
        return JsonResponse(
            {"ok": False, "error": "Invite already processed."},
            status=400,
        )

    # ACCEPT
    if action == "accept":
        if not game_account_id:
            return HttpResponseBadRequest("game_account_id is required to accept")

        ga = get_object_or_404(
            GameAccount,
            pk=game_account_id,
            user=request.user,
            active=True,
        )

        try:
            invite.accept(ga)
        except ValidationError as e:
            msg = e.messages if hasattr(e, "messages") else str(e)
            return JsonResponse({"ok": False, "error": msg}, status=400)

        _recompute_team_status(invite.tournament_registration)
        return JsonResponse({"ok": True, "status": "accepted"})

    # REJECT
    try:
        invite.reject()
    except ValidationError as e:
        msg = e.messages if hasattr(e, "messages") else str(e)
        return JsonResponse({"ok": False, "error": msg}, status=400)

    return JsonResponse({"ok": True, "status": "rejected"})