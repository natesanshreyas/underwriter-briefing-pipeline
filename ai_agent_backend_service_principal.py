"""
AI Foundry Agent Backend - FastAPI Server (Service Principal / Azure AD Auth)

Connects the web frontend to Azure AI Foundry agent and Azure Functions API.
Handles chat interactions and function calling.

Uses Azure AD authentication instead of API keys for more secure access to OpenAI.
"""

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os
import json
import httpx
from typing import List, Optional, Dict, Any
from openai import AzureOpenAI
from azure.identity import DefaultAzureCredential
import asyncio

app = FastAPI(title="Underwriter Briefing Agent API")

# Serve static frontend
app.mount("/frontend", StaticFiles(directory="frontend"), name="frontend")

# CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Update with your frontend domain in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration
AZURE_FUNCTIONS_BASE_URL = os.getenv(
    "AZURE_FUNCTIONS_BASE_URL",
    "https://underwriter-briefing-api.azurewebsites.net/api"
)
OPENAI_ENDPOINT = os.getenv("OPENAI_ENDPOINT")
OPENAI_API_VERSION = os.getenv("OPENAI_API_VERSION", "2024-02-15-preview")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4")


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: List[ChatMessage]
    stream: bool = False


class ChatResponse(BaseModel):
    message: ChatMessage
    function_calls: Optional[List[Dict[str, Any]]] = None


# Load agent configuration
def load_agent_config():
    """Load agent configuration from file"""
    try:
        with open("ai_agent_config.json", "r") as f:
            return json.load(f)
    except FileNotFoundError:
        raise Exception("ai_agent_config.json not found")


# Initialize OpenAI client with Azure AD authentication
def get_openai_client():
    """
    Initialize Azure OpenAI client using Azure AD (Service Principal).
    
    Authenticates as a service principal instead of using API keys.
    The service principal must have "Cognitive Services OpenAI User" role
    assigned on the shreyasOAI resource.
    """
    if not OPENAI_ENDPOINT:
        raise HTTPException(
            status_code=500,
            detail="OPENAI_ENDPOINT not configured"
        )
    
    try:
        credential = DefaultAzureCredential()
        
        # Get token for Azure Cognitive Services
        token = credential.get_token("https://cognitiveservices.azure.com/.default")
        
        return AzureOpenAI(
            azure_ad_token_provider=lambda: credential.get_token("https://cognitiveservices.azure.com/.default").token,
            api_version=OPENAI_API_VERSION,
            azure_endpoint=OPENAI_ENDPOINT
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to authenticate with Azure AD: {str(e)}"
        )


# Function calling implementations
async def call_get_briefing(briefing_id: str, company: str) -> Dict[str, Any]:
    """Call Azure Function to get briefing by ID"""
    url = f"{AZURE_FUNCTIONS_BASE_URL}/GetBriefing"
    params = {"id": briefing_id, "company": company}

    async with httpx.AsyncClient() as client:
        response = await client.get(url, params=params, timeout=30.0)

        if response.status_code == 200:
            return response.json()
        elif response.status_code == 404:
            return {"error": "Briefing not found"}
        else:
            return {"error": f"API error: {response.status_code}"}


async def call_get_briefings_by_email(email: str, limit: int = 10) -> Dict[str, Any]:
    """Call Azure Function to get briefings by email"""
    url = f"{AZURE_FUNCTIONS_BASE_URL}/GetBriefingsByEmail"
    params = {"email": email, "limit": limit}

    async with httpx.AsyncClient() as client:
        response = await client.get(url, params=params, timeout=30.0)

        if response.status_code == 200:
            return response.json()
        else:
            return {"error": f"API error: {response.status_code}"}


async def call_get_briefings_by_company(company: str, limit: int = 10) -> Dict[str, Any]:
    """Call Azure Function to get briefings by company"""
    url = f"{AZURE_FUNCTIONS_BASE_URL}/GetBriefingsByCompany"
    params = {"company": company, "limit": limit}

    async with httpx.AsyncClient() as client:
        response = await client.get(url, params=params, timeout=30.0)

        if response.status_code == 200:
            return response.json()
        else:
            return {"error": f"API error: {response.status_code}"}



async def execute_function_call(function_name: str, arguments: Dict[str, Any]) -> str:
    """Execute the appropriate function based on name"""
    if function_name == "get_briefing":
        result = await call_get_briefing(
            arguments.get("id"),
            arguments.get("company")
        )
    elif function_name == "get_briefings_by_email":
        result = await call_get_briefings_by_email(
            arguments.get("email"),
            arguments.get("limit", 10)
        )
    elif function_name == "get_briefings_by_company":
        result = await call_get_briefings_by_company(
            arguments.get("company"),
            arguments.get("limit", 10)
        )
    else:
        result = {"error": f"Unknown function: {function_name}"}
    
    return json.dumps(result, indent=2)


@app.get("/")
async def root():
    """Serve the frontend UI"""
    return FileResponse("frontend/index.html")


@app.get("/health")
async def health():
    """Health check"""
    return {
        "status": "running",
        "service": "Underwriter Briefing Agent Backend",
        "azure_functions_url": AZURE_FUNCTIONS_BASE_URL,
        "auth_method": "Azure AD Service Principal"
    }


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Handle chat interactions with the AI agent.
    Supports function calling to retrieve briefings.
    """
    try:
        client = get_openai_client()
        agent_config = load_agent_config()
        
        # Prepare messages with system prompt
        messages = [
            {"role": "system", "content": agent_config["instructions"]}
        ]
        messages.extend([{"role": m.role, "content": m.content} for m in request.messages])
        
        # Prepare function definitions
        functions = [tool["function"] for tool in agent_config["tools"]]
        
        # First API call
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=messages,
            functions=functions,
            function_call="auto",
            temperature=agent_config.get("temperature", 0.7)
        )
        
        message = response.choices[0].message
        function_calls_made = []
        
        # Handle function calling
        while message.function_call:
            function_name = message.function_call.name
            function_args = json.loads(message.function_call.arguments)
            
            # Execute the function
            function_result = await execute_function_call(function_name, function_args)
            
            # Track function call
            function_calls_made.append({
                "name": function_name,
                "arguments": function_args,
                "result": json.loads(function_result)
            })
            
            # Add function call and result to messages
            messages.append({
                "role": "assistant",
                "content": None,
                "function_call": {
                    "name": function_name,
                    "arguments": message.function_call.arguments
                }
            })
            messages.append({
                "role": "function",
                "name": function_name,
                "content": function_result
            })
            
            # Get next response
            response = client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=messages,
                functions=functions,
                function_call="auto",
                temperature=agent_config.get("temperature", 0.7)
            )
            message = response.choices[0].message
        
        # Return final response
        return ChatResponse(
            message=ChatMessage(
                role="assistant",
                content=message.content or ""
            ),
            function_calls=function_calls_made if function_calls_made else None
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/config")
async def get_config():
    """Get agent configuration"""
    try:
        config = load_agent_config()
        return config
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
