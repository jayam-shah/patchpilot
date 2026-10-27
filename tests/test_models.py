from database import (
    ChangelogTag,
    RepoApiUsage,
    ServiceRequest,
    get_session,
    init_db,
)
from feature_catalog import (
    FEATURE_CATALOG,
    get_all_patterns_for_service,
    get_features_for_service,
    get_patterns_for_feature,
)


def test_feature_catalog_has_nine_services():
    assert len(FEATURE_CATALOG) == 9


def test_openai_has_correct_features():
    features = get_features_for_service("openai")
    assert "chat.completions" in features
    assert "embeddings" in features
    assert "images" in features


def test_stripe_patterns():
    patterns = get_patterns_for_feature("stripe", "payment_intents")
    assert "stripe.PaymentIntent.create" in patterns


def test_get_all_patterns_for_service():
    patterns = get_all_patterns_for_service("twilio")
    assert "sms" in patterns
    assert "voice" in patterns


def test_unknown_service_returns_empty():
    assert get_features_for_service("unknown_api") == []
    assert get_patterns_for_feature("unknown_api", "feature") == []


def test_repo_api_usage_table_exists():
    init_db()
    session = get_session()
    try:
        count = session.query(RepoApiUsage).count()
        assert count >= 0
    finally:
        session.close()


def test_changelog_tag_table_exists():
    init_db()
    session = get_session()
    try:
        count = session.query(ChangelogTag).count()
        assert count >= 0
    finally:
        session.close()


def test_service_request_table_exists():
    init_db()
    session = get_session()
    try:
        count = session.query(ServiceRequest).count()
        assert count >= 0
    finally:
        session.close()
