"""
Router admin — Toutes les routes de ce fichier sont réservées aux administrateurs.

Chaque endpoint utilise la dependency `require_admin` qui vérifie :
1. Que l'utilisateur est authentifié (token JWT valide)
2. Que le rôle de l'utilisateur est bien "admin"
3. Sinon, renvoie une erreur HTTP 403 (Accès interdit)

Utilisation :
from app.routers.auth import require_admin, user_role

    @router.get("/admin/users")
    async def list_users(admin: User = Depends(require_admin)):
        ...
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.models.chauffeur import ProfilChauffeur
from app.models.proprietaire import ProfilProprietaire
from app.models.mecanicien import ProfilMecanicien
from app.models.incident import Incident
from app.models.assistance import DemandeAssistance
from app.models.camion import Camion
from app.schemas.incident import IncidentOut
from app.schemas.mecanicien import AssistanceOut, MecanicienVerificationUpdate
from app.routers.auth import require_admin

router = APIRouter(prefix="/api/admin", tags=["Admin"])


# ─── Statistiques du dashboard ─────────────────────

@router.get("/stats")
async def get_stats(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Retourne les statistiques globales pour le dashboard admin.
    Protégé : uniquement les administrateurs.
    """
    total_users = (await db.execute(select(func.count()).select_from(User))).scalar() or 0
    total_chauffeurs = (
        await db.execute(
            select(func.count()).select_from(User).where(User.role == "chauffeur")
        )
    ).scalar() or 0
    total_proprietaires = (
        await db.execute(
            select(func.count()).select_from(User).where(User.role == "proprietaire")
        )
    ).scalar() or 0
    total_mecaniciens = (
        await db.execute(
            select(func.count()).select_from(User).where(User.role == "mecanicien")
        )
    ).scalar() or 0
    total_admins = (
        await db.execute(
            select(func.count()).select_from(User).where(User.role == "admin")
        )
    ).scalar() or 0
    total_camions = (
        await db.execute(select(func.count()).select_from(Camion))
    ).scalar() or 0

    return {
        "total_utilisateurs": total_users,
        "chauffeurs": total_chauffeurs,
        "proprietaires": total_proprietaires,
        "mecaniciens": total_mecaniciens,
        "admins": total_admins,
        "camions": total_camions,
    }


# ─── Assistance mécanique (supervision admin) ─────

@router.get("/assistance", response_model=dict)
async def list_all_assistance(
    statut: str | None = None,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy.orm import selectinload

    query = (
        select(DemandeAssistance)
        .options(
            selectinload(DemandeAssistance.demandeur),
            selectinload(DemandeAssistance.mecanicien).selectinload(ProfilMecanicien.user),
        )
        .order_by(DemandeAssistance.created_at.desc())
    )
    if statut:
        query = query.where(DemandeAssistance.statut == statut)
    result = await db.execute(query)
    demandes = result.scalars().all()

    total = len(demandes)
    en_attente = sum(1 for d in demandes if d.statut == "en_attente")
    pris_en_charge = sum(1 for d in demandes if d.statut == "pris_en_charge")
    terminee = sum(1 for d in demandes if d.statut == "terminee")

    return {
        "total": total,
        "en_attente": en_attente,
        "pris_en_charge": pris_en_charge,
        "terminee": terminee,
        "demandes": [AssistanceOut.model_validate(d) for d in demandes],
    }


# ─── Gestion des utilisateurs ──────────────────────

@router.get("/users")
async def list_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    role: str | None = None,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Liste tous les utilisateurs avec filtres optionnels.
    Protégé : uniquement les administrateurs.
    """
    query = select(User)
    if role:
        query = query.where(User.role == role)
    query = query.order_by(User.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    users = result.scalars().all()
    return [
        {
            "id": str(u.id),
            "email": u.email,
            "nom_complet": u.nom_complet,
            "telephone": u.telephone,
            "role": u.role.value if hasattr(u.role, "value") else u.role,
            "is_active": u.is_active,
            "is_verified": u.is_verified,
            "created_at": u.created_at.isoformat(),
        }
        for u in users
    ]


@router.get("/users/{user_id}")
async def get_user(
    user_id: uuid.UUID,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Récupère les détails d'un utilisateur spécifique.
    Protégé : uniquement les administrateurs.
    """
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")
    return {
        "id": str(user.id),
        "email": user.email,
        "nom_complet": user.nom_complet,
        "telephone": user.telephone,
        "role": user.role.value if hasattr(user.role, "value") else user.role,
        "is_active": user.is_active,
        "is_verified": user.is_verified,
        "created_at": user.created_at.isoformat(),
    }


@router.put("/users/{user_id}/status")
async def toggle_user_status(
    user_id: uuid.UUID,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Active ou désactive un utilisateur.
    Protégé : uniquement les administrateurs.
    """
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")

    # Un admin ne peut pas se désactiver lui-même
    if user.id == admin.id:
        raise HTTPException(status_code=400, detail="Vous ne pouvez pas désactiver votre propre compte")

    user.is_active = not user.is_active
    await db.flush()
    return {
        "message": f"Utilisateur {'activé' if user.is_active else 'désactivé'} avec succès",
        "is_active": user.is_active,
    }


# ─── Gestion des documents ─────────────────────────

@router.get("/documents")
async def list_all_documents(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    statut: str | None = None,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Liste tous les documents uploadés par les utilisateurs.
    Protégé : uniquement les administrateurs.
    """
    from app.models.document import Document
    from sqlalchemy.orm import joinedload
    query = select(Document).options(joinedload(Document.utilisateur))
    if statut:
        query = query.where(Document.statut == statut)
    query = query.order_by(Document.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    docs = result.unique().scalars().all()
    return [
        {
            "id": str(d.id),
            "utilisateur_id": str(d.utilisateur_id),
            "utilisateur_nom": d.utilisateur.nom_complet if d.utilisateur else None,
            "utilisateur_email": d.utilisateur.email if d.utilisateur else None,
            "utilisateur_role": d.utilisateur.role.value if d.utilisateur and hasattr(d.utilisateur.role, "value") else (d.utilisateur.role if d.utilisateur else None),
            "type_document": d.type_document.value if hasattr(d.type_document, "value") else d.type_document,
            "fichier_url": d.fichier_url,
            "statut": d.statut.value if hasattr(d.statut, "value") else d.statut,
            "created_at": d.created_at.isoformat(),
        }
        for d in docs
    ]


from pydantic import BaseModel


class DocumentStatutUpdate(BaseModel):
    statut: str
    motif: str | None = None


@router.put("/documents/{document_id}/statut")
async def update_document_statut(
    document_id: uuid.UUID,
    body: DocumentStatutUpdate,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Met à jour le statut d'un document (validé, rejeté, en_attente).
    Protégé : uniquement les administrateurs.
    Envoie une notification à l'utilisateur concerné.
    En cas de rejet, envoie un email avec le motif et sauvegarde le commentaire.
    """
    from app.models.document import Document
    from app.utils.notifications import notify_user
    from app.utils.email import send_document_rejection_email
    from app.utils.verification import set_verification_status, APPROVED, REJECTED, REQUIRED_DOCS_BY_ROLE
    from sqlalchemy.orm import selectinload

    statut = body.statut
    motif = body.motif

    result = await db.execute(
        select(Document)
        .where(Document.id == document_id)
        .options(selectinload(Document.utilisateur))
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document non trouvé")

    if statut == "rejete" and not motif:
        raise HTTPException(status_code=422, detail="Un motif de rejet est obligatoire")

    doc.statut = statut
    doc.validated_at = datetime.now(timezone.utc)
    doc.commentaire_admin = motif if statut == "rejete" else None

    lien_documents = f"/dashboard/{user_role(doc.utilisateur)}/documents"

    if statut == "valide":
        await notify_user(
            db,
            user_id=doc.utilisateur_id,
            titre="Document validé",
            contenu=f"Votre document de type « {doc.type_document.value if hasattr(doc.type_document, 'value') else doc.type_document} » a été validé par un administrateur.",
            type_notif="document",
            lien=lien_documents,
        )
        user_result = await db.execute(select(User).where(User.id == doc.utilisateur_id))
        user = user_result.scalar_one_or_none()
        if user:
            role_types = REQUIRED_DOCS_BY_ROLE.get(user_role(user))
            if role_types:
                docs_result = await db.execute(
                    select(Document).where(
                        Document.utilisateur_id == user.id,
                        Document.type_document.in_(role_types),
                    )
                )
                all_docs = docs_result.scalars().all()
                validated_types = {d.type_document.value if hasattr(d.type_document, 'value') else d.type_document for d in all_docs if d.statut == "valide"}
                if set(role_types).issubset(validated_types):
                    set_verification_status(user, APPROVED)
            else:
                set_verification_status(user, APPROVED)
    elif statut == "rejete":
        await notify_user(
            db,
            user_id=doc.utilisateur_id,
            titre="Document rejeté",
            contenu=f"Votre document de type « {doc.type_document.value if hasattr(doc.type_document, 'value') else doc.type_document} » a été rejeté. Motif : {motif}",
            type_notif="document",
            lien=lien_documents,
        )
        # Envoi email de rejet
        user_result = await db.execute(select(User).where(User.id == doc.utilisateur_id))
        user = user_result.scalar_one_or_none()
        if user:
            # Synchronise le statut global du compte
            set_verification_status(user, REJECTED, motif=motif)
            doc_label = doc.type_document.value if hasattr(doc.type_document, 'value') else doc.type_document
            send_document_rejection_email(
                to_email=user.email,
                user_name=user.nom_complet or "",
                document_type=doc_label,
                motif=motif,
            )

    await db.flush()
    return {"message": f"Statut du document mis à jour : {statut}"}


# ─── Vérification des mécaniciens ───────────────────

@router.get("/mechanics/pending")
async def list_pending_mechanics(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    statut: str | None = None,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Liste les mécaniciens en attente de vérification (justificatif soumis).
    Protégé : uniquement les administrateurs.
    """
    from sqlalchemy.orm import selectinload

    query = select(ProfilMecanicien).options(
        selectinload(ProfilMecanicien.user)
    )
    if statut:
        query = query.where(ProfilMecanicien.verification_status == statut)
    else:
        query = query.where(ProfilMecanicien.verification_status != "approved")
    query = query.order_by(ProfilMecanicien.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    profils = result.scalars().all()
    return [
        {
            "id": str(p.id),
            "user_id": str(p.user_id),
            "nom_complet": p.user.nom_complet if p.user else None,
            "email": p.user.email if p.user else None,
            "telephone": p.user.telephone if p.user else None,
            "specialites": p.specialites,
            "annees_experience": p.annees_experience,
            "tarification": p.tarification.value if hasattr(p.tarification, "value") else p.tarification,
            "proof_document_url": p.proof_document_url,
            "verification_status": p.verification_status,
            "created_at": p.created_at.isoformat(),
        }
        for p in profils
    ]


@router.put("/verify-mechanic/{mecanicien_id}")
async def verify_mechanic(
    mecanicien_id: uuid.UUID,
    body: MecanicienVerificationUpdate,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Approuve ou rejette le justificatif d'un mécanicien.
    Protégé : uniquement les administrateurs.
    Envoie une notification au mécanicien concerné.
    """
    from sqlalchemy.orm import selectinload
    from app.utils.notifications import notify_user
    from app.utils.email import (
        send_verification_rejection_email,
        send_verification_approved_email,
    )
    from app.utils.verification import set_verification_status, APPROVED, REJECTED

    result = await db.execute(
        select(ProfilMecanicien)
        .where(ProfilMecanicien.id == mecanicien_id)
        .options(selectinload(ProfilMecanicien.user))
    )
    profil = result.scalar_one_or_none()
    if not profil:
        raise HTTPException(status_code=404, detail="Mécanicien non trouvé")

    motif = body.motif.strip() if body.motif else None
    if body.statut == REJECTED and not motif:
        raise HTTPException(status_code=422, detail="Un motif de rejet est obligatoire")

    profil.verification_status = body.statut
    lien = "/dashboard/mecanicien"

    if body.statut == "approved":
        profil.verification_status = "approved"
        if profil.user:
            set_verification_status(profil.user, APPROVED)
            await notify_user(
                db,
                user_id=profil.user_id,
                titre="Compte mécanicien approuvé",
                contenu="Votre justificatif a été approuvé. Vous avez maintenant accès à l'ensemble des fonctionnalités.",
                type_notif="document",
                lien=lien,
            )
            send_verification_approved_email(
                to_email=profil.user.email,
                user_name=profil.user.nom_complet or "",
                role="mecanicien",
            )
    else:
        profil.verification_status = "rejected"
        if profil.user:
            set_verification_status(profil.user, REJECTED, motif=motif)
            await notify_user(
                db,
                user_id=profil.user_id,
                titre="Compte mécanicien rejeté",
                contenu=f"Votre justificatif a été rejeté. Motif : {motif}. Veuillez soumettre un nouveau document.",
                type_notif="document",
                lien=lien,
            )
            send_verification_rejection_email(
                to_email=profil.user.email,
                user_name=profil.user.nom_complet or "",
                motif=motif,
                role="mecanicien",
            )

    await db.flush()
    return {
        "message": f"Vérification du mécanicien : {body.statut}",
        "verification_status": profil.verification_status,
    }


# ─── Vérification unifiée des comptes (tous rôles) ──


class VerificationDecision(BaseModel):
    """Décision admin : approuver ou rejeter le dossier d'inscription d'un utilisateur."""
    statut: str = Field(..., pattern=r"^(approved|rejected)$")
    motif: str | None = None


@router.get("/verifications")
async def list_verifications(
    statut: str | None = None,
    role: str | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Liste les dossiers d'inscription avec leurs documents pour l'espace admin.
    Le paramètre `statut` accepte un ou plusieurs statuts séparés par des virgules
    (ex. "pending_upload,pending_approval" pour le filtre "En attente").
    Protégé : uniquement les administrateurs.
    """
    from app.utils.verification import REQUIRED_DOCS_BY_ROLE
    from app.models.document import Document

    query = select(User).where(User.role != "admin")
    if statut:
        statuts = [s.strip() for s in statut.split(",") if s.strip()]
        if statuts:
            query = query.where(User.verification_status.in_(statuts))
    if role:
        query = query.where(User.role == role)
    query = query.order_by(User.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    users = result.scalars().all()

    user_ids = [u.id for u in users]
    docs_by_user: dict[str, list[dict]] = {}
    if user_ids:
        docs_result = await db.execute(
            select(Document)
            .where(Document.utilisateur_id.in_(user_ids))
            .order_by(Document.created_at.desc())
        )
        for d in docs_result.scalars().all():
            docs_by_user.setdefault(str(d.utilisateur_id), []).append(
                {
                    "id": str(d.id),
                    "type_document": d.type_document.value if hasattr(d.type_document, "value") else d.type_document,
                    "fichier_url": d.fichier_url,
                    "statut": d.statut.value if hasattr(d.statut, "value") else d.statut,
                    "commentaire_admin": d.commentaire_admin,
                    "validated_at": d.validated_at.isoformat() if d.validated_at else None,
                    "created_at": d.created_at.isoformat(),
                }
            )

    mechanic_user_ids = [u.id for u in users if user_role(u) == "mecanicien"]
    proof_by_user: dict[str, dict] = {}
    if mechanic_user_ids:
        profils_result = await db.execute(
            select(ProfilMecanicien).where(ProfilMecanicien.user_id.in_(mechanic_user_ids))
        )
        for p in profils_result.scalars().all():
            proof_by_user[str(p.user_id)] = {
                "id": str(p.id),
                "type_document": "justificatif",
                "fichier_url": p.proof_document_url,
                "statut": p.verification_status,
                "commentaire_admin": None,
                "validated_at": None,
                "created_at": p.created_at.isoformat() if p.created_at else None,
            }

    items = []
    for u in users:
        required = REQUIRED_DOCS_BY_ROLE.get(user_role(u), [])
        docs = docs_by_user.get(str(u.id), [])
        if user_role(u) == "mecanicien":
            proof = proof_by_user.get(str(u.id))
            docs = [proof] if proof and proof.get("fichier_url") else []
        submitted = {d["type_document"] for d in docs}
        # Aplatit les groupes de documents requis en une liste de types simples
        # (ex: [["permis"], ["cni","passeport"]] → ["permis","cni","passeport"]).
        # Un groupe est considéré soumis dès que l'UN de ses types est présent,
        # sinon tous les types du groupe sont marqués manquants.
        required_flat: list[str] = []
        missing_flat: list[str] = []
        for group in required:
            group_types = group if isinstance(group, (list, tuple, set)) else [group]
            required_flat.extend(group_types)
            if not any(t in submitted for t in group_types):
                missing_flat.extend(group_types)
        submitted_dates = [d.get("created_at") for d in docs if d.get("created_at")]
        soumis_le = max(submitted_dates) if submitted_dates else (
            u.created_at.isoformat() if u.created_at else None
        )
        items.append(
            {
                "user_id": str(u.id),
                "nom_complet": u.nom_complet,
                "email": u.email,
                "telephone": u.telephone,
                "photo_profil": u.photo_profil,
                "role": u.role.value,
                "is_verified": u.is_verified,
                "verification_status": u.verification_status,
                "verification_reject_motif": u.verification_reject_motif,
                "required_documents": required_flat,
                "missing_documents": missing_flat,
                "documents": docs,
                "created_at": u.created_at.isoformat() if u.created_at else None,
                "soumis_le": soumis_le,
            }
        )
    return items


@router.put("/verifications/{user_id}")
async def decide_verification(
    user_id: uuid.UUID,
    body: VerificationDecision,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Approuve ou rejette le dossier d'inscription d'un utilisateur (tous rôles).
    - [VALIDER] : statut -> approved / is_verified = True, les documents sont marqués validés.
    - [REJETER] : motif obligatoire, statut -> rejected, notification + email avec le motif.
    Protégé : uniquement les administrateurs.
    """
    from app.utils.notifications import notify_user
    from app.utils.email import (
        send_verification_rejection_email,
        send_verification_approved_email,
    )
    from app.utils.verification import set_verification_status, APPROVED, REJECTED
    from app.models.document import Document

    motif = body.motif.strip() if body.motif else None
    if body.statut == REJECTED and not motif:
        raise HTTPException(status_code=422, detail="Un motif de rejet est obligatoire")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")
    if user.role.value == "admin":
        raise HTTPException(status_code=400, detail="Impossible de vérifier un compte administrateur")

    role = user.role.value

    if body.statut == APPROVED:
        set_verification_status(user, APPROVED)
        if role in ("chauffeur", "proprietaire"):
            now = datetime.now(timezone.utc)
            docs_result = await db.execute(
                select(Document).where(
                    Document.utilisateur_id == user.id,
                    Document.statut != "valide",
                )
            )
            for d in docs_result.scalars().all():
                d.statut = "valide"
                d.commentaire_admin = None
                d.validated_at = now
        elif role == "mecanicien":
            p_result = await db.execute(
                select(ProfilMecanicien).where(ProfilMecanicien.user_id == user.id)
            )
            profil = p_result.scalar_one_or_none()
            if profil:
                profil.verification_status = "approved"
        await notify_user(
            db,
            user_id=user.id,
            titre="Compte vérifié",
            contenu="Votre dossier d'inscription a été validé. Vous avez maintenant un accès complet à la plateforme.",
            type_notif="document",
            lien=f"/dashboard/{role}",
        )
        send_verification_approved_email(
            to_email=user.email,
            user_name=user.nom_complet or "",
            role=role,
        )
        message = f"Compte de {user.nom_complet} validé avec succès"
    else:
        set_verification_status(user, REJECTED, motif=motif)
        if role in ("chauffeur", "proprietaire"):
            docs_result = await db.execute(
                select(Document).where(
                    Document.utilisateur_id == user.id,
                    Document.statut != "valide",
                )
            )
            for d in docs_result.scalars().all():
                d.statut = "rejete"
                d.commentaire_admin = motif
        elif role == "mecanicien":
            p_result = await db.execute(
                select(ProfilMecanicien).where(ProfilMecanicien.user_id == user.id)
            )
            profil = p_result.scalar_one_or_none()
            if profil:
                profil.verification_status = "rejected"
        await notify_user(
            db,
            user_id=user.id,
            titre="Dossier d'inscription rejeté",
            contenu=f"Votre dossier d'inscription nécessite des corrections. Motif : {motif}",
            type_notif="document",
            lien=f"/dashboard/{role}",
        )
        send_verification_rejection_email(
            to_email=user.email,
            user_name=user.nom_complet or "",
            motif=motif,
            role=role,
        )
        message = f"Compte de {user.nom_complet} rejeté"

    await db.flush()
    return {
        "message": message,
        "verification_status": user.verification_status,
        "is_verified": user.is_verified,
    }


# ─── Gestion des incidents ─────────────────────────

@router.get("/incidents", response_model=list[IncidentOut])
async def list_all_incidents(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    statut: str | None = None,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Liste tous les incidents déclarés.
    Protégé : uniquement les administrateurs.
    """
    from sqlalchemy.orm import selectinload
    query = select(Incident).options(selectinload(Incident.declarant))
    if statut:
        query = query.where(Incident.statut == statut)
    query = query.order_by(Incident.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    incidents = result.scalars().all()
    return [IncidentOut.model_validate(i) for i in incidents]
