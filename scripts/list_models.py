from dotenv import load_dotenv
from google import genai

load_dotenv()
client = genai.Client()          # keep a reference so it stays open

for m in client.models.list():
    if "flash" in m.name:
        print(m.name.removeprefix("models/"))