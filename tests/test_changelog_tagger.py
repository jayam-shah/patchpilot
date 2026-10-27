from changelog_tagger import detect_change_type, detect_features


def test_detects_breaking_change():
    text = "Breaking change: stripe.PaymentIntent.create now requires automatic_payment_methods"
    change_type, confidence = detect_change_type(text)
    assert change_type == "breaking"
    assert confidence == "high"


def test_detects_deprecation():
    text = "The charges endpoint is deprecated and will be removed in the next major version"
    change_type, confidence = detect_change_type(text)
    assert change_type == "deprecation"


def test_detects_new_feature():
    text = "New: introducing the batch API endpoint for bulk operations"
    change_type, confidence = detect_change_type(text)
    assert change_type == "new_feature"


def test_detects_other():
    text = "We updated our documentation and fixed some typos"
    change_type, _ = detect_change_type(text)
    assert change_type == "other"


def test_detects_stripe_features():
    text = "stripe.PaymentIntent.create now requires a new parameter. stripe.Customer.create is unchanged."
    features = detect_features(text, "stripe")
    assert "payment_intents" in features
    assert "customers" in features


def test_detects_openai_features():
    text = "client.chat.completions.create now accepts a new response_format parameter"
    features = detect_features(text, "openai")
    assert "chat.completions" in features


def test_no_features_for_wrong_service():
    text = "stripe.PaymentIntent.create now requires automatic_payment_methods"
    features = detect_features(text, "twilio")
    assert features == []


def test_empty_text_returns_other():
    change_type, _ = detect_change_type("")
    assert change_type == "other"
