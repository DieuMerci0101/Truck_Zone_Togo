"""
Utilitaires partagés pour le workflow de vérification des comptes.

Statuts possibles (User.verification_status et ProfilMecanicien.verification_status) :
  - pending_upload   : l'utilisateur n'a pas encore soumis tous ses documents
  - pending_approval : tous les documents requis ont été soumis, en attente d'examen admin
  - approved         : dossier validé par l'administrateur, accès complet
  - rejected         : dossier rejeté, un motif a été enregistré
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.models.enums import TypeDocument
from app.models.mecanicien import ProfilMecanicien
from app.models.user import User

PENDING_UPLOAD = "pending_upload"
PENDING_APPROVAL = "pending_approval"
APPROVED = "approved"
REJECTED = "rejected"

VALID_STATUSES = {PENDING_UPLOAD, PENDING_APPROVAL, APPROVED, REJECTED}

# Documents obligatoires par rôle pour considérer le dossier "complet".
# Un groupe = liste de types équivalents : il suffit que l'UN d'entre eux soit
# soumis (ex: pièce d'identité = "cni" OU "passeport").
#   - chauffeur     : permis → pièce d'identité → casier judiciaire → photo d'identité
#   - proprietaire  : preuve d'entreprise (RCCM/patente) → pièce d'identité
#   - mecanicien    : justificatif unique (diplôme / attestation / certificat)
REQUIRED_DOCS_BY_ROLE: dict[str, list[list[str]]] = {
    "chauffeur": [["permis"], ["cni", "passeport"], ["casier"], ["photo_identite"]],
    "proprietaire": [["rccm", "patente"], ["cni", "passeport"]],
    "mecanicien": [["justificatif"]],
}


def _type_doc_value(td) -> str:
    return td.value if hasattr(td, "value") else td


async def submitted_doc_types(db: AsyncSession, user_id: str) -> set[str]:
    """Types de documents déjà soumis par un utilisateur (chauffeur / proprietaire)."""
    result = await db.execute(
        select(Document.type_document).where(Document.utilisateur_id == user_id)
    )
    return {_type_doc_value(td) for td in result.scalars().all()}


async def all_required_docs_submitted(db: AsyncSession, user: User) -> bool:
    """
    Vrai si l'utilisateur a soumis la totalité de ses documents requis.
    - Chauffeur / propriétaire : chaque type requis possède au moins une ligne Document.
    - Mécanicien : un justificatif a été uploadé sur son profil.
    """
    required = REQUIRED_DOCS_BY_ROLE.get(user.role.value)
    if not required:
        return False
    if user.role.value == "mecanicien":
        result = await db.execute(
            select(ProfilMecanicien).where(ProfilMecanicien.user_id == user.id)
        )
        profil = result.scalar_one_or_none()
        return bool(profil and profil.proof_document_url)
    submitted = await submitted_doc_types(db, user.id)
    for group in required:
        group_types = group if isinstance(group, (list, tuple, set)) else [group]
        if not any(t in submitted for t in group_types):
            return False
    return True


def set_verification_status(
    user: User,
    status: str,
    motif: str | None = None,
    is_verified: bool | None = None,
) -> None:
    """Met à jour le statut de vérification global de l'utilisateur."""
    if status not in VALID_STATUSES:
        raise ValueError(f"Statut de vérification invalide : {status}")
    user.verification_status = status
    if status == REJECTED:
        user.verification_reject_motif = motif
        if is_verified is None:
            user.is_verified = False
    elif status == APPROVED:
        user.verification_reject_motif = None
        if is_verified is None:
            user.is_verified = True
    elif status == PENDING_APPROVAL:
        user.verification_reject_motif = None
    if is_verified is not None:
        user.is_verified = is_verified


async def sync_verification_after_upload(db: AsyncSession, user: User) -> None:
    """
    Après un upload de document, passe automatiquement le compte en `pending_approval`
    dès que la totalité des documents requis a été soumise.
    """
    if await all_required_docs_submitted(db, user):
        set_verification_status(user, PENDING_APPROVAL)
