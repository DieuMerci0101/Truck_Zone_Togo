"""
Stockage persistant et centralisé des fichiers uploadés.

Tous les fichiers sont écrits sous `uploads/permanent/<categorie>/` :
un dossier dédié et persistant, jamais purgé par une tâche de nettoyage
automatique. Les anciens fichiers ne sont supprimés que lors d'une
suppression explicite (endpoints DELETE) — jamais par le serveur seul.

Chaque fichier est référencé en base par une URL relative servie par le
montage statique FastAPI `/uploads` : ces liens restent valides aussi
longtemps que le fichier existe sur disque.
"""
from __future__ import annotations

import uuid
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent  # backend/
UPLOADS_ROOT = BASE_DIR / "uploads"
PERMANENT_DIR = UPLOADS_ROOT / "permanent"

# Catégories de fichiers et leur dossier persistant dédié.
CATEGORIES: dict[str, Path] = {
    "photos": PERMANENT_DIR / "photos",
    "camions": PERMANENT_DIR / "camions",
    "documents": PERMANENT_DIR / "documents",
    "justificatifs": PERMANENT_DIR / "justificatifs",
    "audios": PERMANENT_DIR / "audios",
}


def ensure_dirs() -> None:
    """Crée tous les dossiers de stockage s'ils n'existent pas."""
    for directory in CATEGORIES.values():
        directory.mkdir(parents=True, exist_ok=True)


def save_upload(content: bytes, category: str, ext: str = "") -> str:
    """
    Écrit un fichier dans `uploads/permanent/<category>/` et retourne son
    URL relative (ex: `/uploads/permanent/photos/abc123.jpg`).

    Le nom de fichier est un UUID aléatoire : unique à chaque upload, ce qui
    fournit nativement une invalidation de cache (nouvelle URL = nouvelle
    ressource côté navigateur).
    """
    category = (category or "").lower()
    directory = CATEGORIES.get(category)
    if directory is None:
        raise ValueError(f"Catégorie de stockage inconnue : {category}")

    directory.mkdir(parents=True, exist_ok=True)
    ext = (ext or "").lower()
    if ext and not ext.startswith("."):
        ext = f".{ext}"
    filename = f"{uuid.uuid4().hex}{ext}"
    (directory / filename).write_bytes(content)
    return f"/uploads/permanent/{category}/{filename}"


def delete_upload(url: str | None) -> bool:
    """
    Supprime un fichier servi sous `/uploads/...` (chemin relatif).
    Idempotent : ne lève jamais d'erreur si le fichier est déjà absent.
    """
    if not url or not url.startswith("/uploads/"):
        return False
    disk_path = UPLOADS_ROOT / url.removeprefix("/uploads/")
    try:
        if disk_path.exists() and disk_path.is_file():
            disk_path.unlink()
            return True
    except OSError:
        pass
    return False
