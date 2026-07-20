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

settings = get_settings()
security = HTTPBearer(auto_error=False)

router = APIRouter(prefix="/api/auth", tags=["Auth"])


# ─── Helpers ────────────────────────────────────────

def create_token(user_id: str, token_type: str = "access") -> str:
    if token_type == "access":
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    else:
        expire = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)
    payload = {
        "sub": user_id,
        "type": token_type,
        "exp": expire,
    }
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
    if current_user.role.value != "admin":
        raise HTTPException(
            status_code=403,
            detail="Accès réservé aux administrateurs",
        )
    return current_user


# ─── Schémas ────────────────────────────────────────

class UserRegister(BaseModel):
    nom_complet: str = Field(..., min_length=2, max_length=255)
    email: EmailStr
    password: str = Field(..., min_length=8)
    confirm_password: str
    telephone: str = Field(..., pattern=r"^\+228\d{8}$")
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
    role: str
    is_verified: bool
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class UserUpdate(BaseModel):
    nom_complet: str | None = None
    telephone: str | None = None


# ─── Endpoints ──────────────────────────────────────

@router.post("/register", response_model=UserOut, status_code=201)
async def register(data: UserRegister, db: AsyncSession = Depends(get_db)):
    if data.password != data.confirm_password:
        raise HTTPException(status_code=400, detail="Les mots de passe ne correspondent pas")

    existing = await db.execute(select(User).where(User.email == data.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email déjà utilisé")

    user = User(
        id=uuid.uuid4(),
        email=data.email,
        password_hash=bcrypt.hash(data.password),
        nom_complet=data.nom_complet,
        telephone=data.telephone,
        role=data.role,
        is_verified=True,
        is_active=True,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return user


@router.post("/login", response_model=TokenResponse)
async def login(data: UserLogin, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == data.email))
    user = result.scalar_one_or_none()
    if not user or not bcrypt.verify(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Email ou mot de passe incorrect")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Compte désactivé")

    access_token = create_token(str(user.id), "access")
    refresh_token = create_token(str(user.id), "refresh")

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user={
            "id": str(user.id),
            "email": user.email,
            "nom_complet": user.nom_complet,
            "role": user.role,
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
    if user.role.value != "admin":
        raise HTTPException(
            status_code=403,
            detail="Ce compte n'est pas un administrateur",
        )

    access_token = create_token(str(user.id), "access")
    refresh_token = create_token(str(user.id), "refresh")

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user={
            "id": str(user.id),
            "email": user.email,
            "nom_complet": user.nom_complet,
            "role": user.role,
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
    if data.nom_complet:
        current_user.nom_complet = data.nom_complet
    if data.telephone:
        current_user.telephone = data.telephone
    await db.flush()
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

    if user:
        # Invalider les anciens OTP
        old_otps = await db.execute(
            select(OTPReset).where(OTPReset.user_id == user.id, OTPReset.used == False)
        )
        for otp in old_otps.scalars():
            otp.used = True

        # Générer un code OTP à 6 chiffres
        otp_code = str(uuid.uuid4().int)[:6]
        otp = OTPReset(
            id=uuid.uuid4(),
            user_id=user.id,
            code_hash=bcrypt.hash(otp_code),
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
            used=False,
            attempts=0,
        )
        db.add(otp)
        await db.flush()

    # Toujours renvoyer le même message (sécurité)
    return {"message": "Si cet email existe, un code OTP a été envoyé"}


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

    if not otp or not bcrypt.verify(data.code, otp.code_hash):
        raise HTTPException(status_code=400, detail="Code OTP invalide")

    otp.used = True
    user.password_hash = bcrypt.hash(data.new_password)
    await db.flush()

    return {"message": "Mot de passe réinitialisé avec succès"}


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

    access_token = create_token(str(user.id), "access")
    refresh_token = create_token(str(user.id), "refresh")

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user={
            "id": str(user.id),
            "email": user.email,
            "nom_complet": user.nom_complet,
            "role": user.role,
        },
    )


@router.post("/logout")
async def logout():
    return {"message": "Déconnexion réussie"}
