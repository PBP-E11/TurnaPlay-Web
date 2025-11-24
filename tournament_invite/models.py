import uuid
from django.db import models, transaction
from django.conf import settings
from django.core.exceptions import ValidationError

from django.db.models import Q

from tournament_registration.models import TournamentRegistration, TeamMember
from game_account.models import GameAccount


class TournamentInvite(models.Model):
    class Status(models.TextChoices):
        PENDING = ("pending", "Pending")
        ACCEPTED = ("accepted", "Accepted")
        REJECTED = ("rejected", "Rejected")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Penerima undangan (user yang diajak)
    user_account = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="received_invites",
        verbose_name="Invited User",
    )

    # Tim pengundang (registrasi turnamen)
    tournament_registration = models.ForeignKey(
        TournamentRegistration,
        on_delete=models.CASCADE,
        related_name="sent_invites",
        verbose_name="Inviting Team",
    )

    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            # Unique hanya saat status pending
            models.UniqueConstraint(
                fields=["user_account", "tournament_registration"],
                name="unique_pending_invite_per_user_and_team",
                condition=Q(status="pending"),
            ),
        ]
        ordering = ["-created_at"]
        verbose_name = "Tournament Invite"
        verbose_name_plural = "Tournament Invites"

    # ---------- Helpers ----------

    @property
    def tournament(self):
        return self.tournament_registration.tournament

    def _is_tournament_active(self) -> bool:
        """
        Mengembalikan True jika pendaftaran turnamen masih dibuka.
        Modul tournaments menganotasi 'is_active' pada queryset; jika tidak ada,
        kita fallback ke perhitungan tanggal bila field tersedia; jika tidak juga,
        kita anggap aktif.
        """
        t = self.tournament
        # 1) pakai anotasi kalau ada
        if hasattr(t, "is_active"):
            return bool(getattr(t, "is_active"))
        # 2) fallback: coba start/end bila ada
        try:
            from django.utils import timezone

            now = timezone.now().date()
            start = getattr(t, "registration_open_date", None) or getattr(
                t, "registration_start_date", None
            )
            end = getattr(t, "registration_close_date", None) or getattr(
                t, "registration_end_date", None
            )
            if start and end:
                return start <= now <= end
        except Exception:
            pass
        # 3) fallback terakhir
        return True

    def _team_size_limit(self) -> int | None:
        """Ambil kapasitas tim dari TournamentFormat."""
        tf = getattr(self.tournament, "tournament_format", None)
        return getattr(tf, "team_size", None) if tf else None

    def _current_member_count(self) -> int:
        return self.tournament_registration.members.count()

    def team_has_capacity(self) -> bool:
        """True jika jumlah member saat ini masih < team_size (kalau diketahui)."""
        limit = self._team_size_limit()
        return True if limit is None else self._current_member_count() < limit

    # ---------- Validasi ----------

    def clean(self):
        """
        Dijalankan pada create/update.
        Kita batasi pembuatan undangan hanya jika:
        - turnamen masih aktif
        - tim masih punya kapasitas (berdasar team_size jika tersedia)
        - penerima belum menjadi anggota tim lain pada turnamen yang sama
        """
        errors = {}

        # 1) turnamen aktif
        if not self._is_tournament_active():
            errors["tournament_registration"] = "Pendaftaran turnamen sudah ditutup."

        # 2) kapasitas tim
        if not self.team_has_capacity():
            errors["tournament_registration"] = "Kapasitas tim sudah penuh."

        # 3) satu user satu tim per turnamen
        if self.status == self.Status.PENDING:
            try:
                user_ga_qs = GameAccount.objects.filter(
                    user=self.user_account, active=True
                ).values_list("id", flat=True)
                if TeamMember.objects.filter(
                    game_account_id__in=list(user_ga_qs),
                    team__tournament=self.tournament,
                ).exists():
                    errors["user_account"] = (
                        "Pengguna sudah tergabung di tim lain pada turnamen ini."
                    )
            except Exception:
                pass

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    # ---------- accept / reject ----------

    @transaction.atomic
    def accept(self, game_account: GameAccount):
        """
        Terima undangan dengan memilih sebuah GameAccount.
        - Memastikan invite masih pending.
        - Memastikan tournament aktif & kapasitas tersedia.
        - Memastikan game account milik user yang diundang dan game-nya cocok.
        - Membuat TeamMember dengan full_clean() terlebih dahulu.
        - Mengubah status invite menjadi accepted.
        Return: instance TeamMember baru.
        """
        if self.status != self.Status.PENDING:
            raise ValidationError("Undangan tidak dalam status pending.")

        if not self._is_tournament_active():
            raise ValidationError("Pendaftaran turnamen sudah ditutup.")

        if not self.team_has_capacity():
            raise ValidationError("Kapasitas tim sudah penuh.")

        # GameAccount harus milik user penerima dan aktif
        if game_account.user_id != self.user_account_id or not game_account.active:
            raise ValidationError("Game account tidak valid untuk pengguna ini.")

        # Game turnamen harus cocok
        t_format = getattr(self.tournament, "tournament_format", None)
        t_game_id = getattr(t_format, "game_id", None)
        if t_game_id and str(game_account.game_id) != str(t_game_id):
            raise ValidationError("Game account tidak sesuai dengan game turnamen.")

        # Buat member baru (non-leader) dengan validation
        member = TeamMember(
            team=self.tournament_registration,
            game_account=game_account,
            is_leader=False,
        )
        member.full_clean() 
        member.save()

        # Update status undangan
        self.status = self.Status.ACCEPTED
        self.save(update_fields=["status"])

        return member

    @transaction.atomic
    def reject(self):
        """Tolak undangan (tidak membuat TeamMember)."""
        if self.status != self.Status.PENDING:
            raise ValidationError("Undangan tidak dalam status pending.")
        self.status = self.Status.REJECTED
        self.save(update_fields=["status"])

    def __str__(self):
        team = self.tournament_registration.team_name
        return f"Invite to {self.user_account} for team {team} ({self.status})"