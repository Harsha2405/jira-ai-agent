from fastapi import FastAPI, Request
import requests
import os
from dotenv import load_dotenv
import google.generativeai as genai
import json
import re

load_dotenv()

app = FastAPI()

JIRA_BASE = os.getenv("JIRA_BASE")
EMAIL = os.getenv("JIRA_EMAIL")
API_TOKEN = os.getenv("JIRA_API_TOKEN")

auth = (EMAIL, API_TOKEN)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel("gemini-1.5-flash-latest")
else:
    model = None


def extract_with_gemini(text):
    if not model:
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
        response = model.generate_content(prompt)
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

    processed_systems = ", ".join(systems)

    summary_text = (
        f"🤖 AI Agent Processed Request\n\n"
        f"Action: {action}\n"
        f"User: {email}\n"
        f"Systems: {processed_systems}\n"
        f"Execution Status: Success"
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