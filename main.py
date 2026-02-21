from fastapi import FastAPI, Request
import requests
import os
import re
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = FastAPI()

# Read credentials from .env
JIRA_BASE = os.getenv("JIRA_BASE")
EMAIL = os.getenv("JIRA_EMAIL")
API_TOKEN = os.getenv("JIRA_API_TOKEN")

auth = (EMAIL, API_TOKEN)


@app.post("/webhook")
async def jira_webhook(request: Request):
    payload = await request.json()

    issue_key = payload["issue"]["key"]
    print("Issue key received:", issue_key)

    # Extract description safely
    description = payload["issue"]["fields"].get("description", "")
    print("Description:", description)

    # Extract email using regex
    email_match = re.search(r'[\w\.-]+@[\w\.-]+', str(description))

    if email_match:
        extracted_email = email_match.group(0)
    else:
        extracted_email = "No email found"

    print("Extracted email:", extracted_email)

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
                                "text": f"🤖 AI Agent detected email: {extracted_email}"
                            }
                        ]
                    }
                ]
            }
        },
        auth=auth
    )

    print("Jira API response:", response.status_code)
    print("Jira API response text:", response.text)

    return {"status": "success"}