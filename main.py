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

# -------------------------
# Environment Variables
# -------------------------
JIRA_BASE = os.getenv("JIRA_BASE")
EMAIL = os.getenv("JIRA_EMAIL")
API_TOKEN = os.getenv("JIRA_API_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

auth = (EMAIL, API_TOKEN)

# -------------------------
# Gemini Client Setup
# -------------------------
if GEMINI_API_KEY:
    client = genai.Client(api_key=GEMINI_API_KEY)
else:
    client = None


# -------------------------
# Gemini Extraction
# -------------------------
def extract_with_gemini(text):
    if not client:
        print("Gemini client not initialized")
        return None

    prompt = f"""
    Analyze this Jira ticket and determine if it is a deactivation request.

    Text:
    {text}

    If it is a deactivation request, return ONLY valid JSON:

    {{
      "action": "deactivate",
      "email": "user@example.com",
      "systems": ["jira", "confluence", "azure_devops"]
    }}

    If it is NOT a deactivation request, return:

    {{
      "action": "ignore"
    }}
    """

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
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


# -------------------------
# Simulated Deactivation Engine
# -------------------------
def deactivate_user(email, system):
    print(f"Processing deactivation for {email} in {system}")
    time.sleep(1)

    if random.choice([True, True, True, False]):
        return "Success"
    else:
        return "Failed"


# -------------------------
# Transition Issue to Done
# -------------------------
def transition_issue_to_done(issue_key):
    transitions_url = f"{JIRA_BASE}/rest/api/3/issue/{issue_key}/transitions"

    response = requests.get(transitions_url, auth=auth)
    transitions = response.json().get("transitions", [])

    done_transition_id = None

    for t in transitions:
        if t["name"].lower() == "done":
            done_transition_id = t["id"]
            break

    if done_transition_id:
        transition_response = requests.post(
            transitions_url,
            json={"transition": {"id": done_transition_id}},
            auth=auth
        )
        print("Transition Response:", transition_response.status_code)


# -------------------------
# Webhook Endpoint
# -------------------------
@app.post("/webhook")
async def jira_webhook(request: Request):
    payload = await request.json()

    issue_key = payload["issue"]["key"]
    description = payload["issue"]["fields"].get("description", "")

    print("Issue:", issue_key)
    print("Description:", description)

    structured_data = extract_with_gemini(description)

    # Ignore if Gemini failed
    if not structured_data:
        print("No structured data. Ignoring.")
        return {"status": "Ignored"}

    action = structured_data.get("action", "ignore")

    # Trigger only for deactivation
    if action.lower() != "deactivate":
        print("Not a deactivation request. Ignoring.")
        return {"status": "Ignored - Not deactivation"}

    email = structured_data.get("email", "not found")
    systems = structured_data.get("systems", [])

    if not systems:
        systems = ["jira"]

    results = {}

    for system in systems:
        results[system] = deactivate_user(email, system)

    result_lines = ""
    for sys, status in results.items():
        result_lines += f"{sys.upper()} : {status}\n"

    summary_text = (
        f"🤖 AI Agent Processed Deactivation Request\n\n"
        f"User: {email}\n\n"
        f"Execution Results:\n"
        f"{result_lines}"
    )

    comment_url = f"{JIRA_BASE}/rest/api/3/issue/{issue_key}/comment"

    requests.post(
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

    # Auto move to Done if all systems succeeded
    if all(status == "Success" for status in results.values()):
        transition_issue_to_done(issue_key)

    return {"status": "Processed"}