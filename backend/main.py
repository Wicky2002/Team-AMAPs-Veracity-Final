from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="Vector Agents - Growth Loop API")

# Allow Next.js frontend to communicate with the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------------------
# Define the Request Payload Schema
# -----------------------------------------
class ChatRequest(BaseModel):
    message: str
    mode: str = "research"

# -----------------------------------------
# API Endpoints
# -----------------------------------------
@app.get("/")
def read_root():
    return {"status": "Vector Agents API is running!"}

@app.post("/api/chat")
async def process_chat(request: ChatRequest):
    """
    Mock endpoint to simulate the multi-agent routing.
    Currently hardcoded to return the Research UI Schema for Sprint 1 testing.
    """
    
    # In Sprint 2, this will route to the actual LLM and Supabase DB
    # For now, we return the strict JSON schema to test the Next.js UI Interceptor
    
    mock_research_response = {
        "ui_component": "ResearchSummaryCard",
        "target_market": "AI SDR (Vector Agents - Lilian)",
        "status": "complete",
        "findings": {
            "competitor_gaps": [
                "Most competitors rely solely on email outreach; weak multi-channel orchestration.",
                "High friction in syncing data back to Salesforce/HubSpot in real-time."
            ],
            "audience_signals": [
                "VP Sales on LinkedIn are complaining about generic AI email personalization.",
                "High intent shown in communities for tools that handle objection handling natively."
            ]
        },
        "recommended_angles": [
            "Lead with native multi-channel capabilities (Email + LinkedIn).",
            "Focus on deep CRM integration and automatic objection handling."
        ]
    }

    return {"response": mock_research_response}