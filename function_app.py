"""
Azure Function App - Underwriter Briefing API

Exposes HTTP endpoints for retrieving briefings from Cosmos DB.
Integrates with Copilot Studio via Power Automate.
"""

import azure.functions as func
import json
import logging
from cosmos_storage import BriefingStorage, get_cosmos_config

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)


@app.route(route="GetBriefing", methods=["GET"])
def get_briefing(req: func.HttpRequest) -> func.HttpResponse:
    """
    Get a specific briefing by ID.
    
    Query params:
        id: Briefing ID (required)
        company: Broker company (required, partition key)
    
    Example:
        GET /api/GetBriefing?id=test_example_com_2026-01-31&company=Acme
    """
    logging.info('GetBriefing function triggered')
    
    try:
        # Get params
        briefing_id = req.params.get('id')
        company = req.params.get('company')
        
        if not briefing_id or not company:
            return func.HttpResponse(
                json.dumps({
                    "error": "Missing required parameters: 'id' and 'company'"
                }),
                status_code=400,
                mimetype="application/json"
            )
        
        # Initialize storage
        cfg = get_cosmos_config()
        storage = BriefingStorage(
            endpoint=cfg["endpoint"],
            key=cfg["key"],
            database_name=cfg["database"],
            container_name=cfg["container"]
        )
        
        # Retrieve briefing
        briefing = storage.get_briefing_by_id(briefing_id, company)
        
        if briefing:
            return func.HttpResponse(
                json.dumps(briefing, default=str),
                status_code=200,
                mimetype="application/json"
            )
        else:
            return func.HttpResponse(
                json.dumps({"error": "Briefing not found"}),
                status_code=404,
                mimetype="application/json"
            )
    
    except Exception as e:
        logging.error(f"Error in GetBriefing: {str(e)}")
        return func.HttpResponse(
            json.dumps({"error": str(e)}),
            status_code=500,
            mimetype="application/json"
        )


@app.route(route="GetBriefingsByEmail", methods=["GET"])
def get_briefings_by_email(req: func.HttpRequest) -> func.HttpResponse:
    """
    Get all briefings for a broker email.
    
    Query params:
        email: Broker email (required)
        limit: Max results (optional, default 10)
    
    Example:
        GET /api/GetBriefingsByEmail?email=broker@company.com&limit=5
    """
    logging.info('GetBriefingsByEmail function triggered')
    
    try:
        # Get params
        email = req.params.get('email')
        limit = int(req.params.get('limit', 10))
        
        if not email:
            return func.HttpResponse(
                json.dumps({"error": "Missing required parameter: 'email'"}),
                status_code=400,
                mimetype="application/json"
            )
        
        # Initialize storage
        cfg = get_cosmos_config()
        storage = BriefingStorage(
            endpoint=cfg["endpoint"],
            key=cfg["key"],
            database_name=cfg["database"],
            container_name=cfg["container"]
        )
        
        # Query briefings
        briefings = storage.get_briefings_by_email(email, limit)
        
        return func.HttpResponse(
            json.dumps({
                "count": len(briefings),
                "briefings": briefings
            }, default=str),
            status_code=200,
            mimetype="application/json"
        )
    
    except Exception as e:
        logging.error(f"Error in GetBriefingsByEmail: {str(e)}")
        return func.HttpResponse(
            json.dumps({"error": str(e)}),
            status_code=500,
            mimetype="application/json"
        )


@app.route(route="GetBriefingsByCompany", methods=["GET"])
def get_briefings_by_company(req: func.HttpRequest) -> func.HttpResponse:
    """
    Get all briefings for a company.
    
    Query params:
        company: Broker company (required)
        limit: Max results (optional, default 10)
    
    Example:
        GET /api/GetBriefingsByCompany?company=Acme%20Manufacturing&limit=20
    """
    logging.info('GetBriefingsByCompany function triggered')
    
    try:
        # Get params
        company = req.params.get('company')
        limit = int(req.params.get('limit', 10))
        
        if not company:
            return func.HttpResponse(
                json.dumps({"error": "Missing required parameter: 'company'"}),
                status_code=400,
                mimetype="application/json"
            )
        
        # Initialize storage
        cfg = get_cosmos_config()
        storage = BriefingStorage(
            endpoint=cfg["endpoint"],
            key=cfg["key"],
            database_name=cfg["database"],
            container_name=cfg["container"]
        )
        
        # Query briefings
        briefings = storage.get_briefings_by_company(company, limit)
        
        return func.HttpResponse(
            json.dumps({
                "count": len(briefings),
                "company": company,
                "briefings": briefings
            }, default=str),
            status_code=200,
            mimetype="application/json"
        )
    
    except Exception as e:
        logging.error(f"Error in GetBriefingsByCompany: {str(e)}")
        return func.HttpResponse(
            json.dumps({"error": str(e)}),
            status_code=500,
            mimetype="application/json"
        )


@app.route(route="SearchBriefings", methods=["GET"])
def search_briefings(req: func.HttpRequest) -> func.HttpResponse:
    """
    Search briefings by keyword.
    
    Query params:
        q: Search query (required)
        limit: Max results (optional, default 20)
    
    Example:
        GET /api/SearchBriefings?q=renewal&limit=10
    """
    logging.info('SearchBriefings function triggered')
    
    try:
        # Get params
        query = req.params.get('q')
        limit = int(req.params.get('limit', 20))
        
        if not query:
            return func.HttpResponse(
                json.dumps({"error": "Missing required parameter: 'q' (search query)"}),
                status_code=400,
                mimetype="application/json"
            )
        
        # Initialize storage
        cfg = get_cosmos_config()
        storage = BriefingStorage(
            endpoint=cfg["endpoint"],
            key=cfg["key"],
            database_name=cfg["database"],
            container_name=cfg["container"]
        )
        
        # Search
        briefings = storage.search_briefings(query, limit)
        
        return func.HttpResponse(
            json.dumps({
                "query": query,
                "count": len(briefings),
                "briefings": briefings
            }, default=str),
            status_code=200,
            mimetype="application/json"
        )
    
    except Exception as e:
        logging.error(f"Error in SearchBriefings: {str(e)}")
        return func.HttpResponse(
            json.dumps({"error": str(e)}),
            status_code=500,
            mimetype="application/json"
        )


@app.route(route="ProcessEmail", methods=["POST"])
def process_email(req: func.HttpRequest) -> func.HttpResponse:
    """
    Process a new email and generate briefing.
    
    Request body (JSON):
    {
        "email": "broker@company.com",
        "name": "Broker Name",
        "company": "Company Name",
        "subject": "Email subject",
        "body": "Email body text"
    }
    
    Returns: Generated briefing JSON
    """
    logging.info('ProcessEmail function triggered')
    
    try:
        # Parse request
        req_body = req.get_json()
        
        email = req_body.get('email')
        name = req_body.get('name', 'Unknown')
        company = req_body.get('company', 'Unknown')
        subject = req_body.get('subject', 'No subject')
        body = req_body.get('body')
        
        if not email or not body:
            return func.HttpResponse(
                json.dumps({"error": "Missing required fields: 'email' and 'body'"}),
                status_code=400,
                mimetype="application/json"
            )
        
        # Generate briefing (import here to avoid cold start)
        from underwriter_briefing import BriefingGenerator, get_config
        from azure.ai.textanalytics import TextAnalyticsClient
        from azure.identity import DefaultAzureCredential, get_bearer_token_provider
        from openai import AzureOpenAI

        # Get config
        cfg = get_config()
        credential = DefaultAzureCredential()

        # Create Language client
        language_client = TextAnalyticsClient(
            endpoint=cfg["LANGUAGE_ENDPOINT"],
            credential=credential
        )

        # Generate briefing
        generator = BriefingGenerator(language_client)
        briefing = generator.generate_briefing(
            broker_email=email,
            body_text=body,
            subject=subject,
            sender_name=name,
            sender_company=company
        )

        # Optional: LLM enhancement
        if cfg.get("OPENAI_ENDPOINT"):
            try:
                openai_client = AzureOpenAI(
                    azure_ad_token_provider=get_bearer_token_provider(
                        credential, "https://cognitiveservices.azure.com/.default"
                    ),
                    api_version="2024-02-15-preview",
                    azure_endpoint=cfg["OPENAI_ENDPOINT"]
                )
                briefing = generator.generate_narrative_wrapper(
                    briefing,
                    openai_client,
                    model=cfg.get("OPENAI_MODEL", "gpt-4o-mini")
                )
            except:
                logging.warning("LLM enhancement skipped")

        # Store in Cosmos DB
        cosmos_cfg = get_cosmos_config()
        storage = BriefingStorage(
            endpoint=cosmos_cfg["endpoint"],
            database_name=cosmos_cfg["database"],
            container_name=cosmos_cfg["container"]
        )
        
        briefing_dict = briefing.to_dict()
        stored = storage.store_briefing(briefing_dict)
        
        return func.HttpResponse(
            json.dumps({
                "status": "success",
                "briefing_id": stored['id'],
                "briefing": briefing_dict
            }, default=str),
            status_code=200,
            mimetype="application/json"
        )
    
    except Exception as e:
        logging.error(f"Error in ProcessEmail: {str(e)}")
        return func.HttpResponse(
            json.dumps({"error": str(e)}),
            status_code=500,
            mimetype="application/json"
        )
