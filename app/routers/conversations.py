import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.user import User
from app.models.conversation import Conversation, ConversationParticipant
from app.models.message import Message
from app.routers.auth import get_current_user
from app.schemas.conversation import (
    ConversationCreate,
    ConversationOut,
    MessageCreate,
    MessageOut,
)

router = APIRouter(prefix="/api/conversations", tags=["Messagerie"])


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
        out.append(ConversationOut(
            id=conv.id,
            type=conv.type.value if hasattr(conv.type, "value") else conv.type,
            created_at=conv.created_at,
            updated_at=conv.updated_at,
            last_message=last_msg.contenu if last_msg else None,
            last_message_at=last_msg.created_at if last_msg else None,
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
        if other_parts.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Conversation déjà existante")

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
    await db.refresh(conv)

    return ConversationOut(
        id=conv.id,
        type=conv.type.value if hasattr(conv.type, "value") else conv.type,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
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
    return ConversationOut(
        id=conv.id,
        type=conv.type.value if hasattr(conv.type, "value") else conv.type,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
        last_message=last_msg.contenu if last_msg else None,
        last_message_at=last_msg.created_at if last_msg else None,
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
        .order_by(Message.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    messages = result.scalars().all()
    return [
        MessageOut(
            id=m.id,
            conversation_id=m.conversation_id,
            expediteur_id=m.expediteur_id,
            contenu=m.contenu,
            type=m.type.value if hasattr(m.type, "value") else m.type,
            lu=m.lu,
            created_at=m.created_at,
        )
        for m in reversed(messages)
    ]


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
    return MessageOut(
        id=msg.id,
        conversation_id=msg.conversation_id,
        expediteur_id=msg.expediteur_id,
        contenu=msg.contenu,
        type=msg.type.value if hasattr(msg.type, "value") else msg.type,
        lu=msg.lu,
        created_at=msg.created_at,
    )
