"""Group + model registry endpoints — plan section 19."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from .. import models, schemas
from ..database import get_db

router = APIRouter(prefix="/groups", tags=["groups"])


@router.post("", response_model=schemas.GroupOut)
def create_group(payload: schemas.GroupCreate, db: Session = Depends(get_db)):
    g = models.Group(name=payload.name, description=payload.description)
    db.add(g)
    db.commit()
    db.refresh(g)
    return g


@router.get("", response_model=list[schemas.GroupOut])
def list_groups(db: Session = Depends(get_db)):
    return db.query(models.Group).order_by(models.Group.id).all()


@router.get("/{group_id}", response_model=schemas.GroupOut)
def get_group(group_id: int, db: Session = Depends(get_db)):
    g = db.get(models.Group, group_id)
    if not g:
        raise HTTPException(404, "Group not found")
    return g


@router.patch("/{group_id}", response_model=schemas.GroupOut)
def update_group(group_id: int, payload: schemas.GroupUpdate, db: Session = Depends(get_db)):
    g = db.get(models.Group, group_id)
    if not g:
        raise HTTPException(404, "Group not found")
    if payload.name is not None:
        g.name = payload.name
    if payload.description is not None:
        g.description = payload.description
    db.commit()
    db.refresh(g)
    return g


@router.delete("/{group_id}")
def delete_group(group_id: int, db: Session = Depends(get_db)):
    g = db.get(models.Group, group_id)
    if not g:
        raise HTTPException(404, "Group not found")
    db.delete(g)
    db.commit()
    return {"deleted": group_id}


@router.post("/{group_id}/models", response_model=schemas.GroupModelOut)
def add_model_to_group(group_id: int, payload: schemas.GroupModelAdd, db: Session = Depends(get_db)):
    if not db.get(models.Group, group_id):
        raise HTTPException(404, "Group not found")
    model = db.get(models.LLMModel, payload.model_id)
    if not model:
        raise HTTPException(404, "Model not found")
    link = models.GroupModel(
        group_id=group_id,
        model_id=payload.model_id,
        turn_order=payload.turn_order,
        is_enabled=payload.is_enabled,
        system_prompt_override=payload.system_prompt_override,
    )
    db.add(link)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(409, f"Model '{model.name}' is already assigned to this group.")
    db.refresh(link)
    return link


@router.put("/{group_id}/models/reorder", response_model=list[schemas.GroupModelOut])
def reorder_group_models(
    group_id: int, payload: schemas.GroupModelsReorderRequest, db: Session = Depends(get_db)
):
    if not db.get(models.Group, group_id):
        raise HTTPException(404, "Group not found")
    links = (
        db.query(models.GroupModel)
        .options(joinedload(models.GroupModel.model))
        .filter(models.GroupModel.group_id == group_id)
        .all()
    )
    by_id = {l.id: l for l in links}
    if set(payload.ordered_link_ids) != set(by_id.keys()):
        raise HTTPException(
            422,
            f"ordered_link_ids must contain exactly the link IDs of this group. "
            f"Expected {sorted(by_id.keys())}, got {payload.ordered_link_ids}.",
        )
    for order, link_id in enumerate(payload.ordered_link_ids):
        by_id[link_id].turn_order = order
    db.commit()
    rows = (
        db.query(models.GroupModel)
        .options(joinedload(models.GroupModel.model))
        .filter(models.GroupModel.group_id == group_id)
        .order_by(models.GroupModel.turn_order, models.GroupModel.id)
        .all()
    )
    return rows


@router.get("/{group_id}/models", response_model=list[schemas.GroupModelOut])
def list_group_models(group_id: int, db: Session = Depends(get_db)):
    rows = (
        db.query(models.GroupModel)
        .options(joinedload(models.GroupModel.model))
        .filter(models.GroupModel.group_id == group_id)
        .order_by(models.GroupModel.turn_order, models.GroupModel.id)
        .all()
    )
    return rows


@router.patch("/{group_id}/models/{link_id}", response_model=schemas.GroupModelOut)
def update_group_model(
    group_id: int, link_id: int, payload: schemas.GroupModelUpdate, db: Session = Depends(get_db)
):
    link = (
        db.query(models.GroupModel)
        .filter(models.GroupModel.id == link_id, models.GroupModel.group_id == group_id)
        .first()
    )
    if not link:
        raise HTTPException(404, "Group model link not found")
    if payload.turn_order is not None:
        link.turn_order = payload.turn_order
    if payload.is_enabled is not None:
        link.is_enabled = payload.is_enabled
    if payload.system_prompt_override is not None:
        link.system_prompt_override = payload.system_prompt_override
    db.commit()
    db.refresh(link)
    return link


@router.delete("/{group_id}/models/{link_id}")
def remove_model_from_group(group_id: int, link_id: int, db: Session = Depends(get_db)):
    link = (
        db.query(models.GroupModel)
        .filter(models.GroupModel.id == link_id, models.GroupModel.group_id == group_id)
        .first()
    )
    if not link:
        raise HTTPException(404, "Group model link not found")
    db.delete(link)
    db.commit()
    return {"deleted": link_id}


model_router = APIRouter(prefix="/models", tags=["models"])


@model_router.post("", response_model=schemas.LLMModelOut)
def create_model(payload: schemas.LLMModelCreate, db: Session = Depends(get_db)):
    m = models.LLMModel(**payload.model_dump())
    db.add(m)
    db.commit()
    db.refresh(m)
    return m


@model_router.get("", response_model=list[schemas.LLMModelOut])
def list_models(db: Session = Depends(get_db)):
    return db.query(models.LLMModel).order_by(models.LLMModel.id).all()


@model_router.get("/{model_id}", response_model=schemas.LLMModelOut)
def get_model(model_id: int, db: Session = Depends(get_db)):
    m = db.get(models.LLMModel, model_id)
    if not m:
        raise HTTPException(404, "Model not found")
    return m


@model_router.patch("/{model_id}", response_model=schemas.LLMModelOut)
def update_model(model_id: int, payload: schemas.LLMModelUpdate, db: Session = Depends(get_db)):
    m = db.get(models.LLMModel, model_id)
    if not m:
        raise HTTPException(404, "Model not found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(m, k, v)
    db.commit()
    db.refresh(m)
    return m


@model_router.delete("/{model_id}")
def delete_model(model_id: int, db: Session = Depends(get_db)):
    m = db.get(models.LLMModel, model_id)
    if not m:
        raise HTTPException(404, "Model not found")
    db.delete(m)
    db.commit()
    return {"deleted": model_id}


@model_router.post("/test-connection", response_model=schemas.TestConnectionOut)
async def test_model_connection(payload: schemas.TestConnectionRequest):
    """Live ping with exact diagnostics (plan §2). Accepts partial/new configs."""
    from ..llm.manager import llm_manager

    config = {
        "provider": payload.provider,
        "model_name": payload.model_name,
        "api_key": payload.api_key or "",
        "base_url": payload.base_url or "",
        "temperature": payload.temperature,
        "max_output_tokens": payload.max_output_tokens,
        "name": payload.model_name,
    }
    result = await llm_manager.verify_connection(config)
    return schemas.TestConnectionOut(**result)
