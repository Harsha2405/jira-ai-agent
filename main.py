from fastapi import FastAPI, Request
import requests
import os
from dotenv import load_dotenv
from google import genai
import json
import re
import time

load_dotenv()

app = FastAPI()

# =============================
# ENV VARIABLES
# =============================
JIRA_BASE = os.getenv("JIRA_BASE")
JIRA_EMAIL = os.getenv("JIRA_EMAIL")
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

auth = (JIRA_EMAIL, JIRA_API_TOKEN)

# =============================
# GEMINI CLIENT
# =============================
client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None


# =============================
# CLEAN JIRA MARKUP
# =============================
def clean_jira_markup(text):
    pattern = r'\[([^\|]+)\|mailto:[^\]]+\]'
    return re.sub(pattern, r'\1', text)


# =============================
# GEMINI EXTRACTION
# =============================
def extract_with_gemini(text):
    if not client:
        print("Gemini not initialized")
        return None

    prompt = f"""
    Analyze the following Jira ticket.

    If it is a deactivation request, return ONLY JSON in this format:

    {{
      "action": "deactivate",
      "email": "user@example.com",
      "systems": ["jira", "azure_devops", "confluence"]
    }}

    If not related to deactivation, return:
    {{
      "action": "ignore"
    }}

    Ticket:
    {text}
    """

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )

        raw = response.text.strip()
        print("Gemini Raw Response:", raw)

        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            return json.loads(match.group())

        return None

    except Exception as e:
        print("Gemini Error:", e)
        return None


# =============================
# EXECUTION ENGINE
# =============================
def deactivate_user(email, system):
    print(f"Processing deactivation for {email} in {system}")
    time.sleep(1)

    supported_systems = ["jira", "azure_devops", "confluence"]

    if system.lower() in supported_systems:
        return "Success"
    else:
        return "Unsupported System"


# =============================
# TRANSITION FUNCTION
# =============================
def transition_issue(issue_key, target_status):
    transitions_url = f"{JIRA_BASE}/rest/api/3/issue/{issue_key}/transitions"

    response = requests.get(transitions_url, auth=auth)
    transitions = response.json().get("transitions", [])

    print("Available transitions:")
    for t in transitions:
        print("->", t["name"])

    for t in transitions:
        if t["name"].lower() == target_status.lower():
            transition_id = t["id"]

            r = requests.post(
                transitions_url,
                json={"transition": {"id": transition_id}},
                auth=auth
            )

            print(f"Moved to {target_status}:", r.status_code)
            return True

    print(f"Transition to {target_status} NOT available.")
    return False


# =============================
# WEBHOOK
# =============================
@app.post("/webhook")
async def jira_webhook(request: Request):
    payload = await request.json()

    issue_key = payload["issue"]["key"]
    description = payload["issue"]["fields"].get("description", "")

    description = clean_jira_markup(description)

    print("Issue:", issue_key)
    print("Description:", description)

    structured = extract_with_gemini(description)

    if not structured:
        print("No structured data.")
        return {"status": "Ignored"}

    if structured.get("action", "").lower() != "deactivate":
        print("Not a deactivation request.")
        return {"status": "Ignored"}

    email = structured.get("email", "not found")
    systems = structured.get("systems", ["jira"])

    results = {}

    for system in systems:
        results[system] = deactivate_user(email, system)

    # =============================
    # COMMENT SUMMARY
    # =============================
    result_text = ""
    for sys, status in results.items():
        result_text += f"{sys.upper()} : {status}\n"

    summary = (
        f"🤖 AI Agent Processed Deactivation Request\n\n"
        f"User: {email}\n\n"
        f"Execution Results:\n"
        f"{result_text}"
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
                            {"type": "text", "text": summary}
                        ]
                    }
                ]
            }
        },
        auth=auth
    )

    # =============================
    # SMART WORKFLOW ROUTING
    # =============================

    # Step 1: Move to In Progress (if available)
    transition_issue(issue_key, "In Progress")

    # Step 2: Final Routing
    if all(status == "Success" for status in results.values()):
        transition_issue(issue_key, "Done")

    elif any(status == "Unsupported System" for status in results.values()):
        transition_issue(issue_key, "In Review")

    else:
        print("Failure detected — staying in workflow.")

    return {"status": "Processed"}