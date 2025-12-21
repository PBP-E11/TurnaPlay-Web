import json
from game_account.models import GameAccount
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from game_account.forms import GameAccountForm
from django.shortcuts import get_object_or_404
from django.http import JsonResponse, HttpResponseBadRequest, HttpResponseForbidden
from django.views import View
from django.db import transaction, IntegrityError
from django.shortcuts import render
from tournaments.models import Game
from django.conf import settings


@csrf_exempt
def game_accounts_list_create(request):
    # GET -> list (supports ?game=<id>)
    if request.method == 'GET':
        game_id = request.GET.get('game')
        if game_id:
            # Only show user's accounts for specific game (even when filtered)
            if request.user.is_authenticated:
                qs = GameAccount.objects.filter(game__id=game_id, user=request.user, active=True)
            else:
                qs = GameAccount.objects.none()
        elif request.user.is_authenticated:
            # Show all of user's active accounts
            qs = GameAccount.objects.filter(user=request.user, active=True)
        else:
            qs = GameAccount.objects.none()

        data = []
        for ga in qs:
            data.append({
                'id': str(ga.id),
                'user': ga.user_id,
                'game': str(ga.game_id),
                'game_name': getattr(ga.game, 'name', None),
                'ingame_name': ga.ingame_name,
                'active': ga.active
            })
        return JsonResponse(data, safe=False, status=200)

    # POST -> create
    if request.method == 'POST':
        # TESTING: allow unauthenticated for quick testing by assigning a default user.
        from django.contrib.auth import get_user_model
        User = get_user_model()
        if not request.user.is_authenticated:
            return HttpResponseForbidden()

        try:
            payload = json.loads(request.body.decode('utf-8'))
        except json.JSONDecodeError:
            return HttpResponseBadRequest("Invalid JSON")
        form = GameAccountForm(data=payload)
        if form.is_valid():
            ga = form.save(commit=False)
            ga.user = request.user
            try:
                with transaction.atomic():
                    ga.save()
            except IntegrityError:
                return JsonResponse({'detail': 'Account with that in-game name already exists for this game.'}, status=400)
            return JsonResponse({'id': str(ga.id), 'user': ga.user_id, 'game': str(ga.game_id), 'ingame_name': ga.ingame_name, 'active': ga.active}, status=201)
        return JsonResponse({'errors': form.errors}, status=400)

@method_decorator(csrf_exempt, name='dispatch')
class GameAccountDetail(View):
    def dispatch(self, request, *args, **kwargs):
        if request.method == 'POST':
            try:
                payload = json.loads(request.body.decode())
                if payload.get('_method') == 'DELETE':
                    request.method = 'DELETE'
                if payload.get('_method') == 'PATCH':
                    request.method = 'PATCH'
            except Exception:
                pass
        return super().dispatch(request, *args, **kwargs)
    
    def get(self, request, pk):
        ga = get_object_or_404(GameAccount, pk=pk)
        data = {
            'id': str(ga.id),
            'user': ga.user_id,
            'game': str(ga.game_id),
            'game_name': getattr(ga.game, 'name', None),
            'ingame_name': ga.ingame_name,
            'active': ga.active,
        }
        return JsonResponse(data)

    def delete(self, request, pk):
        if not request.user.is_authenticated:
            return HttpResponseForbidden()
        ga = get_object_or_404(GameAccount, pk=pk)
        if ga.user != request.user and not request.user.is_staff:
            return HttpResponseForbidden()
        ga.active = False
        ga.save()   
        return JsonResponse({'detail': 'deleted'}, status=200)

    def _update_instance_from_payload(self, request, ga, partial=False):
        try:
            payload = json.loads(request.body.decode('utf-8'))
        except json.JSONDecodeError:
            return JsonResponse({'detail': 'Invalid JSON'}, status=400)

        # If partial, allow missing fields; otherwise require form to validate full payload
        form = GameAccountForm(data=payload, instance=ga)
        if form.is_valid():
            try:
                with transaction.atomic():
                    updated = form.save(commit=False)
                    # don't allow changing owner here
                    updated.user = ga.user
                    updated.save()
            except IntegrityError:
                return JsonResponse({'detail': 'Account with that in-game name already exists for this game.'}, status=400)
            data = {
                'id': str(updated.id),
                'user': updated.user_id,
                'game': str(updated.game_id),
                'game_name': getattr(updated.game, 'name', None),
                'ingame_name': updated.ingame_name,
                'active': updated.active,
            }
            return JsonResponse(data, status=200)
        else:
            return JsonResponse({'errors': form.errors}, status=400)

    def put(self, request, pk):
        # Full update
        if not request.user.is_authenticated:
            return HttpResponseForbidden()
        ga = get_object_or_404(GameAccount, pk=pk)
        if ga.user != request.user and not request.user.is_staff:
            return HttpResponseForbidden()
        return self._update_instance_from_payload(request, ga, partial=False)

    def patch(self, request, pk):
        # Partial update
        if not request.user.is_authenticated:
            return HttpResponseForbidden()
        ga = get_object_or_404(GameAccount, pk=pk)
        if ga.user != request.user and not request.user.is_staff:
            return HttpResponseForbidden()
        try:
            payload = json.loads(request.body.decode('utf-8'))
        except json.JSONDecodeError:
            return JsonResponse({'detail': 'Invalid JSON'}, status=400)
        data = {
            'game': ga.game_id,
            'ingame_name': ga.ingame_name,
        }
        # overwrite with supplied fields
        if 'game' in payload:
            data['game'] = payload.get('game')
        if 'ingame_name' in payload:
            data['ingame_name'] = payload.get('ingame_name')
        form = GameAccountForm(data=data, instance=ga)
        if form.is_valid():
            try:
                with transaction.atomic():
                    updated = form.save(commit=False)
                    updated.user = ga.user
                    updated.save()
            except IntegrityError:
                return JsonResponse({'detail': 'Account with that in-game name already exists for this game.'}, status=400)
            data = {
                'id': str(updated.id),
                'user': updated.user_id,
                'game': str(updated.game_id),
                'game_name': getattr(updated.game, 'name', None),
                'ingame_name': updated.ingame_name,
                'active': updated.active,
            }
            return JsonResponse(data, status=200)
        return JsonResponse({'errors': form.errors}, status=400)
    
def games_list(request):
    """
    Return JSON list of games for selection in mobile test screen.
    Each item: { 'id': '<id_or_uuid>', 'name': '<game name>' }
    """
    qs = Game.objects.all()
    data = [{'id': str(g.id), 'name': getattr(g, 'name', '')} for g in qs]
    return JsonResponse(data, safe=False)
