import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.user import User
from app.models.incident import Incident, IncidentCommentaire
from app.routers.auth import get_current_user, user_role
from app.schemas.incident import (
    IncidentCommentaireCreate,
    IncidentCommentaireOut,
    IncidentCreate,
    IncidentOut,
    IncidentStatistiques,
    IncidentUpdate,
    StatutIncidentUpdate,
)
from app.utils.notifications import notify_all_admins, notify_user

router = APIRouter(prefix="/api/incidents", tags=["Incidents"])


def _localisation_wkt(lat: float, lng: float) -> str:
    return f"POINT({lng} {lat})"


def _incident_out(i: Incident) -> IncidentOut:
    return IncidentOut.model_validate(i)


def _commentaire_out(c: IncidentCommentaire) -> IncidentCommentaireOut:
    return IncidentCommentaireOut(
        id=c.id,
        incident_id=c.incident_id,
        auteur_id=c.auteur_id,
        contenu=c.contenu,
        created_at=c.created_at,
    )


@router.get("/", response_model=list[IncidentOut])
async def list_incidents(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    statut: str | None = None,
    type_incident: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(Incident).options(selectinload(Incident.declarant))
    if user_role(current_user) != "admin":
        query = query.where(Incident.declarant_id == current_user.id)
    if statut:
        query = query.where(Incident.statut == statut)
    if type_incident:
        query = query.where(Incident.type_incident == type_incident)
    query = query.order_by(Incident.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    return [_incident_out(i) for i in result.scalars().all()]


@router.post("/", response_model=IncidentOut, status_code=201)
async def create_incident(
    data: IncidentCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    wkt = _localisation_wkt(data.localisation_lat, data.localisation_lng)
    from datetime import datetime as dt_type
    date_inc = dt_type.fromisoformat(data.date_incident)

    incident = Incident(
        id=uuid.uuid4(),
        declarant_id=current_user.id,
        type_incident=data.type_incident,
        date_incident=date_inc,
        localisation=wkt,
        description=data.description,
        gravite=data.gravite,
        vehicules_impliques=data.vehicules_impliques,
        victimes=data.victimes,
        nombre_victimes=data.nombre_victimes,
        temoin_contact=data.temoin_contact,
    )
    db.add(incident)
    await db.flush()
    await db.refresh(incident)
    incident.declarant = current_user

    type_label = data.type_incident
    gravite_label = data.gravite
    await notify_all_admins(
        db,
        titre="Nouvel incident déclaré",
        contenu=f"Un incident de type « {type_label} » de gravité « {gravite_label } » a été déclaré. Description: {data.description[:100] if data.description else 'N/A'}",
        type_notif="incident",
        lien=f"/admin/dashboard/incidents",
    )

    await notify_user(
        db,
        user_id=current_user.id,
        titre="Incident déclaré avec succès",
        contenu=f"Votre déclaration d'incident de type « {type_label} » a été enregistrée et transmise aux administrateurs.",
        type_notif="incident",
        lien=f"/dashboard/chauffeur/incidents",
    )

    return _incident_out(incident)


@router.get("/statistiques", response_model=IncidentStatistiques)
async def get_statistiques(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Incident))
    incidents = result.scalars().all()

    par_type = {}
    par_gravite = {}
    for i in incidents:
        t = i.type_incident.value if hasattr(i.type_incident, "value") else i.type_incident
        g = i.gravite.value if hasattr(i.gravite, "value") else i.gravite
        par_type[t] = par_type.get(t, 0) + 1
        par_gravite[g] = par_gravite.get(g, 0) + 1

    return IncidentStatistiques(
        total=len(incidents),
        par_type=par_type,
        par_gravite=par_gravite,
        par_mois=[],
    )


@router.get("/proches", response_model=list[IncidentOut])
async def get_incidents_proches(
    lat: float = Query(..., ge=-90, le=90),
    lng: float = Query(..., ge=-180, le=180),
    rayon_km: int = Query(50, gt=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Incident)
        .options(selectinload(Incident.declarant))
        .order_by(Incident.created_at.desc()).limit(50)
    )
    return [_incident_out(i) for i in result.scalars().all()]


@router.put("/{incident_id}/statut")
async def update_incident_statut(
    incident_id: uuid.UUID,
    data: StatutIncidentUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Admin può chiudere o aggiornare lo statuto di un incident."""
    if user_role(current_user) != "admin":
        raise HTTPException(status_code=403, detail="Réservé aux administrateurs")
    result = await db.execute(
        select(Incident)
        .options(selectinload(Incident.declarant))
        .where(Incident.id == incident_id)
    )
    incident = result.scalar_one_or_none()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident non trouvé")
    incident.statut = data.statut
    await db.flush()
    return {"message": "Statut mis à jour", "statut": incident.statut}


@router.get("/{incident_id}", response_model=IncidentOut)
async def get_incident(
    incident_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Incident)
        .options(selectinload(Incident.declarant))
        .where(Incident.id == incident_id)
    )
    incident = result.scalar_one_or_none()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident non trouvé")
    return _incident_out(incident)


@router.put("/{incident_id}", response_model=IncidentOut)
async def update_incident(
    incident_id: uuid.UUID,
    data: IncidentUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Incident)
        .options(selectinload(Incident.declarant))
        .where(Incident.id == incident_id)
    )
    incident = result.scalar_one_or_none()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident non trouvé")
    if incident.declarant_id != current_user.id and user_role(current_user) != "admin":
        raise HTTPException(status_code=403, detail="Accès refusé")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(incident, field, value)
    await db.flush()
    await db.refresh(incident)
    return _incident_out(incident)


@router.post(
    "/{incident_id}/commentaire",
    response_model=IncidentCommentaireOut,
    status_code=201,
)
async def add_commentaire(
    incident_id: uuid.UUID,
    data: IncidentCommentaireCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Incident).where(Incident.id == incident_id))
    incident = result.scalar_one_or_none()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident non trouvé")

    commentaire = IncidentCommentaire(
        id=uuid.uuid4(),
        incident_id=incident_id,
        auteur_id=current_user.id,
        contenu=data.contenu,
    )
    db.add(commentaire)
    await db.flush()
    await db.refresh(commentaire)
    return _commentaire_out(commentaire)


@router.get("/{incident_id}/commentaires", response_model=list[IncidentCommentaireOut])
async def list_commentaires(
    incident_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(IncidentCommentaire)
        .where(IncidentCommentaire.incident_id == incident_id)
        .order_by(IncidentCommentaire.created_at.asc())
    )
    return [_commentaire_out(c) for c in result.scalars().all()]
