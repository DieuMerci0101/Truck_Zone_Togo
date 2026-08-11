import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.document import Document
from app.models.enums import TypeDocument
from app.models.user import User
from app.routers.auth import get_current_user
from app.routers.chauffeurs import (
    DOCUMENT_ALLOWED_EXTENSIONS,
    DOCUMENT_MAX_FILE_SIZE,
)
from app.services.audit import log_action
from app.services.storage import save_upload

router = APIRouter(prefix="/api/documents", tags=["Documents"])

MAX_FILES_PER_UPLOAD = 20


@router.post("/upload", status_code=201)
async def upload_documents(
    type_document: str = Form("autre"),
    files: list[UploadFile] = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload multi-fichiers pour un utilisateur connecté.

    - Enregistre chaque fichier dans /uploads/documents/
    - Stocke chaque enregistrement dans la table `documents`, relié au user_id
    - Bascule automatiquement le compte en `pending_approval` dès que tous les
      documents requis sont soumis
    """
    type_doc_enum = None
    for td in TypeDocument:
        if td.value == type_document:
            type_doc_enum = td
            break
    if not type_doc_enum:
        raise HTTPException(status_code=400, detail="Type de document invalide")

    if len(files) > MAX_FILES_PER_UPLOAD:
        raise HTTPException(
            status_code=400,
            detail=f"Trop de fichiers ({MAX_FILES_PER_UPLOAD} maximum).",
        )

    created = []

    for file in files:
        ext = os.path.splitext(file.filename or "")[1].lower()
        if ext not in DOCUMENT_ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"Format non supporté pour « {file.filename} ». JPG/PNG/PDF uniquement.",
            )

        content = await file.read()
        if len(content) > DOCUMENT_MAX_FILE_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"Le fichier « {file.filename} » est trop lourd (10 Mo max).",
            )

        # Stockage persistant centralisé : les documents KYC ne sont jamais
        # purgés automatiquement, ils restent récupérables même des années
        # après (lié au user_id via la table `documents`).
        fichier_url = save_upload(content, "documents", ext)

        doc = Document(
            id=uuid.uuid4(),
            utilisateur_id=current_user.id,
            type_document=type_doc_enum,
            fichier_url=fichier_url,
            statut="en_attente",
        )
        db.add(doc)
        created.append(
            {
                "id": str(doc.id),
                "url": doc.fichier_url,
                "type_document": type_doc_enum.value,
            }
        )

    await db.flush()

    from app.utils.verification import sync_verification_after_upload

    await sync_verification_after_upload(db, current_user)

    await log_action(
        db,
        user_id=str(current_user.id),
        action="UPLOAD_DOCUMENT",
        target_type="user",
        target_id=str(current_user.id),
        details={
            "type_document": type_doc_enum.value,
            "nb_fichiers": len(created),
            "urls": [c["url"] for c in created],
        },
    )

    await db.commit()

    return {"message": f"{len(created)} document(s) uploadé(s)", "documents": created}
