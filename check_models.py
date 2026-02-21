from google import genai

API_KEY = "AIzaSyAWfwDlfVhFl415hjMnjibP4F-EgJ-0bGk"

client = genai.Client(api_key=API_KEY)

print("Available Models:\n")

for model in client.models.list():
    print(model.name)