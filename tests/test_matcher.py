from changelog_tagger import detect_change_type, detect_features
from matcher import should_patch


def test_should_patch_breaking():
    assert should_patch("breaking") is True


def test_should_patch_deprecation():
    assert should_patch("deprecation") is True


def test_should_not_patch_new_feature():
    assert should_patch("new_feature") is False


def test_should_not_patch_other():
    assert should_patch("other") is False


def test_breaking_change_detected_correctly():
    text = "Breaking change: stripe.PaymentIntent.create now requires automatic_payment_methods"
    change_type, _ = detect_change_type(text)
    assert should_patch(change_type) is True


def test_new_feature_not_patched():
    text = "New: introducing the batch API endpoint for bulk operations"
    change_type, _ = detect_change_type(text)
    assert should_patch(change_type) is False


def test_feature_match_stripe():
    text = (
        "stripe.PaymentIntent.create now requires automatic_payment_methods parameter"
    )
    features = detect_features(text, "stripe")
    assert "payment_intents" in features


def test_feature_mismatch_wrong_service():
    text = "stripe.PaymentIntent.create now requires automatic_payment_methods"
    features = detect_features(text, "openai")
    assert len(features) == 0
