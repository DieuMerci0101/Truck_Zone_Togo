import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.user import User
from app.models.conversation import Conversation, ConversationParticipant
from app.models.message import Message
from app.routers.auth import get_current_user
from app.services.storage import save_upload
from app.schemas.conversation import (
    ConversationCreate,
    ConversationOut,
    InitiateFromOffer,
    MessageCreate,
    MessageOut,
)

router = APIRouter(prefix="/api/conversations", tags=["Messagerie"])

# Alias pour l'initiation d'une conversation depuis l'annuaire (ex: propriétaire → chauffeur).
chat_router = APIRouter(prefix="/api/chat", tags=["Chat (initiation)"])


async def _existing_conversation_id(
    user_a_id: uuid.UUID,
    user_b_id: uuid.UUID,
    db: AsyncSession,
) -> uuid.UUID | None:
    """Renvoie l'ID de la conversation directe existante entre deux utilisateurs, sinon None."""
    my_parts = await db.execute(
        select(ConversationParticipant).where(
            ConversationParticipant.user_id == user_a_id
        )
    )
    my_conv_ids = [p.conversation_id for p in my_parts.scalars().all()]
    if not my_conv_ids:
        return None
    other_part = await db.execute(
        select(ConversationParticipant).where(
            ConversationParticipant.conversation_id.in_(my_conv_ids),
            ConversationParticipant.user_id == user_b_id,
        )
    )
    existing = other_part.scalar_one_or_none()
    return existing.conversation_id if existing else None


async def get_or_create_direct_conversation(
    db: AsyncSession,
    user_a_id: uuid.UUID,
    user_b_id: uuid.UUID,
) -> Conversation:
    """
    Retourne la conversation directe existante entre `user_a_id` et
    `user_b_id`, ou la crée (sans message) si aucune n'existe. Idempotent :
    utilisé par l'ouverture automatique des conversations (candidatures,
    demande d'assistance, clic « Contacter »).
    """
    if str(user_a_id) == str(user_b_id):
        raise HTTPException(status_code=400, detail="Impossible de se contacter soi-même")

    existing_id = await _existing_conversation_id(user_a_id, user_b_id, db)
    if existing_id:
        result = await db.execute(
            select(Conversation).where(Conversation.id == existing_id)
        )
        return result.scalar_one()

    conv = Conversation(id=uuid.uuid4(), type="directe")
    db.add(conv)
    await db.flush()
    db.add(ConversationParticipant(conversation_id=conv.id, user_id=user_a_id))
    db.add(ConversationParticipant(conversation_id=conv.id, user_id=user_b_id))
    await db.flush()
    return conv


async def _build_conversation_out(
    conv: Conversation,
    db: AsyncSession,
    last_message: str | None,
    last_message_at: datetime | None,
) -> ConversationOut:
    participants = await _fetch_participants(conv.id, db)
    return ConversationOut(
        id=conv.id,
        type=conv.type.value if hasattr(conv.type, "value") else conv.type,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
        last_message=last_message,
        last_message_at=last_message_at,
        participants=participants,
    )


@chat_router.post("/initiate", response_model=ConversationOut, status_code=201)
async def initiate_conversation(
    data: ConversationCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Démarre une conversation avec un utilisateur :
     1) Vérifie si une conversation existe déjà entre current_user et le participant cible.
     2) Si aucune n'existe : crée la conversation et enregistre le premier message.
     3) Si elle existe déjà : ajoute le nouveau message dans la discussion existante.
    Retourne toujours la conversation (existante ou nouvelle).
    """
    return await create_conversation(data, current_user, db)


@chat_router.post("/initiate-from-offer", response_model=ConversationOut, status_code=201)
async def initiate_from_offer(
    data: InitiateFromOffer,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Démarre (ou réutilise) la conversation privée entre le chauffeur connecté
    et le propriétaire qui a publié un camion ou une offre.
    Paramètres : camion_id OU offre_id + le message rédigé par le chauffeur.
    """
    from app.models.camion import Camion
    from app.models.offre import OffreRecrutement
    from app.models.proprietaire import ProfilProprietaire

    if not data.camion_id and not data.offre_id:
        raise HTTPException(
            status_code=400,
            detail="camion_id ou offre_id est requis",
        )

    now = datetime.now(timezone.utc)
    profil_proprietaire_id = None
    reference = "annonce"

    if data.offre_id:
        result = await db.execute(
            select(OffreRecrutement).where(OffreRecrutement.id == data.offre_id)
        )
        offre = result.scalar_one_or_none()
        if not offre:
            raise HTTPException(status_code=404, detail="Offre non trouvée")
        expires = offre.expires_at
        if expires is not None:
            expires_aware = expires.replace(tzinfo=timezone.utc) if expires.tzinfo is None else expires
            if expires_aware <= now:
                raise HTTPException(status_code=400, detail="Cette offre a expiré")
        profil_proprietaire_id = offre.proprietaire_id
        reference = f"l'offre « {offre.titre} »"

    elif data.camion_id:
        result = await db.execute(
            select(Camion).where(Camion.id == data.camion_id)
        )
        camion = result.scalar_one_or_none()
        if not camion:
            raise HTTPException(status_code=404, detail="Camion non trouvé")
        if not camion.is_public:
            raise HTTPException(status_code=400, detail="Ce camion n'est pas public")
        expires = camion.expires_at
        if expires is None or expires <= now:
            raise HTTPException(status_code=400, detail="Cette annonce a expiré")
        if not camion.proprietaire_id:
            raise HTTPException(status_code=400, detail="Aucun propriétaire associé à ce camion")
        profil_proprietaire_id = camion.proprietaire_id
        reference = f"le camion {camion.immatriculation}"

    profil_result = await db.execute(
        select(ProfilProprietaire).where(ProfilProprietaire.id == profil_proprietaire_id)
    )
    profil = profil_result.scalar_one_or_none()
    if not profil:
        raise HTTPException(status_code=404, detail="Propriétaire introuvable")

    owner_user_id = profil.user_id
    if str(owner_user_id) == str(current_user.id):
        raise HTTPException(status_code=400, detail="Impossible de se contacter soi-même")

    # Vérifier si une conversation existe déjà entre le chauffeur et le propriétaire.
    existing_conv_id = await _existing_conversation_id(
        current_user.id, owner_user_id, db
    )

    if existing_conv_id:
        conv_result = await db.execute(
            select(Conversation).where(Conversation.id == existing_conv_id)
        )
        conv = conv_result.scalar_one()
        msg = Message(
            id=uuid.uuid4(),
            conversation_id=conv.id,
            expediteur_id=current_user.id,
            contenu=data.message,
            type="texte",
        )
        db.add(msg)
        conv.updated_at = now
        await _notifier_autres_participants(
            conv.id,
            current_user.id,
            current_user.nom_complet,
            data.message,
            db,
        )
        await db.commit()
        await db.refresh(conv)
        return await _build_conversation_out(conv, db, data.message, now)

    # Aucune conversation existante → création + premier message.
    conv = Conversation(type="directe")
    db.add(conv)
    await db.flush()

    db.add(ConversationParticipant(conversation_id=conv.id, user_id=current_user.id))
    await db.flush()
    db.add(ConversationParticipant(conversation_id=conv.id, user_id=owner_user_id))
    await db.flush()

    msg = Message(
        id=uuid.uuid4(),
        conversation_id=conv.id,
        expediteur_id=current_user.id,
        contenu=data.message,
        type="texte",
    )
    db.add(msg)
    conv.updated_at = now

    await _notifier_autres_participants(
        conv.id,
        current_user.id,
        current_user.nom_complet,
        data.message,
        db,
    )

    # Notifier le propriétaire qu'un chauffeur l'a contacté à propos de l'annonce.
    from app.utils.notifications import notify_user

    await notify_user(
        db,
        user_id=owner_user_id,
        titre="Nouvelle demande de contact",
        contenu=f"{current_user.nom_complet} vous a contacté à propos de {reference}.",
        type_notif="message",
        lien=f"/dashboard/chat?conv={conv.id}",
        metadata={"conversation_id": str(conv.id)},
        email=True,
        push=True,
    )

    await db.commit()
    await db.refresh(conv)

    return await _build_conversation_out(conv, db, data.message, now)


async def _get_conversation_with_access(
    conversation_id: uuid.UUID,
    current_user: User,
    db: AsyncSession,
) -> Conversation:
    result = await db.execute(
        select(Conversation).where(Conversation.id == conversation_id)
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation non trouvée")

    part_result = await db.execute(
        select(ConversationParticipant).where(
            ConversationParticipant.conversation_id == conversation_id,
            ConversationParticipant.user_id == current_user.id,
        )
    )
    if not part_result.scalar_one_or_none():
        raise HTTPException(status_code=403, detail="Accès refusé")
    return conv


async def _fetch_participants(
    conversation_id: uuid.UUID,
    db: AsyncSession,
) -> list["ParticipantOut"]:
    from app.schemas.conversation import ParticipantOut
    from app.models.chauffeur import ProfilChauffeur
    from app.models.mecanicien import ProfilMecanicien

    result = await db.execute(
        select(ConversationParticipant)
        .where(ConversationParticipant.conversation_id == conversation_id)
        .options(selectinload(ConversationParticipant.user))
    )
    parts = result.scalars().all()
    out = []
    for p in parts:
        u = p.user
        if u is None:
            continue
        role = u.role.value if hasattr(u.role, "value") else u.role
        presence = None
        if role == "chauffeur":
            chauffeur_result = await db.execute(
                select(ProfilChauffeur).where(ProfilChauffeur.user_id == u.id)
            )
            chauffeur = chauffeur_result.scalar_one_or_none()
            if chauffeur and chauffeur.disponibilite is not None:
                presence = chauffeur.disponibilite.value if hasattr(chauffeur.disponibilite, "value") else chauffeur.disponibilite
        elif role == "mecanicien":
            mecanicien_result = await db.execute(
                select(ProfilMecanicien).where(ProfilMecanicien.user_id == u.id)
            )
            mecanicien = mecanicien_result.scalar_one_or_none()
            if mecanicien and mecanicien.position_active:
                presence = "en_ligne"
            else:
                presence = "hors_ligne"
        out.append(ParticipantOut(
            id=u.id,
            nom_complet=u.nom_complet,
            email=u.email,
            telephone=u.telephone,
            role=role,
            photo_profil=u.photo_profil,
            presence=presence,
        ))
    return out


async def _notifier_autres_participants(
    conversation_id: uuid.UUID,
    expediteur_id: uuid.UUID,
    expediteur_nom: str,
    contenu: str,
    db: AsyncSession,
    audio: bool = False,
    extrait: str | None = None,
) -> None:
    """Crée une notification pour chaque autre participant de la conversation."""
    from app.utils.notifications import notify_user

    result = await db.execute(
        select(ConversationParticipant).where(
            ConversationParticipant.conversation_id == conversation_id,
            ConversationParticipant.user_id != expediteur_id,
        )
    )
    destinataires = [p.user_id for p in result.scalars().all()]
    if not destinataires:
        return
    preview = contenu.strip()[:100] if contenu and contenu.strip() else None
    extrait_final = (
        preview
        or extrait
        or ("Message vocal" if audio else "Nouveau message")
    )
    for uid in destinataires:
        await notify_user(
            db,
            user_id=uid,
            titre="Nouveau message",
            contenu=f"{expediteur_nom} : {extrait_final}",
            type_notif="message",
            lien=f"/dashboard/chat?conv={conversation_id}",
            metadata={"conversation_id": str(conversation_id), "audio": audio},
            email=True,
            push=True,
        )


def _message_preview(msg: Message | None) -> str | None:
    """Aperçu du dernier message : le texte, ou un libellé pour les médias."""
    if msg is None:
        return None
    if msg.contenu and msg.contenu.strip():
        return msg.contenu
    return {
        "audio": "🎤 Message vocal",
        "image": "📷 Photo",
        "video": "🎬 Vidéo",
        "fichier": "📎 Document",
    }.get(msg.type, "Nouveau message")


@router.get("/", response_model=list[ConversationOut])
async def list_conversations(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    part_result = await db.execute(
        select(ConversationParticipant).where(
            ConversationParticipant.user_id == current_user.id
        )
    )
    participant_ids = [p.conversation_id for p in part_result.scalars().all()]

    if not participant_ids:
        return []

    conv_result = await db.execute(
        select(Conversation).where(Conversation.id.in_(participant_ids))
        .order_by(Conversation.updated_at.desc())
        .offset(skip)
        .limit(limit)
    )
    conversations = conv_result.scalars().all()

    out = []
    for conv in conversations:
        last_msg_result = await db.execute(
            select(Message)
            .where(Message.conversation_id == conv.id)
            .order_by(Message.created_at.desc())
            .limit(1)
        )
        last_msg = last_msg_result.scalar_one_or_none()
        participants = await _fetch_participants(conv.id, db)
        out.append(ConversationOut(
            id=conv.id,
            type=conv.type.value if hasattr(conv.type, "value") else conv.type,
            created_at=conv.created_at,
            updated_at=conv.updated_at,
            last_message=_message_preview(last_msg),
            last_message_at=last_msg.created_at if last_msg else None,
            participants=participants,
        ))
    return out


@router.post("/", response_model=ConversationOut, status_code=201)
async def create_conversation(
    data: ConversationCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    target_result = await db.execute(
        select(User).where(User.id == data.participant_id)
    )
    target = target_result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")
    if target.id == current_user.id:
        raise HTTPException(status_code=400, detail="Impossible de créer une conversation avec soi-même")

    existing_parts = await db.execute(
        select(ConversationParticipant).where(
            ConversationParticipant.user_id == current_user.id
        )
    )
    my_conv_ids = [p.conversation_id for p in existing_parts.scalars().all()]

    if my_conv_ids:
        other_parts = await db.execute(
            select(ConversationParticipant).where(
                ConversationParticipant.conversation_id.in_(my_conv_ids),
                ConversationParticipant.user_id == data.participant_id,
            )
        )
        existing = other_parts.scalar_one_or_none()
        if existing:
            # If premier_message is provided, send it in the existing conversation
            if data.premier_message:
                msg = Message(
                    id=uuid.uuid4(),
                    conversation_id=existing.conversation_id,
                    expediteur_id=current_user.id,
                    contenu=data.premier_message,
                    type="texte",
                )
                db.add(msg)
                now = datetime.now(timezone.utc)
                conv_update = await db.execute(
                    select(Conversation).where(Conversation.id == existing.conversation_id)
                )
                existing_conv = conv_update.scalar_one()
                existing_conv.updated_at = now
                await _notifier_autres_participants(
                    existing_conv.id,
                    current_user.id,
                    current_user.nom_complet,
                    data.premier_message,
                    db,
                )
                await db.commit()
                await db.refresh(existing_conv)
                participants = await _fetch_participants(existing_conv.id, db)
                return ConversationOut(
                    id=existing_conv.id,
                    type=existing_conv.type.value if hasattr(existing_conv.type, "value") else existing_conv.type,
                    created_at=existing_conv.created_at,
                    updated_at=existing_conv.updated_at,
                    last_message=data.premier_message,
                    last_message_at=now,
                    participants=participants,
                )
            raise HTTPException(
                status_code=409,
                detail=f"Conversation déjà existante: {existing.conversation_id}",
            )

    conv = Conversation(
        id=uuid.uuid4(),
        type="directe",
    )
    db.add(conv)
    await db.flush()

    p1 = ConversationParticipant(conversation_id=conv.id, user_id=current_user.id)
    db.add(p1)
    await db.flush()
    p2 = ConversationParticipant(conversation_id=conv.id, user_id=data.participant_id)
    db.add(p2)
    await db.flush()

    # Send first message if provided
    if data.premier_message:
        msg = Message(
            id=uuid.uuid4(),
            conversation_id=conv.id,
            expediteur_id=current_user.id,
            contenu=data.premier_message,
            type="texte",
        )
        db.add(msg)
        conv.updated_at = datetime.now(timezone.utc)
        await _notifier_autres_participants(
            conv.id,
            current_user.id,
            current_user.nom_complet,
            data.premier_message,
            db,
        )

    await db.commit()
    await db.refresh(conv)

    participants = await _fetch_participants(conv.id, db)

    return ConversationOut(
        id=conv.id,
        type=conv.type.value if hasattr(conv.type, "value") else conv.type,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
        last_message=data.premier_message,
        last_message_at=conv.updated_at if data.premier_message else None,
        participants=participants,
    )


@router.get("/{conversation_id}", response_model=ConversationOut)
async def get_conversation(
    conversation_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    conv = await _get_conversation_with_access(conversation_id, current_user, db)
    last_msg_result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conv.id)
        .order_by(Message.created_at.desc())
        .limit(1)
    )
    last_msg = last_msg_result.scalar_one_or_none()
    participants = await _fetch_participants(conv.id, db)
    return ConversationOut(
        id=conv.id,
        type=conv.type.value if hasattr(conv.type, "value") else conv.type,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
        last_message=_message_preview(last_msg),
        last_message_at=last_msg.created_at if last_msg else None,
        participants=participants,
    )


def _enrich_message(msg: Message) -> MessageOut:
    """Build a MessageOut with sender info populated from the message relationship."""
    sender = msg.expediteur
    type_val = msg.type.value if hasattr(msg.type, "value") else msg.type
    return MessageOut(
        id=msg.id,
        conversation_id=msg.conversation_id,
        expediteur_id=msg.expediteur_id,
        contenu=msg.contenu,
        type=type_val,
        media_url=msg.media_url,
        lu=msg.lu,
        created_at=msg.created_at,
        expediteur_nom=sender.nom_complet if sender else None,
        expediteur_avatar=sender.photo_profil if sender else None,
        expediteur_role=sender.role.value if sender and hasattr(sender.role, "value") else (sender.role if sender else None),
    )


@router.get("/{conversation_id}/messages", response_model=list[MessageOut])
async def list_messages(
    conversation_id: uuid.UUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_conversation_with_access(conversation_id, current_user, db)
    result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .options(selectinload(Message.expediteur))
        .order_by(Message.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    messages = result.scalars().all()
    return [_enrich_message(m) for m in reversed(messages)]


@router.post("/{conversation_id}/messages", response_model=MessageOut, status_code=201)
async def send_message(
    conversation_id: uuid.UUID,
    data: MessageCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_conversation_with_access(conversation_id, current_user, db)

    msg = Message(
        id=uuid.uuid4(),
        conversation_id=conversation_id,
        expediteur_id=current_user.id,
        contenu=data.contenu,
        type=data.type,
    )
    db.add(msg)

    conv_result = await db.execute(
        select(Conversation).where(Conversation.id == conversation_id)
    )
    conv = conv_result.scalar_one()
    conv.updated_at = datetime.now(timezone.utc)

    await db.flush()
    await db.refresh(msg)
    await _notifier_autres_participants(
        conversation_id,
        current_user.id,
        current_user.nom_complet,
        data.contenu,
        db,
    )
    # Re-fetch with expediteur relation loaded
    result = await db.execute(
        select(Message).where(Message.id == msg.id).options(selectinload(Message.expediteur))
    )
    msg_with_sender = result.scalar_one()
    return _enrich_message(msg_with_sender)


AUDIO_ALLOWED = {"audio/webm", "audio/mp3", "audio/mpeg", "audio/ogg", "audio/wav"}

# Limite de taille des pièces jointes (25 Mo) — au-delà, refus clair.
MAX_MEDIA_BYTES = 25 * 1024 * 1024

IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp", "image/heic"}
VIDEO_TYPES = {"video/mp4", "video/webm", "video/quicktime", "video/x-m4v"}
# Documents (fiches techniques, devis, PV, contrats…).
DOCUMENT_TYPES = {
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "text/plain",
    "text/csv",
}
DOCUMENT_LABELS = {
    "application/pdf": "PDF",
    "application/msword": "Word",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "Word",
    "application/vnd.ms-excel": "Excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "Excel",
    "application/vnd.ms-powerpoint": "PowerPoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": "PowerPoint",
    "text/plain": "Texte",
    "text/csv": "CSV",
}


@router.post("/{conversation_id}/messages/media", response_model=MessageOut, status_code=201)
async def send_media_message(
    conversation_id: uuid.UUID,
    file: UploadFile = File(...),
    contenu: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Envoie une pièce jointe (photo, vidéo ou document) dans une conversation.

    Le type du message (`image`, `video` ou `fichier`) est déduit du
    Content-Type du fichier. Le fichier est stocké de façon permanente sur le
    Cloud Storage (Supabase) — ou sur le disque local en repli.
    """
    await _get_conversation_with_access(conversation_id, current_user, db)

    content_type = (file.content_type or "").lower()
    if content_type.startswith("audio/"):
        if content_type not in AUDIO_ALLOWED:
            raise HTTPException(
                status_code=400,
                detail=f"Format audio non supporté: {file.content_type}",
            )
        message_type, category, extrait = "audio", "audios", "Message vocal"
    elif content_type in IMAGE_TYPES:
        message_type, category, extrait = "image", "photos", "📷 Photo"
    elif content_type in VIDEO_TYPES:
        message_type, category, extrait = "video", "videos", "🎬 Vidéo"
    elif content_type in DOCUMENT_TYPES:
        message_type, category, extrait = "fichier", "documents", "📎 Document"
    else:
        raise HTTPException(
            status_code=400,
            detail=(
                "Type de fichier non supporté. Formats acceptés : images "
                "(jpg, png, webp), vidéos (mp4, webm, mov), documents "
                "(pdf, doc, xls, txt) et audio."
            ),
        )

    content = await file.read()
    if len(content) > MAX_MEDIA_BYTES:
        raise HTTPException(
            status_code=413,
            detail="Fichier trop volumineux (maximum 25 Mo)",
        )
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Fichier vide")

    ext = file.filename.split(".")[-1] if file.filename and "." in file.filename else ""
    media_url = save_upload(content, category, ext)

    msg = Message(
        id=uuid.uuid4(),
        conversation_id=conversation_id,
        expediteur_id=current_user.id,
        contenu=contenu or "",
        type=message_type,
        media_url=media_url,
    )
    db.add(msg)

    conv_result = await db.execute(
        select(Conversation).where(Conversation.id == conversation_id)
    )
    conv = conv_result.scalar_one()
    conv.updated_at = datetime.now(timezone.utc)

    await db.flush()
    await db.refresh(msg)
    await _notifier_autres_participants(
        conversation_id,
        current_user.id,
        current_user.nom_complet,
        contenu or "",
        db,
        audio=(message_type == "audio"),
        extrait=extrait,
    )
    result = await db.execute(
        select(Message).where(Message.id == msg.id).options(selectinload(Message.expediteur))
    )
    msg_with_sender = result.scalar_one()
    return _enrich_message(msg_with_sender)


@router.post("/{conversation_id}/messages/audio", response_model=MessageOut, status_code=201)
async def send_audio_message(
    conversation_id: uuid.UUID,
    file: UploadFile = File(...),
    contenu: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_conversation_with_access(conversation_id, current_user, db)

    if file.content_type not in AUDIO_ALLOWED:
        raise HTTPException(
            status_code=400,
            detail=f"Format audio non supporté: {file.content_type}. Formats acceptés: webm, mp3, ogg, wav",
        )

    ext = file.filename.split(".")[-1] if file.filename and "." in file.filename else "webm"
    content = await file.read()
    media_url = save_upload(content, "audios", ext)

    msg = Message(
        id=uuid.uuid4(),
        conversation_id=conversation_id,
        expediteur_id=current_user.id,
        contenu=contenu or "",
        type="audio",
        media_url=media_url,
    )
    db.add(msg)

    conv_result = await db.execute(
        select(Conversation).where(Conversation.id == conversation_id)
    )
    conv = conv_result.scalar_one()
    conv.updated_at = datetime.now(timezone.utc)

    await db.flush()
    await db.refresh(msg)
    await _notifier_autres_participants(
        conversation_id,
        current_user.id,
        current_user.nom_complet,
        contenu or "",
        db,
        audio=True,
    )
    result = await db.execute(
        select(Message).where(Message.id == msg.id).options(selectinload(Message.expediteur))
    )
    msg_with_sender = result.scalar_one()
    return _enrich_message(msg_with_sender)


@router.put("/{conversation_id}/lire")
async def mark_conversation_read(
    conversation_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_conversation_with_access(conversation_id, current_user, db)

    result = await db.execute(
        select(Message).where(
            Message.conversation_id == conversation_id,
            Message.expediteur_id != current_user.id,
            Message.lu == False,
        )
    )
    messages = result.scalars().all()
    for m in messages:
        m.lu = True

    # Marque les notifications "message" liées à cette conversation comme lues
    from sqlalchemy import update as sa_update
    from app.models.notification import Notification
    await db.execute(
        sa_update(Notification)
        .where(
            Notification.destinataire_id == current_user.id,
            Notification.type == "message",
            Notification.lu == False,
            Notification.lien.contains(str(conversation_id)),
        )
        .values(lu=True)
    )
    await db.flush()
    return {
        "message": "Messages marqués comme lus",
        "marked": len(messages),
    }
