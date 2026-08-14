"""
Stockage persistant et centralisé des fichiers uploadés.

Deux modes, choisis automatiquement :

1. **Cloud (Supabase Storage)** — si `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY`
   sont définis. Les fichiers sont téléversés dans un bucket PUBLIC via l'API
   REST (`/storage/v1/object`), et l'URL publique absolue retournée est
   enregistrée en base. Fichiers permanents, indépendants de l'instance
   (indispensable sur Render gratuit dont le disque est effacé à chaque
   redémarrage).

2. **Disque local (repli)** — si Supabase n'est pas configuré. Écriture sous
   `uploads/permanent/<categorie>/`, URL relative servie par le montage
   statique `/uploads`. Utilisé en développement local ou tant que la
   migration n'est pas activée.

Les anciens fichiers ne sont supprimés que lors d'une suppression explicite
(endpoints DELETE) — jamais par le serveur seul. Idempotent : `delete_upload`
ne lève jamais d'erreur si le fichier est déjà absent.
"""
from __future__ import annotations

import logging
import uuid
from pathlib import Path

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent.parent  # backend/
UPLOADS_ROOT = BASE_DIR / "uploads"
PERMANENT_DIR = UPLOADS_ROOT / "permanent"

# Catégories de fichiers et leur dossier persistant dédié (mode local).
CATEGORIES: dict[str, Path] = {
    "photos": PERMANENT_DIR / "photos",
    "camions": PERMANENT_DIR / "camions",
    "documents": PERMANENT_DIR / "documents",
    "justificatifs": PERMANENT_DIR / "justificatifs",
    "audios": PERMANENT_DIR / "audios",
}

# Association extension → Content-Type (utilisé par l'API Supabase pour
# stocker et servir le bon type MIME).
_MIME_TYPES: dict[str, str] = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".mp4": "video/mp4",
    ".webm": "video/webm",
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".ogg": "audio/ogg",
    ".wav": "audio/wav",
    ".pdf": "application/pdf",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".txt": "text/plain",
}


def ensure_dirs() -> None:
    """Crée tous les dossiers de stockage s'ils n'existent pas (mode local)."""
    for directory in CATEGORIES.values():
        directory.mkdir(parents=True, exist_ok=True)


def _supabase_configured() -> bool:
    settings = get_settings()
    return bool(settings.supabase_url and settings.supabase_service_role_key)


def _public_base_url() -> str:
    """Racine des URLs publiques du bucket Supabase (sans slash final)."""
    settings = get_settings()
    return (
        f"{settings.supabase_url.rstrip('/')}"
        f"/storage/v1/object/public/{settings.supabase_bucket}"
    )


def _upload_to_supabase(content: bytes, key: str, content_type: str) -> str:
    """Téléverse `content` vers `key` du bucket public. Retourne l'URL publique."""
    settings = get_settings()
    url = (
        f"{settings.supabase_url.rstrip('/')}"
        f"/storage/v1/object/{settings.supabase_bucket}/{key}"
    )
    headers = {
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
        "content-type": content_type,
    }
    resp = httpx.put(url, content=content, headers=headers, timeout=30)
    if resp.status_code >= 400:
        logger.error(
            "[STORAGE] Upload Supabase échoué (%s %s) pour %s : %s",
            resp.status_code,
            resp.reason_phrase,
            key,
            resp.text[:300],
        )
        raise RuntimeError(
            f"Upload Supabase refusé (HTTP {resp.status_code}): {resp.text[:200]}"
        )
    public_url = f"{_public_base_url()}/{key}"
    logger.info("[STORAGE] Fichier téléversé sur Supabase : %s", public_url)
    return public_url


def _delete_from_supabase(public_url: str) -> bool:
    """Supprime un objet Supabase à partir de son URL publique absolue."""
    settings = get_settings()
    prefix = f"{_public_base_url()}/"
    if not public_url.startswith(prefix):
        return False
    key = public_url.removeprefix(prefix)
    url = (
        f"{settings.supabase_url.rstrip('/')}"
        f"/storage/v1/object/{settings.supabase_bucket}/{key}"
    )
    headers = {
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
    }
    resp = httpx.delete(url, headers=headers, timeout=30)
    if resp.status_code >= 400 and resp.status_code != 404:
        logger.warning(
            "[STORAGE] Suppression Supabase échouée (%s %s) pour %s : %s",
            resp.status_code,
            resp.reason_phrase,
            key,
            resp.text[:200],
        )
        return False
    logger.info("[STORAGE] Fichier supprimé sur Supabase : %s", key)
    return True


def save_upload(content: bytes, category: str, ext: str = "") -> str:
    """
    Écrit un fichier et retourne son URL publique.

    - Supabase configuré → URL absolue `https://...storage.../public/<cat>/<uuid>.<ext>`.
    - Sinon → URL relative `/uploads/permanent/<cat>/<uuid>.<ext>` (disque local).

    Le nom de fichier est un UUID aléatoire : unique à chaque upload, ce qui
    fournit nativement une invalidation de cache (nouvelle URL = nouvelle
    ressource côté navigateur).
    """
    category = (category or "").lower()
    if category not in CATEGORIES:
        raise ValueError(f"Catégorie de stockage inconnue : {category}")

    ext = (ext or "").lower()
    if ext and not ext.startswith("."):
        ext = f".{ext}"
    filename = f"{uuid.uuid4().hex}{ext}"
    key = f"{category}/{filename}"

    if _supabase_configured():
        content_type = _MIME_TYPES.get(ext, "application/octet-stream")
        return _upload_to_supabase(content, key, content_type)

    directory = CATEGORIES[category]
    directory.mkdir(parents=True, exist_ok=True)
    (directory / filename).write_bytes(content)
    return f"/uploads/permanent/{category}/{filename}"


def delete_upload(url: str | None) -> bool:
    """
    Supprime un fichier, qu'il soit cloud (URL absolue Supabase) ou local
    (chemin relatif `/uploads/...`). Idempotent, ne lève jamais d'erreur.
    """
    if not url:
        return False
    if _supabase_configured() and url.startswith("https://"):
        try:
            return _delete_from_supabase(url)
        except Exception as exc:  # pragma: no cover - défense en profondeur
            logger.warning("[STORAGE] Échec suppression cloud : %s", exc)
            return False
    if url.startswith("/uploads/"):
        disk_path = UPLOADS_ROOT / url.removeprefix("/uploads/")
        try:
            if disk_path.exists() and disk_path.is_file():
                disk_path.unlink()
                return True
        except OSError:
            pass
    return False
