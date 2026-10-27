from database import ChangelogSnapshot, ChangelogTag, get_session
from feature_catalog import FEATURE_CATALOG
from logger import get_logger

logger = get_logger(__name__)

CHANGE_TYPE_KEYWORDS = {
    "breaking": [
        "breaking change",
        "breaking:",
        "deprecated and removed",
        "no longer supported",
        "must now",
        "required",
        "migration required",
        "incompatible",
        "renamed",
        "replaced by",
        "has been removed",
    ],
    "deprecation": [
        "deprecated",
        "will be removed",
        "legacy",
        "sunset",
        "end of life",
        "eol",
        "please migrate",
    ],
    "new_feature": [
        "new:",
        "introducing",
        "added",
        "now supports",
        "we're launching",
        "announcing",
        "available now",
        "new endpoint",
        "new parameter",
    ],
}


def detect_change_type(text: str) -> tuple[str, str]:
    text_lower = text.lower()
    for change_type in ["deprecation", "breaking", "new_feature"]:
        keywords = CHANGE_TYPE_KEYWORDS[change_type]
        for kw in keywords:
            if kw in text_lower:
                return change_type, "high"
    return "other", "low"


def detect_features(text: str, service: str) -> list[str]:
    features = FEATURE_CATALOG.get(service, {})
    matched = []
    text_lower = text.lower()
    for feature, patterns in features.items():
        for pattern in patterns:
            if pattern.lower() in text_lower:
                matched.append(feature)
                break
    return list(set(matched))


def tag_snapshot(snapshot_id: int, service: str) -> ChangelogTag | None:
    session = get_session()
    try:
        snapshot = session.query(ChangelogSnapshot).filter_by(id=snapshot_id).first()
        if not snapshot:
            logger.warning(f"Snapshot {snapshot_id} not found")
            return None

        existing = (
            session.query(ChangelogTag)
            .filter_by(snapshot_id=snapshot_id, service=service)
            .first()
        )
        if existing:
            logger.debug(f"Snapshot {snapshot_id} already tagged for {service}")
            return existing

        text = snapshot.raw_content or ""
        change_type, confidence = detect_change_type(text)
        features = detect_features(text, service)

        if not features:
            confidence = "low"

        tag = ChangelogTag(
            snapshot_id=snapshot_id,
            service=service,
            features=features,
            change_type=change_type,
            tag_confidence=confidence,
        )
        session.add(tag)
        session.commit()
        session.refresh(tag)

        logger.info(
            f"Tagged snapshot {snapshot_id} [{service}]: "
            f"type={change_type}, features={features}, confidence={confidence}"
        )
        return tag
    finally:
        session.close()


def get_tags_for_snapshot(snapshot_id: int) -> list[ChangelogTag]:
    session = get_session()
    try:
        return session.query(ChangelogTag).filter_by(snapshot_id=snapshot_id).all()
    finally:
        session.close()
