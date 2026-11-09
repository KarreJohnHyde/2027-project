"""Authenticated private reference reports; shared workspace rules never apply."""
from fastapi import APIRouter, Depends, Response
from app.models.entities import User
from app.services.auth import get_current_user
from app.services import private_references as store

router = APIRouter(prefix="/private-references", tags=["Private reference cases"])
HEADERS = {"Cache-Control": "no-store, private", "Pragma": "no-cache", "Vary": "Authorization", "X-Content-Type-Options": "nosniff"}


@router.get("")
def list_references(response: Response, current_user: User = Depends(get_current_user)):
    response.headers.update(HEADERS)
    return store.listing(current_user)


@router.get("/{study_id}")
def get_reference(study_id: str, response: Response, current_user: User = Depends(get_current_user)):
    response.headers.update(HEADERS)
    return store.public_report(store.load(current_user, study_id))


@router.get("/{study_id}/assets/{asset_id}")
def get_source(study_id: str, asset_id: str, current_user: User = Depends(get_current_user)):
    content, mime = store.asset(current_user, study_id, asset_id)
    return Response(content, media_type=mime, headers=HEADERS)


@router.delete("/{study_id}", status_code=204)
def delete_reference(study_id: str, current_user: User = Depends(get_current_user)):
    store.erase(current_user, study_id)
    return Response(status_code=204, headers=HEADERS)
