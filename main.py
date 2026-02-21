from fastapi import FastAPI, Request
import requests
import os
from dotenv import load_dotenv
from google import genai
import json
import re
import random
import time

load_dotenv()

app = FastAPI()

JIRA_BASE = os.getenv("JIRA_BASE")
EMAIL = os.getenv("JIRA_EMAIL")
API_TOKEN = os.getenv("JIRA_API_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

auth = (EMAIL, API_TOKEN)

# Initialize Gemini client
if GEMINI_API_KEY:
    client = genai.Client(api_key=GEMINI_API_KEY)
else:
    client = None


# ----------------------------
# Gemini Extraction
# ----------------------------
def extract_with_gemini(text):
    if not client:
        return None

    prompt = f"""
    Extract structured information from this Jira request.

    Text:
    {text}

    Return ONLY valid JSON in this format:
    {{
      "action": "deactivate",
      "email": "user@example.com",
      "systems": ["jira", "confluence", "azure_devops"]
    }}
    """

    try:
        response = client.models.generate_content(
            model="gemini-1.5-flash",
            contents=prompt,
        )

        raw_text = response.text.strip()
        print("Gemini Raw Response:")
        print(raw_text)

        json_match = re.search(r'\{.*\}', raw_text, re.DOTALL)

        if json_match:
            return json.loads(json_match.group())
        else:
            return None

    except Exception as e:
        print("Gemini Error:", e)
        return None


# ----------------------------
# Simulated Deactivation Engine
# ----------------------------
def deactivate_user(email, system):
    print(f"Processing deactivation for {email} in {system}")
    time.sleep(1)

    if random.choice([True, True, True, False]):
        return "Success"
    else:
        return "Failed"


# ----------------------------
# Webhook Endpoint
# ----------------------------
@app.post("/webhook")
async def jira_webhook(request: Request):
    payload = await request.json()

    issue_key = payload["issue"]["key"]
    description = payload["issue"]["fields"].get("description", "")

    print("Issue:", issue_key)
    print("Description:", description)

    structured_data = extract_with_gemini(description)

    if structured_data:
        email = structured_data.get("email", "not found")
        action = structured_data.get("action", "unknown")
        systems = structured_data.get("systems", [])
    else:
        email_match = re.search(r'[\w\.-]+@[\w\.-]+', description)
        email = email_match.group(0) if email_match else "not found"
        action = "deactivate"
        systems = ["jira"]

    if not systems:
        systems = ["jira"]

    results = {}
    for system in systems:
        results[system] = deactivate_user(email, system)

    result_lines = ""
    for sys, status in results.items():
        result_lines += f"{sys.upper()} : {status}\n"

    summary_text = (
        f"🤖 AI Agent Processed Request\n\n"
        f"Action: {action}\n"
        f"User: {email}\n\n"
        f"Execution Results:\n"
        f"{result_lines}"
    )

    comment_url = f"{JIRA_BASE}/rest/api/3/issue/{issue_key}/comment"

    response = requests.post(
        comment_url,
        json={
            "body": {
                "type": "doc",
                "version": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "content": [
                            {
                                "type": "text",
                                "text": summary_text
                            }
                        ]
                    }
                ]
            }
        },
        auth=auth
    )

    print("Jira Response:", response.status_code)
    print("Jira Response Text:", response.text)

    return {"status": "Processed"}