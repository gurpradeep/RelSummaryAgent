import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
REPO_PATH = os.getenv("REPO_PATH", "../LULCQuant")  # Path to your Git repository
