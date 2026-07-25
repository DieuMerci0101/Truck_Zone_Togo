from __future__ import annotations

import os
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models.user import User
from app.models.photo_profil import PhotoProfil
from app.routers.auth import get_current_user

settings = get_settings()
router = APIRouter(prefix="/api/users", tags=["Users"])

UPLOAD_DIR = Path("uploads/photos")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
MAX_SIZE = 5 * 1024 * 1024  # 5 MB


def _user_dict(u: User) -> dict:
    return {
        "id": str(u.id),
        "email": u.email,
        "nom_complet": u.nom_complet,
        "telephone": u.telephone,
        "role": u.role.value,
        "photo_profil": u.photo_profil,
        "date_naissance": u.date_naissance,
        "lieu_naissance": u.lieu_naissance,
        "adresse": u.adresse,
        "bio": u.bio,
        "is_verified": u.is_verified,
        "is_active": u.is_active,
        "created_at": str(u.created_at),
    }


class ProfileUpdate(BaseModel):
    nom_complet: str | None = None
    telephone: str | None = None
    date_naissance: str | None = None
    lieu_naissance: str | None = None
    adresse: str | None = None
    bio: str | None = None


# ─── Upload photo de profil ─────────────────────────
@router.put("/me/photo")
async def upload_profile_photo(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ext = Path(file.filename or "photo.jpg").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Format non supporté. Utilisez JPG, PNG ou WebP.")

    content = await file.read()
    if len(content) > MAX_SIZE:
        raise HTTPException(status_code=400, detail="Le fichier ne doit pas dépasser 5 Mo.")

    # Désactiver l'ancienne photo active
    old_photos = await db.execute(
        select(PhotoProfil).where(
            PhotoProfil.user_id == current_user.id,
            PhotoProfil.is_active == True,
        )
    )
    for old in old_photos.scalars().all():
        old.is_active = False
        db.add(old)

    # Sauvegarder le fichier
    filename = f"{current_user.id}_{uuid.uuid4().hex[:8]}{ext}"
    filepath = UPLOAD_DIR / filename
    filepath.write_bytes(content)

    photo_url = f"/uploads/photos/{filename}"

    # Créer l'enregistrement en base
    photo_record = PhotoProfil(
        user_id=current_user.id,
        filename=filename,
        original_name=file.filename or "photo.jpg",
        file_path=photo_url,
        file_size=len(content),
        mime_type=file.content_type or "image/jpeg",
        is_active=True,
    )
    db.add(photo_record)

    current_user.photo_profil = photo_url
    db.add(current_user)
    await db.commit()
    await db.refresh(current_user)

    return {"photo_url": photo_url, "message": "Photo de profil mise à jour", "user": _user_dict(current_user)}


# ─── Supprimer photo de profil ─────────────────────
@router.delete("/me/photo")
async def delete_profile_photo(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not current_user.photo_profil:
        raise HTTPException(status_code=400, detail="Aucune photo de profil à supprimer")

    old_photos = await db.execute(
        select(PhotoProfil).where(
            PhotoProfil.user_id == current_user.id,
            PhotoProfil.is_active == True,
        )
    )
    for old in old_photos.scalars().all():
        old.is_active = False
        db.add(old)

    if current_user.photo_profil and current_user.photo_profil.startswith("/uploads/"):
        disk_path = Path(current_user.photo_profil.lstrip("/"))
        if disk_path.exists():
            disk_path.unlink(missing_ok=True)

    current_user.photo_profil = None
    db.add(current_user)
    await db.commit()
    await db.refresh(current_user)

    return {"message": "Photo de profil supprimée", "user": _user_dict(current_user)}


# ─── Modifier le profil complet ────────────────────
@router.put("/me/profile")
async def update_profile(
    data: ProfileUpdate,
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

    return {"message": "Profil mis à jour", "user": _user_dict(current_user)}


# ─── Historique des photos ─────────────────────────
@router.get("/me/photos")
async def get_my_photos(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(PhotoProfil)
        .where(PhotoProfil.user_id == current_user.id)
        .order_by(PhotoProfil.created_at.desc())
    )
    photos = result.scalars().all()
    return [
        {
            "id": str(p.id),
            "file_path": p.file_path,
            "original_name": p.original_name,
            "file_size": p.file_size,
            "mime_type": p.mime_type,
            "is_active": p.is_active,
            "created_at": str(p.created_at),
        }
        for p in photos
    ]


# ─── infos profil rapide ───────────────────────────
@router.get("/me")
async def get_my_profile(current_user: User = Depends(get_current_user)):
    return _user_dict(current_user)
