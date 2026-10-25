import resend

from config import NOTIFICATION_EMAIL, RESEND_API_KEY
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

    try:
        resend.Emails.send(
            {
                "from": "PatchPilot <onboarding@resend.dev>",
                "to": NOTIFICATION_EMAIL,
                "subject": f"[PatchPilot] PR opened — {repo_url.split('/')[-1]}",
                "html": f"""
                <div style="font-family: sans-serif; max-width: 600px; margin: 0 auto;">
                    <h2 style="color: #1a1a2e;">PatchPilot opened a PR</h2>
                    <p>A breaking change was detected in the <strong>{api_name} API</strong>.
                    PatchPilot scanned your repo and opened a pull request with the fix.</p>

                    <table style="width:100%; border-collapse:collapse; margin: 20px 0;">
                        <tr>
                            <td style="padding:8px; color:#666; width:120px;">Repository</td>
                            <td style="padding:8px;"><a href="{repo_url}">{repo_url}</a></td>
                        </tr>
                        <tr style="background:#f9f9f9;">
                            <td style="padding:8px; color:#666;">File patched</td>
                            <td style="padding:8px; font-family:monospace;">{file_path}</td>
                        </tr>
                        <tr>
                            <td style="padding:8px; color:#666;">Pull request</td>
                            <td style="padding:8px;"><a href="{pr_url}">{pr_url}</a></td>
                        </tr>
                    </table>

                    <a href="{pr_url}"
                       style="background:#3b82f6; color:white; padding:12px 24px;
                              text-decoration:none; border-radius:6px; display:inline-block;">
                        Review PR →
                    </a>

                    <p style="color:#999; font-size:12px; margin-top:32px;">
                        Sent by PatchPilot · <a href="https://patchpilot-i8x1.onrender.com">Dashboard</a>
                    </p>
                </div>
            """,
            }
        )
        logger.info(f"Email notification sent for PR: {pr_url}")
        return True
    except Exception as e:  # noqa: BLE001
        logger.error(f"Failed to send email notification: {e}")
        return False
