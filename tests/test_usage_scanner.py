from scanner.usage_scanner import (
    deduplicate_findings,
    scan_dependency_file,
    scan_file_regex,
    scan_python_file_ast,
)


def test_scan_requirements_txt():
    content = "openai==1.3.0\nflask==2.0.0\nstripe>=5.0.0\n"
    result = scan_dependency_file(content, "requirements.txt")
    assert "openai" in result
    assert "stripe" in result
    assert result["openai"] == "1.3.0"
    assert result["stripe"] == "5.0.0"


def test_scan_package_json():
    import json

    content = json.dumps({"dependencies": {"openai": "^4.0.0", "express": "^4.18.0"}})
    result = scan_dependency_file(content, "package.json")
    assert "openai" in result
    assert "express" not in result


def test_scan_python_ast_detects_stripe():
    code = """
import stripe
intent = stripe.PaymentIntent.create(amount=1000, currency='usd')
customer = stripe.Customer.create(email='test@test.com')
"""
    findings = scan_python_file_ast(code, "payments.py")
    services = {f["service"] for f in findings}
    features = {f["feature"] for f in findings}
    assert "stripe" in services
    assert "payment_intents" in features
    assert "customers" in features
    assert all(f["detected_by"] == "ast" for f in findings)


def test_scan_python_ast_detects_openai():
    code = """
from openai import OpenAI
client = OpenAI()
response = client.chat.completions.create(
    model="gpt-4",
    messages=[{"role": "user", "content": "Hello"}]
)
"""
    findings = scan_python_file_ast(code, "ai.py")
    services = {f["service"] for f in findings}
    assert "openai" in services


def test_scan_regex_fallback():
    code = "result = stripe.PaymentIntent.create(amount=500)"
    findings = scan_file_regex(code, "payments.js")
    assert len(findings) > 0
    assert findings[0]["service"] == "stripe"
    assert findings[0]["detected_by"] == "regex"


def test_deduplicate_removes_duplicates():
    findings = [
        {"service": "stripe", "feature": "payment_intents", "file_path": "a.py"},
        {"service": "stripe", "feature": "payment_intents", "file_path": "a.py"},
        {"service": "stripe", "feature": "customers", "file_path": "a.py"},
    ]
    result = deduplicate_findings(findings)
    assert len(result) == 2


def test_unknown_code_returns_empty():
    code = "import flask\napp = Flask(__name__)\n"
    findings = scan_python_file_ast(code, "app.py")
    assert findings == []


def test_syntax_error_returns_empty():
    bad_code = "def broken(:\n    pass"
    findings = scan_python_file_ast(bad_code, "broken.py")
    assert findings == []
