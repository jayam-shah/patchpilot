import os

from dotenv import load_dotenv

load_dotenv()

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://localhost/patchpilot_dev")
API_KEY = os.getenv("API_KEY")
RESEND_API_KEY = os.getenv("RESEND_API_KEY")
NOTIFICATION_EMAIL = os.getenv("NOTIFICATION_EMAIL", "shahjayam227@gmail.com")
