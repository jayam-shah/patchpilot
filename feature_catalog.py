FEATURE_CATALOG = {
    "openai": {
        "chat.completions": [
            "client.chat.completions.create",
            "openai.ChatCompletion.create",
            "chat.completions",
            "/v1/chat/completions",
        ],
        "embeddings": [
            "client.embeddings.create",
            "openai.Embedding.create",
            "/v1/embeddings",
        ],
        "images": [
            "client.images.generate",
            "openai.Image.create",
            "/v1/images/generations",
        ],
        "audio": [
            "client.audio.transcriptions.create",
            "client.audio.speech.create",
            "/v1/audio",
        ],
        "fine_tuning": [
            "client.fine_tuning.jobs.create",
            "openai.FineTuningJob.create",
            "/v1/fine_tuning",
        ],
        "assistants": [
            "client.beta.assistants",
            "client.beta.threads",
            "/v1/assistants",
            "/v1/threads",
        ],
        "models": [
            "client.models.list",
            "openai.Model.list",
            "/v1/models",
        ],
    },
    "stripe": {
        "payment_intents": [
            "stripe.PaymentIntent.create",
            "stripe.PaymentIntent.confirm",
            "stripe.PaymentIntent.retrieve",
            "PaymentIntentCreateParams",
        ],
        "customers": [
            "stripe.Customer.create",
            "stripe.Customer.retrieve",
            "stripe.Customer.modify",
        ],
        "subscriptions": [
            "stripe.Subscription.create",
            "stripe.Subscription.modify",
            "stripe.Subscription.cancel",
        ],
        "charges": [
            "stripe.Charge.create",
            "stripe.Charge.retrieve",
        ],
        "refunds": [
            "stripe.Refund.create",
        ],
        "webhooks": [
            "stripe.Webhook.construct_event",
            "stripe.webhook",
        ],
        "checkout": [
            "stripe.checkout.Session.create",
            "stripe.checkout",
        ],
    },
    "twilio": {
        "sms": [
            "client.messages.create",
            "MessagingResponse",
            "twilio.twiml.messaging",
        ],
        "voice": [
            "client.calls.create",
            "VoiceResponse",
            "twilio.twiml.voice",
        ],
        "verify": [
            "client.verify",
            "verifications.create",
            "verification_checks.create",
        ],
        "whatsapp": [
            "whatsapp:",
            "client.messages.create",
        ],
    },
    "plaid": {
        "transactions": [
            "client.transactions_sync",
            "client.transactions_get",
            "transactions_get",
            "transactions_sync",
        ],
        "auth": [
            "client.auth_get",
            "auth_get",
            "LinkTokenCreateRequest",
        ],
        "identity": [
            "client.identity_get",
            "identity_get",
        ],
        "link": [
            "client.link_token_create",
            "link_token_create",
            "PlaidLink",
        ],
    },
    "sendgrid": {
        "mail_send": [
            "sendgrid.SendGridAPIClient",
            "sg.send",
            "Mail(",
            "sendgrid.helpers.mail",
        ],
        "templates": [
            "TemplateId",
            "DynamicTemplateData",
            "template_id",
        ],
    },
    "slack": {
        "messaging": [
            "client.chat_postMessage",
            "chat.postMessage",
            "WebClient",
        ],
        "events": [
            "slack_bolt",
            "@app.event",
            "SlackEventAdapter",
        ],
        "blocks": [
            "blocks=",
            "SectionBlock",
            "BlockKit",
        ],
    },
    "github": {
        "repos": [
            "repo.get_contents",
            "repo.create_file",
            "Github(",
            "github.Github",
        ],
        "pull_requests": [
            "repo.create_pull",
            "get_pulls",
            "pull_request",
        ],
        "issues": [
            "repo.create_issue",
            "get_issues",
        ],
    },
    "anthropic": {
        "messages": [
            "client.messages.create",
            "anthropic.Anthropic",
            "claude-",
            "from anthropic",
        ],
    },
    "shopify": {
        "products": [
            "shopify.Product",
            "shopify.product",
        ],
        "orders": [
            "shopify.Order",
            "shopify.order",
        ],
        "graphql": [
            "shopify.GraphQL",
            "StorefrontAPI",
        ],
    },
}


def get_features_for_service(service: str) -> list[str]:
    return list(FEATURE_CATALOG.get(service, {}).keys())


def get_patterns_for_feature(service: str, feature: str) -> list[str]:
    return FEATURE_CATALOG.get(service, {}).get(feature, [])


def get_all_patterns_for_service(service: str) -> dict[str, list[str]]:
    return FEATURE_CATALOG.get(service, {})
