from __future__ import annotations

from dataclasses import dataclass

import bcrypt
from pydantic import Field

from app.config import Settings
from app.prototype.storage import PrototypeStore
from app.schemas import StrictModel


class LoginRequest(StrictModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=256)


class LoginResponse(StrictModel):
    authenticated: bool = True


class AuthMeResponse(StrictModel):
    authenticated: bool = True
    email: str
    role: str
    quota_total: int | None = None
    quota_used: int | None = None
    quota_remaining: int | None = None
    unlimited: bool = False


class AuthUnauthenticatedResponse(StrictModel):
    authenticated: bool = False


@dataclass(frozen=True)
class AuthAccount:
    email: str
    password_hash: str
    role: str
    quota_total: int | None = None


class PrototypeAuthService:
    """Server-only account verification and prototype quota coordination."""

    def __init__(self, settings: Settings, store: PrototypeStore) -> None:
        self.store = store
        self.accounts = _accounts_from_settings(settings)
        self.accounts_by_email = {account.email.lower(): account for account in self.accounts}
        for account in self.accounts:
            if account.role == "client":
                self.store.ensure_auth_quota_account(account.email, account.quota_total or 3)

    @property
    def configured(self) -> bool:
        return len(self.accounts) == 3

    def authenticate(self, email: str, password: str) -> AuthAccount | None:
        account = self.accounts_by_email.get(email.strip().lower())
        if account is None:
            return None
        try:
            valid = bcrypt.checkpw(password.encode("utf-8"), account.password_hash.encode("utf-8"))
        except (ValueError, TypeError):
            return None
        return account if valid else None

    def account_for_email(self, email: str | None) -> AuthAccount | None:
        return self.accounts_by_email.get((email or "").strip().lower())

    def profile(self, account: AuthAccount) -> AuthMeResponse:
        if account.role == "admin":
            return AuthMeResponse(
                email=account.email,
                role="admin",
                unlimited=True,
            )
        quota = self.store.get_auth_quota(account.email)
        return AuthMeResponse(
            email=account.email,
            role="client",
            quota_total=quota["quota_total"],
            quota_used=quota["quota_used"],
            quota_remaining=quota["quota_remaining"],
        )

    def reserve_analysis(self, account: AuthAccount) -> str | None:
        if account.role == "admin":
            return ""
        return self.store.reserve_auth_quota(account.email)

    def confirm_analysis(self, reservation_id: str) -> None:
        if reservation_id:
            self.store.confirm_auth_quota_reservation(reservation_id)

    def release_analysis(self, reservation_id: str) -> None:
        if reservation_id:
            self.store.release_auth_quota_reservation(reservation_id)


def _accounts_from_settings(settings: Settings) -> tuple[AuthAccount, ...]:
    raw_accounts = (
        AuthAccount(settings.nexora_user1_email, settings.nexora_user1_password_hash, "client", 3),
        AuthAccount(settings.nexora_user2_email, settings.nexora_user2_password_hash, "client", 3),
        AuthAccount(settings.nexora_admin_email, settings.nexora_admin_password_hash, "admin"),
    )
    if not all(account.email and account.password_hash for account in raw_accounts):
        return ()
    return raw_accounts
