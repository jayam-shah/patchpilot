FEATURE_CATALOG = {
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
}


def get_features_for_service(service: str) -> list[str]:
    return list(FEATURE_CATALOG.get(service, {}).keys())


def get_patterns_for_feature(service: str, feature: str) -> list[str]:
    return FEATURE_CATALOG.get(service, {}).get(feature, [])


def get_all_patterns_for_service(service: str) -> dict[str, list[str]]:
    return FEATURE_CATALOG.get(service, {})
```