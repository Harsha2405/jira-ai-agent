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

client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None


# =============================
# CLEAN JIRA MARKUP
# =============================
def clean_jira_markup(text):
    pattern = r'\[([^\|]+)\|mailto:[^\]]+\]'
    return re.sub(pattern, r'\1', text)


# =============================
# INTENT EXTRACTION
# =============================
def extract_with_gemini(text):
    if not client:
        return None

    prompt = f"""
Determine if this Jira ticket is requesting user access removal.

Consider related words like:
deactivate, disable, revoke, remove access,
relieving, terminate access, offboard.

If YES return ONLY JSON:
{{
  "action": "deactivate",
  "email": "exact-email-from-ticket",
  "systems": ["jira", "azure_devops", "confluence"]
}}

If NOT related to access removal return:
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
        print("Gemini Raw:", raw)

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
    print(f"Processing {email} in {system}")
    time.sleep(1)

    supported = ["jira", "azure_devops", "confluence"]

    if system.lower() in supported:
        return "Success"
    else:
        return "Unsupported System"


# =============================
# TRANSITION FUNCTIONS
# =============================
def transition_issue(issue_key, target_status):
    transitions_url = f"{JIRA_BASE}/rest/api/3/issue/{issue_key}/transitions"

    response = requests.get(transitions_url, auth=auth)
    transitions = response.json().get("transitions", [])

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

    return False


def smart_transition(issue_key, final_status):
    if transition_issue(issue_key, final_status):
        return

    if transition_issue(issue_key, "In Progress"):
        transition_issue(issue_key, final_status)


# =============================
# AI EXECUTIVE SUMMARY
# =============================
def generate_executive_summary(email, results):
    if not client:
        return "Executive summary unavailable."

    prompt = f"""
You are generating a professional executive summary.

IMPORTANT:
- Use the exact email address below.
- DO NOT replace it with placeholders.
- Do NOT modify the email.

User Email: {email}
Execution Results: {results}

Write a short 3–4 line executive summary describing:
- What was requested
- Which systems were processed
- Overall outcome
"""

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )

        return response.text.strip()

    except Exception as e:
        print("Executive Summary Error:", e)
        return "Executive summary generation failed."


# =============================
# WEBHOOK
# =============================
@app.post("/webhook")
async def jira_webhook(request: Request):
    payload = await request.json()

    issue_key = payload["issue"]["key"]
    description = payload["issue"]["fields"].get("description", "")

    description = clean_jira_markup(description)

    structured = extract_with_gemini(description)

    if not structured:
        return {"status": "Ignored"}

    if structured.get("action", "").lower() != "deactivate":
        return {"status": "Ignored"}

    email = structured.get("email", "not found")
    systems = structured.get("systems", ["jira"])

    results = {}

    for system in systems:
        results[system] = deactivate_user(email, system)

    # =============================
    # EXECUTIVE SUMMARY
    # =============================
    exec_summary = generate_executive_summary(email, results)

    result_text = ""
    for sys, status in results.items():
        result_text += f"{sys.upper()} : {status}\n"

    final_comment = (
        f"🤖 AI Agent Processed Access Removal Request\n\n"
        f"User: {email}\n\n"
        f"Execution Results:\n"
        f"{result_text}\n"
        f"AI Executive Summary:\n{exec_summary}"
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
                            {"type": "text", "text": final_comment}
                        ]
                    }
                ]
            }
        },
        auth=auth
    )

    # =============================
    # WORKFLOW DECISION
    # =============================
    if all(status == "Success" for status in results.values()):
        smart_transition(issue_key, "Done")

    elif any(status == "Unsupported System" for status in results.values()):
        smart_transition(issue_key, "In Review")

    return {"status": "Processed"}