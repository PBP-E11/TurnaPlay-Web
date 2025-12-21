import json

from django.http import JsonResponse, HttpRequest, HttpResponseBadRequest
from django.shortcuts import get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.db.models import Max

from tournament_invite.models import TournamentInvite
from game_account.models import GameAccount
from tournament_registration.models import TournamentRegistration, TeamMember
from tournament_invite.views import _invite_queryset_for_user, _recompute_team_status, _is_leader
from user_account.models import UserAccount


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
    action = payload.get("action")
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

    try:
        invite.reject()
    except ValidationError as e:
        msg = e.messages if hasattr(e, "messages") else str(e)
        return JsonResponse({"ok": False, "error": msg}, status=400)

    return JsonResponse({"ok": True, "status": "rejected"})


@login_required
@require_http_methods(["POST"])
@csrf_exempt
def send_invite(request: HttpRequest) -> JsonResponse:
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except Exception:
        return HttpResponseBadRequest("Bad JSON")

    username_or_email = payload.get("username_or_email")
    registration_id = payload.get("registration_id")

    if not username_or_email or not registration_id:
        return JsonResponse(
            {
                "ok": False,
                "status": "error",
                "message": "Missing username_or_email or registration_id.",
            },
            status=400,
        )

    user_to_invite = (
        UserAccount.objects.filter(username__iexact=username_or_email).first()
        or UserAccount.objects.filter(email__iexact=username_or_email).first()
    )

    if not user_to_invite:
        return JsonResponse(
            {"ok": False, "status": "error", "message": "User not found."},
            status=404,
        )

    team = get_object_or_404(TournamentRegistration, pk=registration_id)

    if not _is_leader(request.user, team):
        return JsonResponse(
            {"ok": False, "status": "error", "message": "Only team leader can invite."},
            status=403,
        )

    if user_to_invite.id == request.user.id:
        return JsonResponse(
            {"ok": False, "status": "error", "message": "You cannot invite yourself."},
            status=400,
        )

    same_tournament_member = TeamMember.objects.filter(
        game_account__user=user_to_invite,
        team__tournament=team.tournament,
    ).exists()

    if same_tournament_member:
        return JsonResponse(
            {
                "ok": False,
                "status": "error",
                "message": "Target user already belongs to a team for this tournament.",
            },
            status=400,
        )

    try:
        invite = TournamentInvite.objects.create(
            user_account=user_to_invite,
            tournament_registration=team,
            status=TournamentInvite.Status.PENDING,
        )
    except IntegrityError:
        return JsonResponse(
            {
                "ok": False,
                "status": "error",
                "message": "There is already a pending invite for this user & team.",
            },
            status=400,
        )
    except ValidationError as e:
        msg = e.messages if hasattr(e, "messages") else str(e)
        return JsonResponse(
            {"ok": False, "status": "error", "message": msg},
            status=400,
        )

    return JsonResponse(
        {
            "ok": True,
            "status": "success",
            "message": "Invite sent.",
            "invite": _serialize_invite(invite),
        },
        status=201,
    )


@login_required
@require_http_methods(["POST"])
@csrf_exempt
def api_cancel_invite(request: HttpRequest) -> JsonResponse:
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except Exception:
        return HttpResponseBadRequest("Bad JSON")

    invite_id = payload.get("invite_id")
    if not invite_id:
        return JsonResponse(
            {"ok": False, "status": "error", "message": "invite_id is required."},
            status=400,
        )

    invite = get_object_or_404(TournamentInvite, pk=invite_id)
    team = invite.tournament_registration

    if not _is_leader(request.user, team):
        return JsonResponse(
            {"ok": False, "status": "error", "message": "Only team leader can cancel."},
            status=403,
        )

    if invite.status == TournamentInvite.Status.PENDING:
        invite.delete()
        return JsonResponse(
            {
                "ok": True,
                "status": "cancelled",
                "invite_id": str(invite_id),
                "message": "Invite cancelled.",
            }
        )

    if invite.status == TournamentInvite.Status.ACCEPTED:
        TeamMember.objects.filter(
            team=team,
            game_account__user=invite.user_account,
        ).delete()

        invite.status = TournamentInvite.Status.REJECTED
        invite.save(update_fields=["status"])
        _recompute_team_status(team)

        return JsonResponse(
            {
                "ok": True,
                "status": "member_removed",
                "invite_id": str(invite.id),
                "message": "Invite cancelled and member removed.",
            }
        )

    return JsonResponse(
        {"ok": False, "status": "error", "message": "Nothing to cancel."},
        status=400,
    )


@login_required
@require_http_methods(["GET"])
def api_new_invites(request: HttpRequest) -> JsonResponse:
    latest = (
        TournamentInvite.objects.filter(
            user_account=request.user,
            status=TournamentInvite.Status.PENDING,
        )
        .aggregate(x=Max("created_at"))
        .get("x")
    )

    count_pending = TournamentInvite.objects.filter(
        user_account=request.user,
        status=TournamentInvite.Status.PENDING,
    ).count()

    return JsonResponse(
        {
            "ok": True,
            "pending_count": count_pending,
            "latest_created_at": latest.isoformat() if latest else None,
        }
    )