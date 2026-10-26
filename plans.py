PLAN_LIMITS = {
    "free": {
        "max_repos": 1,
        "max_apis": 3,
        "apis_allowed": ["stripe", "twilio", "openai"],
        "email_notifications": True,
        "activity_feed": True,
        "priority_support": False,
    },
    "pro": {
        "max_repos": 10,
        "max_apis": 9,
        "apis_allowed": [
            "stripe",
            "twilio",
            "openai",
            "plaid",
            "sendgrid",
            "slack",
            "github",
            "anthropic",
            "shopify",
        ],
        "email_notifications": True,
        "activity_feed": True,
        "priority_support": True,
    },
    "enterprise": {
        "max_repos": -1,
        "max_apis": -1,
        "apis_allowed": "__all__",
        "email_notifications": True,
        "activity_feed": True,
        "priority_support": True,
    },
}


def get_effective_plan(user) -> str:
    from datetime import UTC, datetime

    if not user:
        return "free"

    if user.plan_override:
        if user.plan_expires_at is None:
            return user.plan_override
        if datetime.now(tz=UTC) < user.plan_expires_at.replace(tzinfo=UTC):
            return user.plan_override

    if user.plan_expires_at and datetime.now(tz=UTC) > user.plan_expires_at.replace(
        tzinfo=UTC
    ):
        return "free"

    return user.plan or "free"


def get_plan_limits(user) -> dict:
    plan = get_effective_plan(user)
    return PLAN_LIMITS.get(plan, PLAN_LIMITS["free"])


def check_repo_limit(user, current_repo_count: int) -> tuple[bool, str]:
    limits = get_plan_limits(user)
    max_repos = limits["max_repos"]

    if max_repos == -1:
        return True, ""

    if current_repo_count >= max_repos:
        plan = get_effective_plan(user)
        if plan == "free":
            return (
                False,
                f"Free plan allows {max_repos} repo. Upgrade to Pro to monitor up to 10 repos.",
            )
        return (
            False,
            f"Your {plan} plan allows {max_repos} repos. Contact us to upgrade.",
        )

    return True, ""


def check_api_limit(user, api_name: str) -> tuple[bool, str]:
    limits = get_plan_limits(user)
    allowed = limits["apis_allowed"]

    if allowed == "__all__":
        return True, ""

    if api_name not in allowed:
        plan = get_effective_plan(user)
        return (
            False,
            f"The {api_name.title()} API is not available on the {plan} plan. Upgrade to Pro to access all 9 APIs.",
        )

    return True, ""
