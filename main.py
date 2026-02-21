from fastapi import FastAPI, Request
import requests
import os
from dotenv import load_dotenv
import google.generativeai as genai
import json

# Load environment variables
load_dotenv()

app = FastAPI()

# Jira credentials
JIRA_BASE = os.getenv("JIRA_BASE")
EMAIL = os.getenv("JIRA_EMAIL")
API_TOKEN = os.getenv("JIRA_API_TOKEN")

auth = (EMAIL, API_TOKEN)

# Gemini setup
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")


def extract_with_gemini(text):
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

    response = model.generate_content(prompt)
    raw_text = response.text.strip()

    try:
        return json.loads(raw_text)
    except:
        return {
            "action": "unknown",
            "email": "not found",
            "systems": []
        }


@app.post("/webhook")
async def jira_webhook(request: Request):
    payload = await request.json()

    issue_key = payload["issue"]["key"]
    description = payload["issue"]["fields"].get("description", "")

    print("Issue:", issue_key)
    print("Description:", description)

    # Use Gemini to extract info
    structured_data = extract_with_gemini(description)

    print("AI Extracted:", structured_data)

    email = structured_data.get("email", "not found")
    action = structured_data.get("action", "unknown")
    systems = structured_data.get("systems", [])

    # Simulate deactivation
    execution_status = "Success"
    processed_systems = ", ".join(systems) if systems else "Not specified"

    summary_text = (
        f"🤖 AI Agent Processed Request\n\n"
        f"Action: {action}\n"
        f"User: {email}\n"
        f"Systems: {processed_systems}\n"
        f"Execution Status: {execution_status}"
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

    return {"status": "AI processed successfully"}