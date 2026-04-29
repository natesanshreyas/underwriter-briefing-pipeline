"""
AI Foundry Agent Backend - FastAPI Server (Foundry-hosted models)

Connects the web frontend to Azure AI Foundry agent and Azure Functions API.
Uses Azure AI Foundry-hosted models (like DeepSeek-V3.2) with Azure AD authentication.
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
import logging

# Enable detailed logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = FastAPI(title="Underwriter Briefing Agent API (Foundry)")

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

# Configuration - Foundry-specific
AZURE_FUNCTIONS_BASE_URL = os.getenv(
    "AZURE_FUNCTIONS_BASE_URL",
    "https://underwriter-briefing-api.azurewebsites.net/api"
)
# Foundry endpoint (not standalone OpenAI)
OPENAI_ENDPOINT = os.getenv(
    "OPENAI_ENDPOINT",
    "https://shreyasfoundry111111.services.ai.azure.com/"
)
OPENAI_API_VERSION = os.getenv("OPENAI_API_VERSION", "2024-08-01-preview")
# DeepSeek model deployed in Foundry
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "DeepSeek-V3.2")


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


# Initialize OpenAI client with Azure AD authentication (required for Foundry)
def get_openai_client():
    """
    Initialize Azure OpenAI client using Azure AD (Foundry requires RBAC).
    
    Uses DefaultAzureCredential which tries:
    1. Environment variables (AZURE_CLIENT_ID, AZURE_CLIENT_SECRET, AZURE_TENANT_ID)
    2. Managed Identity (if running in Azure)
    3. Azure CLI login
    """
    if not OPENAI_ENDPOINT:
        raise HTTPException(
            status_code=500,
            detail="OPENAI_ENDPOINT not configured"
        )
    
    try:
        credential = DefaultAzureCredential()
        
        return AzureOpenAI(
            azure_ad_token_provider=lambda: credential.get_token("https://ai.azure.com/.default").token,
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
        "service": "Underwriter Briefing Agent Backend (Foundry)",
        "azure_functions_url": AZURE_FUNCTIONS_BASE_URL,
        "foundry_endpoint": OPENAI_ENDPOINT,
        "model": OPENAI_MODEL,
        "auth_method": "Azure AD (Foundry RBAC)"
    }


@app.get("/debug")
async def debug_info():
    """Debug information endpoint"""
    info = {
        "foundry_endpoint": OPENAI_ENDPOINT,
        "model": OPENAI_MODEL,
        "api_version": OPENAI_API_VERSION,
        "config_file_exists": os.path.exists("ai_agent_config.json"),
    }
    
    # Try to get Azure AD token
    try:
        credential = DefaultAzureCredential()
        token = credential.get_token("https://ai.azure.com/.default")
        info["azure_ad_auth"] = "✓ Successfully obtained token (scope: https://ai.azure.com)"
    except Exception as e:
        info["azure_ad_auth"] = f"✗ Error: {str(e)}"
    
    # Try to load config
    try:
        with open("ai_agent_config.json", "r") as f:
            config = json.load(f)
        info["config_loaded"] = "✓ Config loaded successfully"
        info["config_tools_count"] = len(config.get("tools", []))
    except Exception as e:
        info["config_loaded"] = f"✗ Error: {str(e)}"
    
    # Try to create OpenAI client
    try:
        client = get_openai_client()
        info["openai_client"] = "✓ Client created successfully"
    except Exception as e:
        info["openai_client"] = f"✗ Error: {str(e)}"
    
    return info


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Handle chat interactions with the AI agent using Foundry-hosted model.
    Supports function calling to retrieve briefings.
    """
    try:
        logger.debug("Chat request received")
        
        client = get_openai_client()
        logger.debug("OpenAI client created successfully")
        
        agent_config = load_agent_config()
        logger.debug(f"Agent config loaded, tools: {[t['function']['name'] for t in agent_config['tools']]}")
        
        # Prepare messages with system prompt
        messages = [
            {"role": "system", "content": agent_config["instructions"]}
        ]
        messages.extend([{"role": m.role, "content": m.content} for m in request.messages])
        logger.debug(f"Messages prepared: {len(messages)} messages")
        
        # Prepare function definitions
        functions = [tool["function"] for tool in agent_config["tools"]]
        logger.debug(f"Functions prepared: {len(functions)} functions")
        
        # First API call to Foundry-hosted DeepSeek model
        logger.debug(f"Calling Foundry model: {OPENAI_MODEL}")
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=messages,
            functions=functions,
            function_call="auto",
            temperature=agent_config.get("temperature", 0.7)
        )
        logger.debug("Model response received")
        
        message = response.choices[0].message
        function_calls_made = []
        
        # Handle function calling
        while message.function_call:
            function_name = message.function_call.name
            function_args = json.loads(message.function_call.arguments)
            logger.debug(f"Function call: {function_name}({function_args})")
            
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
        
        logger.debug("Chat completed successfully")
        
        # Return final response
        return ChatResponse(
            message=ChatMessage(
                role="assistant",
                content=message.content or ""
            ),
            function_calls=function_calls_made if function_calls_made else None
        )
    
    except Exception as e:
        logger.error(f"Chat error: {type(e).__name__}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {str(e)}")


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
