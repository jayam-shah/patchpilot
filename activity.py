from database import ActivityLog, get_session
from logger import get_logger

logger = get_logger(__name__)


def log_event(
    event_type: str,
    message: str,
    api_name: str | None = None,
    repo_id: int | None = None,
) -> None:
    session = get_session()
    try:
        event = ActivityLog(
            event_type=event_type,
            message=message,
            api_name=api_name,
            repo_id=repo_id,
        )
        session.add(event)
        session.commit()
        logger.debug(f"Activity logged: {event_type} — {message}")
    except Exception as e:  # noqa: BLE001
        logger.error(f"Failed to log activity: {e}")
    finally:
        session.close()
