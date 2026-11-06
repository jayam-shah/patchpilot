import resend

from config import EMAIL_FROM, NOTIFICATION_EMAIL, RESEND_API_KEY
from logger import get_logger

logger = get_logger(__name__)

resend.api_key = RESEND_API_KEY


def send_pr_notification(
    repo_url: str,
    file_path: str,
    pr_url: str,
    api_name: str = "Stripe",
) -> bool:
    if not RESEND_API_KEY:
        logger.warning("RESEND_API_KEY not set — skipping email notification")
        return False

    repo_name = repo_url.rstrip("/").split("/")[-1]

    try:
        resend.Emails.send(
            {
                "from": EMAIL_FROM,
                "to": NOTIFICATION_EMAIL,
                "subject": f"[PatchPilot] Breaking change fixed in {repo_name}",
                "html": f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin:0; padding:0; background:#f6f8fa; font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;">

<table width="100%" cellpadding="0" cellspacing="0" style="background:#f6f8fa; padding:40px 0;">
<tr><td align="center">

  <table width="560" cellpadding="0" cellspacing="0" style="background:#ffffff; border:1px solid #d0d7de; border-radius:8px; overflow:hidden;">

    <tr>
      <td style="background:#0d1117; padding:20px 32px; display:flex; align-items:center;">
        <span style="color:#ffffff; font-size:16px; font-weight:600;">PatchPilot</span>
        <span style="color:#7d8590; font-size:13px; margin-left:8px;">— automated API patch management</span>
      </td>
    </tr>

    <tr>
      <td style="padding:32px;">

        <p style="margin:0 0 4px; font-size:13px; color:#57606a; text-transform:uppercase; letter-spacing:0.05em; font-weight:600;">{api_name} API · Breaking change detected</p>
        <h1 style="margin:0 0 20px; font-size:22px; font-weight:700; color:#1f2328; line-height:1.3;">
          A fix was opened for <span style="color:#0969da;">{repo_name}</span>
        </h1>

        <p style="margin:0 0 24px; font-size:15px; color:#57606a; line-height:1.6;">
          PatchPilot detected a breaking change in the <strong>{api_name} API</strong>,
          scanned your codebase, and automatically opened a pull request with the fix.
        </p>

        <table width="100%" cellpadding="0" cellspacing="0" style="background:#f6f8fa; border:1px solid #d0d7de; border-radius:6px; margin-bottom:24px;">
          <tr>
            <td style="padding:16px 20px; border-bottom:1px solid #d0d7de;">
              <span style="font-size:12px; color:#57606a; display:block; margin-bottom:2px;">Repository</span>
              <a href="{repo_url}" style="font-size:14px; color:#0969da; text-decoration:none; font-weight:500;">{repo_url}</a>
            </td>
          </tr>
          <tr>
            <td style="padding:16px 20px; border-bottom:1px solid #d0d7de;">
              <span style="font-size:12px; color:#57606a; display:block; margin-bottom:2px;">File patched</span>
              <code style="font-size:13px; color:#1f2328; background:#eaeef2; padding:2px 6px; border-radius:4px;">{file_path}</code>
            </td>
          </tr>
          <tr>
            <td style="padding:16px 20px;">
              <span style="font-size:12px; color:#57606a; display:block; margin-bottom:2px;">Pull request</span>
              <a href="{pr_url}" style="font-size:14px; color:#0969da; text-decoration:none; font-weight:500;">{pr_url}</a>
            </td>
          </tr>
        </table>

        <table width="100%" cellpadding="0" cellspacing="0">
          <tr>
            <td>
              <a href="{pr_url}" style="display:inline-block; background:#1f883d; color:#ffffff; font-size:14px; font-weight:600; padding:10px 20px; border-radius:6px; text-decoration:none;">
                Review pull request →
              </a>
            </td>
          </tr>
        </table>

      </td>
    </tr>

    <tr>
      <td style="padding:16px 32px; background:#f6f8fa; border-top:1px solid #d0d7de;">
        <p style="margin:0; font-size:12px; color:#57606a; line-height:1.5;">
          You received this because your repo is monitored by PatchPilot.
          &nbsp;·&nbsp;
          <a href="https://patchpilot-i8x1.onrender.com/dashboard" style="color:#0969da; text-decoration:none;">View dashboard</a>
        </p>
      </td>
    </tr>

  </table>

</td></tr>
</table>

</body>
</html>
            """,
            }
        )
        logger.info(f"Email notification sent for PR: {pr_url}")
        return True
    except Exception as e:  # noqa: BLE001
        logger.error(f"Failed to send email notification: {e}")
        return False


def send_password_reset_email(to_email: str, reset_url: str) -> bool:
    if not RESEND_API_KEY:
        logger.warning("RESEND_API_KEY not set — skipping password reset email")
        return False

    try:
        resend.Emails.send(
            {
                "from": EMAIL_FROM,
                "to": to_email,
                "subject": "Reset your PatchPilot password",
                "html": f"""
<div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif; max-width:480px; margin:0 auto; padding:24px; color:#1f2328;">
  <h2 style="margin:0 0 12px;">Reset your password</h2>
  <p style="font-size:15px; line-height:1.6; color:#57606a;">
    We got a request to reset the password for your PatchPilot account.
    This link works once and expires in 1 hour.
  </p>
  <p style="margin:24px 0;">
    <a href="{reset_url}" style="background:#1f6feb; color:#ffffff; padding:10px 20px; border-radius:6px; text-decoration:none; font-weight:600;">Choose a new password</a>
  </p>
  <p style="font-size:13px; line-height:1.5; color:#57606a;">
    If the button doesn't work, paste this link into your browser:<br>{reset_url}
  </p>
  <p style="font-size:13px; line-height:1.5; color:#57606a;">
    If you didn't ask for this, you can ignore this email. Your password won't change.
  </p>
</div>
""",
                "text": (
                    "Reset your PatchPilot password\n\n"
                    f"Open this link to choose a new password (works once, expires in 1 hour):\n{reset_url}\n\n"
                    "If you didn't ask for this, ignore this email."
                ),
            }
        )
        logger.info("Password reset email sent")
        return True
    except Exception as e:  # noqa: BLE001
        logger.error(f"Failed to send password reset email: {e}")
        return False
