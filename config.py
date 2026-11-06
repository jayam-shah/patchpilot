import os

from dotenv import load_dotenv

load_dotenv()

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://localhost/patchpilot_dev")
API_KEY = os.getenv("API_KEY")
RESEND_API_KEY = os.getenv("RESEND_API_KEY")
NOTIFICATION_EMAIL = os.getenv("NOTIFICATION_EMAIL", "shahjayam227@gmail.com")
EMAIL_FROM = os.getenv("EMAIL_FROM", "PatchPilot <onboarding@resend.dev>")

# GitHub App (PR authorization)
GITHUB_APP_ID = os.getenv("GITHUB_APP_ID", "")
GITHUB_APP_SLUG = os.getenv("GITHUB_APP_SLUG", "")
GITHUB_APP_PRIVATE_KEY_B64 = os.getenv("GITHUB_APP_PRIVATE_KEY_B64", "")
GITHUB_APP_WEBHOOK_SECRET = os.getenv("GITHUB_APP_WEBHOOK_SECRET", "")
