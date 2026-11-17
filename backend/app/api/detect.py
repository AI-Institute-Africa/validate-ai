"""Authenticity detectors: what is installed, in which mode, and whether it loaded."""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.security import Principal, Role, require
from app.detect import registry

router = APIRouter(tags=["authenticity detectors"])
Admin = Annotated[Principal, Depends(require(Role.ADMIN))]


@router.get("/admin/detectors")
def detector_status(p: Admin) -> dict:
    """Mode, manifest state, and each detector's model version, hash and load state.

    Reading this loads no images and changes nothing. A detector that cannot run shows why
    (`no_model`, `hash_mismatch`, `onnxruntime_missing`...); the existing rules then run unchanged.
    """
    return registry.describe()
