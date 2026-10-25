from patcher.ollama_patcher import clean_code_output


def test_strips_opening_fence():
    raw = "```python\nimport stripe\n\nstripe.PaymentIntent.create()\n```"
    result = clean_code_output(raw)
    assert not result.startswith("```")
    assert "import stripe" in result


def test_strips_closing_fence():
    raw = "```\nimport stripe\n```"
    result = clean_code_output(raw)
    assert not result.endswith("```")


def test_no_fences_unchanged():
    raw = "import stripe\n\nstripe.PaymentIntent.create()"
    result = clean_code_output(raw)
    assert result == raw


def test_strips_trailing_prose():
    raw = "import stripe\n\nstripe.PaymentIntent.create(\n    amount=100\n)\nThis change ensures compatibility with the latest Stripe API version."
    result = clean_code_output(raw)
    assert "compatibility" not in result
    assert "stripe.PaymentIntent.create" in result


def test_empty_input():
    result = clean_code_output("")
    assert result == ""


def test_only_fences():
    result = clean_code_output("```\n```")
    assert result == ""
    