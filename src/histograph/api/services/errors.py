from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError


def conflict_from_integrity(error: IntegrityError, detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)
