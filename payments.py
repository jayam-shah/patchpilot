import os

import stripe

from logger import get_logger

logger = get_logger(__name__)

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

PRO_PRICE_ID = os.getenv("STRIPE_PRO_PRICE_ID")
WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")


def create_checkout_session(user_email: str, user_id: int) -> str:
    session = stripe.checkout.Session.create(
        mode="subscription",
        customer_email=user_email,
        line_items=[{"price": PRO_PRICE_ID, "quantity": 1}],
        success_url="https://patchpilot-i8x1.onrender.com/dashboard?upgraded=true",
        cancel_url="https://patchpilot-i8x1.onrender.com/pricing",
        metadata={"user_id": str(user_id)},
    )
    logger.info(f"Checkout session created for user {user_id}: {session.id}")
    return session.url


def handle_webhook_event(payload: bytes, sig_header: str) -> dict:
    try:
        if WEBHOOK_SECRET:
            event = stripe.Webhook.construct_event(payload, sig_header, WEBHOOK_SECRET)
        else:
            import json

            event = json.loads(payload)
    except stripe.error.SignatureVerificationError as e:
        logger.warning(f"Invalid Stripe webhook signature: {e}")
        return {"error": "invalid_signature"}

    logger.info(f"Stripe webhook received: {event['type']}")
    return {"event_type": event["type"], "data": event["data"]["object"]}
