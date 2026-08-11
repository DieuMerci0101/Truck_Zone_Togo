from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.hash import bcrypt
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models.user import User
from app.models.otp import OTPReset
from app.utils.email import send_otp_email
from app.utils.verification import PENDING_UPLOAD

settings = get_settings()
security = HTTPBearer(auto_error=False)

router = APIRouter(prefix="/api/auth", tags=["Auth"])


# ─── Helpers ────────────────────────────────────────

def normalize_role(role) -> str:
    """
    Normalise un rôle quel qu'il soit ('ADMIN', 'admin', 'DRIVER', ...) en
    minuscules afin que toute la logique (JWT, redirects, RBAC) soit cohérente.
    """
    value = getattr(role, "value", role)
    return str(value).strip().lower()


def user_role(user) -> str:
    """Récupère le rôle d'un User de façon sûre (enum ou chaîne brute)."""
    return normalize_role(getattr(user, "role", ""))


def create_token(user_id: str, token_type: str = "access", role: str | None = None, is_verified: bool = False, verification_status: str | None = None) -> str:
    if token_type == "access":
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    else:
        expire = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)
    payload = {
        "sub": user_id,
        "type": token_type,
        "exp": expire,
        "is_verified": is_verified,
        "verification_status": verification_status or PENDING_UPLOAD,
    }
    if role:
        payload["role"] = normalize_role(role)
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError:
        raise HTTPException(status_code=401, detail="Token invalide ou expiré")


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Récupère l'utilisateur connecté à partir du token JWT.
    Utilisé comme dependency FastAPI sur les routes protégées.
    """
    if not credentials:
        raise HTTPException(status_code=401, detail="Non authentifié")
    payload = decode_token(credentials.credentials)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Token invalide")
    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Compte désactivé")
    return user


async def require_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    """
    Vérifie que l'utilisateur connecté a le rôle admin.
    Si ce n'est pas le cas, renvoie une erreur 403.
    À utiliser sur toutes les routes réservées à l'administration.
    """
    if user_role(current_user) != "admin":
        raise HTTPException(
            status_code=403,
            detail="Accès réservé aux administrateurs",
        )
    return current_user


async def require_role(
    *roles: str,
) -> User:
    """
    Fabrique de dépendance RBAC : n'autorise que les rôles listés.
    Utilisation : `current_user: User = Depends(require_role("admin"))`.
    Renvoie 403 "Accès refusé" pour tout autre rôle.
    """
    allowed = {normalize_role(r) for r in roles}

    async def _checker(
        current_user: User = Depends(get_current_user),
    ) -> User:
        if user_role(current_user) not in allowed:
            raise HTTPException(
                status_code=403,
                detail="Accès refusé",
            )
        return current_user

    return _checker


async def require_verified(
    current_user: User = Depends(get_current_user),
) -> User:
    if not current_user.is_verified and user_role(current_user) != "admin":
        raise HTTPException(
            status_code=403,
            detail="Veuillez d'abord soumettre vos documents pour validation",
        )
    return current_user


# ─── Schémas ────────────────────────────────────────

class UserRegister(BaseModel):
    nom_complet: str = Field(..., min_length=2, max_length=255)
    email: EmailStr
    password: str = Field(..., min_length=8)
    confirm_password: str
    # Pays sélectionné dans le formulaire (table `countries`) + numéro national.
    # Le numéro complet (E.164) est reconstitué côté serveur avec l'indicatif.
    country_id: uuid.UUID = Field(...)
    phone_number: str = Field(..., min_length=3, max_length=15)
    # Rétrocompatibilité : ancien champ "telephone" (E.164 complet) si fourni.
    telephone: str | None = Field(
        default=None, pattern=r"^\+[1-9]\d{6,14}$"
    )
    role: str = Field(..., pattern=r"^(chauffeur|proprietaire|mecanicien)$")

    def passwords_match(self):
        if self.password != self.confirm_password:
            raise ValueError("Les mots de passe ne correspondent pas")
        return self


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: dict


class TokenRefresh(BaseModel):
    refresh_token: str


class ChangePassword(BaseModel):
    old_password: str
    new_password: str = Field(..., min_length=8)


class ForgotPassword(BaseModel):
    email: EmailStr


class VerifyOTP(BaseModel):
    email: EmailStr
    code: str = Field(..., min_length=6, max_length=6)


class ResetPassword(BaseModel):
    email: EmailStr
    code: str = Field(..., min_length=6, max_length=6)
    new_password: str = Field(..., min_length=8)


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    nom_complet: str
    telephone: str
    country_id: uuid.UUID | None = None
    role: str
    photo_profil: str | None = None
    photo_profil_version: int = 0
    date_naissance: str | None = None
    lieu_naissance: str | None = None
    adresse: str | None = None
    bio: str | None = None
    is_verified: bool
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class UserUpdate(BaseModel):
    nom_complet: str | None = None
    telephone: str | None = None
    date_naissance: str | None = None
    lieu_naissance: str | None = None
    adresse: str | None = None
    bio: str | None = None


# ─── Endpoints ──────────────────────────────────────

@router.post("/register", response_model=UserOut, status_code=201)
async def register(data: UserRegister, db: AsyncSession = Depends(get_db)):
    if data.password != data.confirm_password:
        raise HTTPException(status_code=400, detail="Les mots de passe ne correspondent pas")

    # Sûreté maximale : le rôle admin ne peut JAMAIS être créé via /register.
    if data.role == "admin":
        raise HTTPException(status_code=403, detail="Accès refusé")

    from app.models.country import Country
    from app.utils.phone import build_e164, is_valid_national_number

    # 1) Le pays sélectionné doit exister et être actif.
    country_result = await db.execute(
        select(Country).where(
            Country.id == data.country_id, Country.is_active.is_(True)
        )
    )
    country = country_result.scalar_one_or_none()
    if not country:
        raise HTTPException(
            status_code=400,
            detail="Pays invalide. Veuillez sélectionner un pays valide.",
        )

    # 2) Reconstruction du numéro complet : indicatif du pays + numéro national.
    if data.telephone:
        # Rétrocompatibilité : l'ancien champ E.164 reste prioritaire.
        telephone = data.telephone
        from app.utils.phone import national_digits

        if not any(
            telephone.startswith(code)
            for code in (
                await db.execute(
                    select(Country.phone_code).where(Country.is_active.is_(True))
                )
            ).scalars().all()
        ):
            raise HTTPException(
                status_code=400,
                detail="Indicatif international invalide. Veuillez sélectionner un pays valide.",
            )
    else:
        if not is_valid_national_number(country, data.phone_number):
            raise HTTPException(
                status_code=400,
                detail="Veuillez saisir un numéro de téléphone valide pour le pays sélectionné.",
            )
        telephone = build_e164(country, data.phone_number)

    existing = await db.execute(select(User).where(User.email == data.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email déjà utilisé")

    user = User(
        id=uuid.uuid4(),
        email=data.email,
        password_hash=bcrypt.hash(data.password),
        nom_complet=data.nom_complet,
        telephone=telephone,
        country_id=country.id,
        role=data.role,
        is_verified=False,
        is_active=True,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)

    # Crée automatiquement le profil associé au rôle "mecanicien".
    # Sans ce profil, l'upload du justificatif échoue avec
    # "Profil mécanicien non trouvé" (le chauffeur/propriétaire,
    # lui, crée son profil via son formulaire).
    if data.role == "mecanicien":
        from app.models.mecanicien import ProfilMecanicien
        from app.models.enums import TarificationMecanicien

        db.add(
            ProfilMecanicien(
                id=uuid.uuid4(),
                user_id=user.id,
                specialites=[],
                annees_experience=0,
                certifications=[],
                tarification=TarificationMecanicien.payant,
                rayon_intervention=30,
                bio=None,
                photo_url=None,
            )
        )

    from app.services.audit import log_action

    await log_action(
        db,
        user_id=str(user.id),
        action="REGISTER",
        target_type="user",
        target_id=str(user.id),
        details={"role": data.role, "email": user.email, "pays": str(country.id)},
    )

    return user


@router.post("/login", response_model=TokenResponse)
async def login(data: UserLogin, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == data.email))
    user = result.scalar_one_or_none()
    if not user or not bcrypt.verify(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Email ou mot de passe incorrect")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Compte désactivé")

    # Séparation stricte des formulaires : l'administrateur ne peut PAS se
    # connecter via le formulaire des utilisateurs publics. Il passe
    # exclusivement par la route dédiée /api/auth/admin/login (Espace Admin).
    if user_role(user) == "admin":
        raise HTTPException(
            status_code=403,
            detail="Accès réservé. Les administrateurs doivent se connecter via l'Espace Administrateur.",
        )

    role = user_role(user)
    access_token = create_token(str(user.id), "access", role=role, is_verified=user.is_verified, verification_status=user.verification_status)
    refresh_token = create_token(str(user.id), "refresh", role=role, is_verified=user.is_verified, verification_status=user.verification_status)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user={
            "id": str(user.id),
            "email": user.email,
            "nom_complet": user.nom_complet,
            "telephone": user.telephone,
            "country_id": str(user.country_id) if user.country_id else None,
            "role": role,
            "photo_profil": user.photo_profil,
            "photo_profil_version": user.photo_profil_version,
            "date_naissance": user.date_naissance,
            "lieu_naissance": user.lieu_naissance,
            "adresse": user.adresse,
            "bio": user.bio,
            "is_verified": user.is_verified,
            "is_active": user.is_active,
            "verification_status": user.verification_status,
            "verification_reject_motif": user.verification_reject_motif,
            "created_at": str(user.created_at),
        },
    )


@router.post("/admin/login", response_model=TokenResponse)
async def admin_login(data: UserLogin, db: AsyncSession = Depends(get_db)):
    """
    Endpoint de connexion spécifique aux administrateurs.
    Vérifie l'email + mot de passe, puis confirme que le rôle est bien 'admin'.
    Un chauffeur ou un propriétaire ne pourra pas se connecter via cette route.
    """
    result = await db.execute(select(User).where(User.email == data.email))
    user = result.scalar_one_or_none()
    if not user or not bcrypt.verify(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Email ou mot de passe incorrect")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Compte désactivé")
    if user_role(user) != "admin":
        raise HTTPException(
            status_code=403,
            detail="Accès refusé. Privilèges administrateur requis.",
        )

    role = user_role(user)
    access_token = create_token(str(user.id), "access", role=role, is_verified=user.is_verified, verification_status=user.verification_status)
    refresh_token = create_token(str(user.id), "refresh", role=role, is_verified=user.is_verified, verification_status=user.verification_status)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user={
            "id": str(user.id),
            "email": user.email,
            "nom_complet": user.nom_complet,
            "telephone": user.telephone,
            "country_id": str(user.country_id) if user.country_id else None,
            "role": role,
            "photo_profil": user.photo_profil,
            "photo_profil_version": user.photo_profil_version,
            "date_naissance": user.date_naissance,
            "lieu_naissance": user.lieu_naissance,
            "adresse": user.adresse,
            "bio": user.bio,
            "is_verified": user.is_verified,
            "is_active": user.is_active,
            "verification_status": user.verification_status,
            "created_at": str(user.created_at),
        },
    )


@router.get("/me", response_model=UserOut)
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.put("/me", response_model=UserOut)
async def update_me(
    data: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if data.nom_complet is not None:
        current_user.nom_complet = data.nom_complet
    if data.telephone is not None:
        current_user.telephone = data.telephone
    if data.date_naissance is not None:
        current_user.date_naissance = data.date_naissance
    if data.lieu_naissance is not None:
        current_user.lieu_naissance = data.lieu_naissance
    if data.adresse is not None:
        current_user.adresse = data.adresse
    if data.bio is not None:
        current_user.bio = data.bio
    db.add(current_user)
    await db.commit()
    await db.refresh(current_user)
    return current_user


@router.put("/change-password")
async def change_password(
    data: ChangePassword,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not bcrypt.verify(data.old_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="Ancien mot de passe incorrect")
    current_user.password_hash = bcrypt.hash(data.new_password)
    await db.flush()
    return {"message": "Mot de passe modifié avec succès"}


@router.post("/forgot-password")
async def forgot_password(data: ForgotPassword, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == data.email))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=400, detail="Adresse e-mail introuvable")

    # Invalider les anciens OTP
    old_otps = await db.execute(
        select(OTPReset).where(OTPReset.user_id == user.id, OTPReset.used == False)
    )
    for otp in old_otps.scalars():
        otp.used = True

    # Générer un code OTP à 6 chiffres (uniquement des chiffres)
    otp_code = f"{uuid.uuid4().int % 1000000:06d}"
    otp = OTPReset(
        id=uuid.uuid4(),
        user_id=user.id,
        code_hash=bcrypt.hash(otp_code),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
        used=False,
        attempts=0,
    )
    db.add(otp)
    await db.flush()

    # Envoyer l'email avec le code OTP via SMTP
    email_sent = send_otp_email(user.email, otp_code, user.nom_complet)
    if not email_sent:
        raise HTTPException(status_code=500, detail="Échec de l'envoi de l'e-mail")

    return {"message": f"Un code OTP a été envoyé à {data.email}"}


@router.post("/verify-otp")
async def verify_otp(data: VerifyOTP, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == data.email))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=400, detail="Email non trouvé")

    otp_result = await db.execute(
        select(OTPReset)
        .where(OTPReset.user_id == user.id, OTPReset.used == False)
        .order_by(OTPReset.created_at.desc())
        .limit(1)
    )
    otp = otp_result.scalar_one_or_none()

    if not otp:
        raise HTTPException(status_code=400, detail="Aucun code OTP actif")

    if otp.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Code OTP expiré")

    if otp.attempts >= 3:
        otp.used = True
        await db.flush()
        raise HTTPException(status_code=400, detail="Trop de tentatives, demandez un nouveau code")

    otp.attempts += 1
    await db.flush()

    if not bcrypt.verify(data.code, otp.code_hash):
        raise HTTPException(status_code=400, detail="Code OTP incorrect")

    return {"message": "Code OTP vérifié", "valid": True}


@router.post("/reset-password")
async def reset_password(data: ResetPassword, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == data.email))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=400, detail="Email non trouvé")

    otp_result = await db.execute(
        select(OTPReset)
        .where(OTPReset.user_id == user.id, OTPReset.used == False)
        .order_by(OTPReset.created_at.desc())
        .limit(1)
    )
    otp = otp_result.scalar_one_or_none()

    if not otp:
        raise HTTPException(status_code=400, detail="Aucun code OTP actif. Redemandez un nouveau code.")

    if otp.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        otp.used = True
        await db.flush()
        raise HTTPException(status_code=400, detail="Code OTP expiré. Redemandez un nouveau code.")

    if otp.attempts >= 3:
        otp.used = True
        await db.flush()
        raise HTTPException(status_code=400, detail="Trop de tentatives, demandez un nouveau code")

    otp.attempts += 1
    await db.flush()

    if not bcrypt.verify(data.code, otp.code_hash):
        raise HTTPException(status_code=400, detail="Code OTP invalide")

    otp.used = True
    user.password_hash = bcrypt.hash(data.new_password)
    await db.flush()

    return {"message": "Mot de passe mis à jour avec succès. Vous pouvez vous connecter."}


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(data: TokenRefresh, db: AsyncSession = Depends(get_db)):
    payload = decode_token(data.refresh_token)
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Token de rafraîchissement invalide")

    user_id = payload.get("sub")
    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Utilisateur non trouvé ou désactivé")

    role = user_role(user)
    access_token = create_token(str(user.id), "access", role=role, is_verified=user.is_verified, verification_status=user.verification_status)
    refresh_token = create_token(str(user.id), "refresh", role=role, is_verified=user.is_verified, verification_status=user.verification_status)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user={
            "id": str(user.id),
            "email": user.email,
            "nom_complet": user.nom_complet,
            "telephone": user.telephone,
            "country_id": str(user.country_id) if user.country_id else None,
            "role": role,
            "is_verified": user.is_verified,
            "is_active": user.is_active,
            "verification_status": user.verification_status,
        },
    )


@router.post("/logout")
async def logout():
    return {"message": "Déconnexion réussie"}
