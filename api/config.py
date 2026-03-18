import os
from dotenv import load_dotenv

load_dotenv()

API_HOST = os.getenv("API_HOST", "127.0.0.1")
API_PORT = int(os.getenv("API_PORT", "8000"))

WEB_ORIGIN_DEV = os.getenv("WEB_ORIGIN_DEV", "http://localhost:3000")
WEB_ORIGIN_NGROK = os.getenv("WEB_ORIGIN_NGROK", "")
