import os
import time

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()
client = genai.Client(http_options=types.HttpOptions(timeout=20_000))  # milliseconds

for model in (os.getenv("GEMINI_MODEL"), os.getenv("GEMINI_BACKUP_MODEL")):
    if not model:
        continue
    print(f"Calling {model} ...", flush=True)
    start = time.perf_counter()
    try:
        reply = client.models.generate_content(model=model, contents="Reply with just: OK")
        print(f"  {reply.text.strip()}  in {time.perf_counter() - start:.1f}s")
    except Exception as e:
        print(f"  FAILED after {time.perf_counter() - start:.1f}s: {str(e)[:150]}")