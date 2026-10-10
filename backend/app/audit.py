from .models import OperationLog


def log_event(db, user_id, action: str, params: dict | None = None) -> None:
    db.add(OperationLog(user_id=user_id, action=action, params=params or {}))
