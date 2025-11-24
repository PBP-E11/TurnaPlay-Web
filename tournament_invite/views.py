from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError, PermissionDenied
from django.db import IntegrityError, transaction
from django.db.models import Max, Q, Count
from django.http import (
    HttpRequest,
    HttpResponse,
    JsonResponse,
    HttpResponseBadRequest,
)
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from .models import TournamentInvite

from user_account.models import UserAccount
from game_account.models import GameAccount
from tournament_registration.models import TournamentRegistration, TeamMember


# ------------ Helper ------------
def _is_leader(user: UserAccount, team: TournamentRegistration) -> bool:
    return TeamMember.objects.filter(team=team, is_leader=True, game_account__user=user).exists()


def _team_size(team: TournamentRegistration) -> int:
    return team.tournament.tournament_format.team_size


def _recompute_team_status(team: TournamentRegistration) -> None:
    try:
        size = _team_size(team)
    except Exception:
        return
    member_count = TeamMember.objects.filter(team=team).count()
    new_status = "valid" if member_count == size else "invalid"
    if getattr(team, "status", None) != new_status:
        team.status = new_status
        team.save(update_fields=["status"])


def _invite_queryset_for_user(user: UserAccount):
    incoming = TournamentInvite.objects.select_related(
        "user_account", "tournament_registration", "tournament_registration__tournament",
        "tournament_registration__tournament__tournament_format",
    ).filter(user_account=user)

    # outgoing = undangan yg dikirim oleh tim di mana user adalah leader
    leader_team_ids = TeamMember.objects.filter(
        game_account__user=user, is_leader=True
    ).values_list("team_id", flat=True)

    outgoing = TournamentInvite.objects.select_related(
        "user_account", "tournament_registration", "tournament_registration__tournament",
        "tournament_registration__tournament__tournament_format",
    ).filter(tournament_registration_id__in=leader_team_ids)

    return incoming, outgoing


# ------------ Pages ------------
@login_required
def invite_list(request: HttpRequest) -> HttpResponse:
    """Halaman daftar undangan (incoming & outgoing), dengan filter sederhana."""
    status = request.GET.get("status")
    status_filter = Q()
    if status in {"pending", "accepted", "rejected"}:
        status_filter = Q(status=status)

    incoming, outgoing = _invite_queryset_for_user(request.user)
    incoming = incoming.filter(status_filter).order_by("-created_at")
    outgoing = outgoing.filter(status_filter).order_by("-created_at")

    leader_teams = (
        TournamentRegistration.objects
        .filter(
            members__game_account__user=request.user,
            members__is_leader=True,
        )
        .select_related(
            "tournament",
            "tournament__tournament_format",
            "tournament__tournament_format__game",
        )
        .distinct()
    )

    user_game_accounts = (
        GameAccount.objects
        .filter(user=request.user, active=True)
        .select_related("game")
        .order_by("game__name", "ingame_name")
    )

    context = {
        "incoming": incoming,
        "outgoing": outgoing,
        "status": status or "all",
        "leader_teams": leader_teams,
        "game_accounts": user_game_accounts,
    }
    return render(request, "tournament_invite/invite_list.html", context)


@login_required
def create_invite(request: HttpRequest) -> HttpResponse:
    """Buat undangan baru (leader only) – versi sederhana form POST."""
    if request.method != "POST":
        messages.error(request, "Invalid method.")
        return redirect("tournament_invite:invite-list")

    user_query = request.POST.get("username_or_email")
    reg_id = request.POST.get("registration_id")

    if not user_query or not reg_id:
        messages.error(request, "Missing parameters.")
        return redirect("tournament_invite:invite-list")

    user_to_invite = (
    UserAccount.objects.filter(username__iexact=user_query).first()
    or UserAccount.objects.filter(email__iexact=user_query).first()
    )
    if not user_to_invite:
        messages.error(request, "User not found.")
        return redirect("tournament_invite:invite-list")
    team = get_object_or_404(TournamentRegistration, pk=reg_id)

    # permission: hanya leader tim
    if not TeamMember.objects.filter(
        team=team, is_leader=True, game_account__user=request.user
    ).exists():
        raise PermissionDenied("Only team leader can invite.")

    # tidak boleh mengundang diri sendiri
    if user_to_invite.id == request.user.id:
        messages.error(request, "You cannot invite yourself.")
        return redirect("tournament_invite:invite-list")

    # tidak boleh undang user yang sudah tergabung di tim turnamen yang sama
    same_tournament_member = TeamMember.objects.filter(
        game_account__user=user_to_invite, team__tournament=team.tournament
    ).exists()
    if same_tournament_member:
        messages.error(request, "Target user already belongs to a team for this tournament.")
        return redirect("tournament_invite:invite-list")

    try:
        TournamentInvite.objects.create(
            user_account=user_to_invite,
            tournament_registration=team,
            status="pending",
        )
        messages.success(request, "Invite sent.")
    except IntegrityError:
        messages.error(request, "There is already a pending invite for this user & team.")

    return redirect("tournament_invite:invite-list")


# ------------ Polling for toast ------------
@login_required
def check_new_invite(request: HttpRequest) -> JsonResponse:
    """Kembalikan pending_count + latest_created_at agar client bisa one-time toast."""
    latest = (
        TournamentInvite.objects.filter(user_account=request.user, status="pending")
        .aggregate(x=Max("created_at"))
        .get("x")
    )
    count_pending = TournamentInvite.objects.filter(
        user_account=request.user, status="pending"
    ).count()

    data = {
        "pending_count": count_pending,
        "latest_created_at": latest.isoformat() if latest else None,
    }
    return JsonResponse(data)


# ------------ JSON Actions (AJAX) ------------
@login_required
@transaction.atomic
def api_accept_invite(request: HttpRequest) -> JsonResponse:
    if request.method != "POST":
        return HttpResponseBadRequest("Invalid method")
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except Exception:
        return HttpResponseBadRequest("Bad JSON")

    invite_id = payload.get("invite_id")
    ga_id = payload.get("game_account_id")
    invite = get_object_or_404(TournamentInvite, pk=invite_id, user_account=request.user)

    if invite.status != "pending":
        return JsonResponse({"ok": False, "error": "Invite already processed."}, status=400)

    team = invite.tournament_registration

    # kapasitas tim
    size = _team_size(team)
    current_members = TeamMember.objects.filter(team=team).count()
    if current_members >= size:
        return JsonResponse({"ok": False, "error": "Team is already full."}, status=400)

    # ambil game account & validasi pemilik + game-nya cocok
    ga = get_object_or_404(GameAccount, pk=ga_id, user=request.user, active=True)
    expected_game_id = team.tournament.tournament_format.game_id
    if str(ga.game_id) != str(expected_game_id):
        return JsonResponse({"ok": False, "error": "Game account does not match tournament game."}, status=400)

    # buat TeamMember menggunakan rule di tournament_registration
    member = TeamMember(team=team, game_account=ga, is_leader=False)
    try:
        invite.accept(ga)
    except ValidationError as e:
        if hasattr(e, "message_dict"):
            msg = e.message_dict
        else:
            msg = e.messages
        return JsonResponse({"ok": False, "error": msg}, status=400)
    except Exception as e:
        return JsonResponse(
            {"ok": False, "error": f"Server error saat menerima undangan: {e}"},
            status=400,
        )

    _recompute_team_status(invite.tournament_registration)
    return JsonResponse({"ok": True})

@login_required
@transaction.atomic
def api_reject_invite(request: HttpRequest) -> JsonResponse:
    if request.method != "POST":
        return HttpResponseBadRequest("Invalid method")
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except Exception:
        return HttpResponseBadRequest("Bad JSON")

    invite_id = payload.get("invite_id")
    invite = get_object_or_404(TournamentInvite, pk=invite_id, user_account=request.user)

    if invite.status != "pending":
        return JsonResponse({"ok": False, "error": "Invite already processed."}, status=400)

    invite.status = "rejected"
    invite.save(update_fields=["status"])
    return JsonResponse({"ok": True})


@login_required
@transaction.atomic
def api_cancel_invite(request: HttpRequest) -> JsonResponse:
    if request.method != "POST":
        return HttpResponseBadRequest("Invalid method")
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except Exception:
        return HttpResponseBadRequest("Bad JSON")

    invite_id = payload.get("invite_id")
    invite = get_object_or_404(TournamentInvite, pk=invite_id)
    team = invite.tournament_registration

    # hanya leader yang dapat cancel
    if not _is_leader(request.user, team):
        raise PermissionDenied("Only team leader can cancel.")

    if invite.status == "pending":
        invite.delete()
        return JsonResponse({"ok": True})
    
    if invite.status == "accepted":
        TeamMember.objects.filter(team=team, game_account__user=invite.user_account).delete()
        invite.status = "rejected"
        invite.save(update_fields=["status"])
        _recompute_team_status(team)
        return JsonResponse({"ok": True})

    return JsonResponse({"ok": False, "error": "Nothing to cancel."}, status=400)
