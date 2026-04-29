#!/usr/bin/env python3
"""
Batch Job Orchestrator - Runs on schedule (2x daily) via ACA Jobs

Fetches new emails from Outlook, generates underwriter briefings, stores in Cosmos DB.
Designed to run as a scheduled container in Azure Container Apps.

Usage:
  python batch_job_orchestrator.py

Expects environment variables:
  - OUTLOOK_MAIL_FOLDER: "INBOX" or folder name
  - OUTLOOK_BATCH_SIZE: emails to process per run (default: 10)
  - LANGUAGE_ENDPOINT: Azure Language Service endpoint
  - OPENAI_ENDPOINT: Azure OpenAI endpoint
  - COSMOS_ENDPOINT: Cosmos DB endpoint
  - GRAPH_TENANT_ID, GRAPH_CLIENT_ID, GRAPH_CLIENT_SECRET: Microsoft Graph API
  Authentication to Language Service, OpenAI, and Cosmos DB is via Managed Identity.
"""

import os
import sys
import json
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import core modules
try:
    from underwriter_briefing import BriefingGenerator
    from cosmos_storage import BriefingStorage
    from azure.ai.textanalytics import TextAnalyticsClient
    from azure.identity import DefaultAzureCredential, get_bearer_token_provider
    from openai import AzureOpenAI
except ImportError as e:
    logger.error(f"Failed to import required modules: {e}")
    sys.exit(1)


class BatchJobOrchestrator:
    """Orchestrates the batch processing of emails to briefings."""

    def __init__(self):
        """Initialize batch job with Azure clients."""
        self.config = self._load_config()
        self._validate_config()

        credential = DefaultAzureCredential()

        self.language_client = TextAnalyticsClient(
            endpoint=self.config["LANGUAGE_ENDPOINT"],
            credential=credential
        )

        self.openai_client = AzureOpenAI(
            azure_ad_token_provider=get_bearer_token_provider(
                credential, "https://cognitiveservices.azure.com/.default"
            ),
            api_version=self.config.get("OPENAI_API_VERSION", "2024-02-15-preview"),
            azure_endpoint=self.config["OPENAI_ENDPOINT"]
        )

        self.cosmos_storage = BriefingStorage(
            endpoint=self.config["COSMOS_ENDPOINT"],
            database_name=self.config.get("COSMOS_DATABASE", "UnderwriterDB"),
            container_name=self.config.get("COSMOS_CONTAINER", "Briefings")
        )
        
        self.briefing_generator = BriefingGenerator(self.language_client)
        
        logger.info("✅ Batch job orchestrator initialized")
    
    def _load_config(self) -> Dict[str, str]:
        """Load configuration from environment variables or secrets.json."""
        config = {}
        
        required_keys = [
            "LANGUAGE_ENDPOINT",
            "OPENAI_ENDPOINT",
            "COSMOS_ENDPOINT",
            "GRAPH_TENANT_ID", "GRAPH_CLIENT_ID", "GRAPH_CLIENT_SECRET"
        ]

        for key in required_keys:
            config[key] = os.getenv(key)

        if not all(config.values()):
            try:
                with open("secrets.json", "r") as f:
                    secrets = json.load(f)
                    for key in required_keys:
                        if not config[key]:
                            config[key] = secrets.get(key)
            except FileNotFoundError:
                pass
        
        # Optional configs with defaults
        config["OUTLOOK_MAIL_FOLDER"] = os.getenv("OUTLOOK_MAIL_FOLDER", "INBOX")
        config["OUTLOOK_BATCH_SIZE"] = int(os.getenv("OUTLOOK_BATCH_SIZE", "10"))
        config["OPENAI_MODEL"] = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        config["OPENAI_API_VERSION"] = os.getenv("OPENAI_API_VERSION", "2024-02-15-preview")
        config["COSMOS_DATABASE"] = os.getenv("COSMOS_DATABASE", "UnderwriterDB")
        config["COSMOS_CONTAINER"] = os.getenv("COSMOS_CONTAINER", "Briefings")
        
        return config
    
    def _validate_config(self) -> None:
        """Validate that all required configuration is present."""
        required = [
            "LANGUAGE_ENDPOINT",
            "OPENAI_ENDPOINT",
            "COSMOS_ENDPOINT",
            "GRAPH_TENANT_ID", "GRAPH_CLIENT_ID", "GRAPH_CLIENT_SECRET"
        ]
        
        missing = [k for k in required if not self.config.get(k)]
        if missing:
            logger.error(f"❌ Missing required configuration: {', '.join(missing)}")
            raise ValueError(f"Missing config: {missing}")
        
        logger.info("✅ All required configuration present")
    
    def fetch_emails_from_outlook(self) -> List[Dict[str, Any]]:
        """
        Fetch recent emails from Outlook via Microsoft Graph API.
        
        Returns:
            List of email dictionaries with: id, subject, sender, body, received_date_time
        """
        logger.info(f"📧 Fetching emails from Outlook ({self.config['OUTLOOK_MAIL_FOLDER']})...")
        
        try:
            # Import Graph API helper
            from examples_outlook import OutlookEmailFetcher
            
            fetcher = OutlookEmailFetcher(
                tenant_id=self.config["GRAPH_TENANT_ID"],
                client_id=self.config["GRAPH_CLIENT_ID"],
                client_secret=self.config["GRAPH_CLIENT_SECRET"]
            )
            
            # Fetch unread emails (or recent if none unread)
            emails = fetcher.fetch_recent_emails(
                folder=self.config["OUTLOOK_MAIL_FOLDER"],
                limit=self.config["OUTLOOK_BATCH_SIZE"],
                unread_only=True  # Only process unread to avoid duplicates
            )
            
            logger.info(f"   Found {len(emails)} emails to process")
            return emails
            
        except Exception as e:
            logger.error(f"❌ Failed to fetch emails: {e}")
            return []
    
    def process_email_to_briefing(self, email: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Convert a single email to an underwriter briefing.
        
        Args:
            email: Email dict with id, subject, sender, body, received_date_time
        
        Returns:
            Briefing dict ready for Cosmos DB storage, or None if processing failed
        """
        try:
            logger.info(f"   Processing: {email.get('subject', 'No Subject')}")
            
            # Extract email fields
            broker_email = email.get("sender", {}).get("emailAddress", {}).get("address", "unknown@unknown.com")
            sender_name = email.get("sender", {}).get("emailAddress", {}).get("name", "Unknown")
            sender_company = email.get("sender", {}).get("emailAddress", {}).get("name", "").split("@")[-1] if "@" in broker_email else "Unknown"
            
            # Generate briefing
            briefing = self.briefing_generator.generate_briefing(
                broker_email=broker_email,
                body_text=email.get("bodyPreview", email.get("body", "")),
                subject=email.get("subject", "No Subject"),
                sender_name=sender_name,
                sender_company=sender_company
            )
            
            # Optional: Enhance with LLM
            try:
                briefing = self.briefing_generator.generate_narrative_wrapper(
                    briefing,
                    self.openai_client,
                    model=self.config["OPENAI_MODEL"]
                )
                logger.info(f"      ✅ Enhanced with {self.config['OPENAI_MODEL']}")
            except Exception as e:
                logger.warning(f"      ⚠️  LLM enhancement skipped: {e}")
            
            return briefing.to_dict()
            
        except Exception as e:
            logger.error(f"   ❌ Failed to process email: {e}")
            return None
    
    def store_briefing(self, briefing_dict: Dict[str, Any]) -> bool:
        """Store a briefing in Cosmos DB."""
        try:
            stored = self.cosmos_storage.store_briefing(briefing_dict)
            logger.info(f"      ✅ Stored in Cosmos DB: {stored.get('id')}")
            return True
        except Exception as e:
            logger.error(f"      ❌ Failed to store in Cosmos DB: {e}")
            return False
    
    def run(self) -> Dict[str, Any]:
        """Execute the batch job."""
        logger.info("\n" + "="*70)
        logger.info("BATCH JOB STARTED")
        logger.info(f"Time: {datetime.now().isoformat()}")
        logger.info("="*70)
        
        stats = {
            "emails_fetched": 0,
            "briefings_generated": 0,
            "briefings_stored": 0,
            "errors": 0,
            "start_time": datetime.now().isoformat(),
        }
        
        # Step 1: Fetch emails
        emails = self.fetch_emails_from_outlook()
        stats["emails_fetched"] = len(emails)
        
        if not emails:
            logger.warning("⚠️  No emails to process")
            stats["end_time"] = datetime.now().isoformat()
            return stats
        
        # Step 2: Process each email to briefing
        for email in emails:
            briefing_dict = self.process_email_to_briefing(email)
            
            if briefing_dict:
                stats["briefings_generated"] += 1
                
                # Step 3: Store in Cosmos DB
                if self.store_briefing(briefing_dict):
                    stats["briefings_stored"] += 1
                else:
                    stats["errors"] += 1
            else:
                stats["errors"] += 1
        
        # Summary
        logger.info("\n" + "="*70)
        logger.info("BATCH JOB COMPLETED")
        logger.info(f"  📧 Emails processed: {stats['emails_fetched']}")
        logger.info(f"  📄 Briefings generated: {stats['briefings_generated']}")
        logger.info(f"  💾 Briefings stored: {stats['briefings_stored']}")
        logger.info(f"  ❌ Errors: {stats['errors']}")
        logger.info("="*70 + "\n")
        
        stats["end_time"] = datetime.now().isoformat()
        return stats


def main():
    """Entry point for batch job."""
    try:
        orchestrator = BatchJobOrchestrator()
        stats = orchestrator.run()
        
        # Exit with success/failure code
        if stats["errors"] == 0 and stats["briefings_stored"] > 0:
            logger.info("✅ Batch job succeeded")
            sys.exit(0)
        elif stats["briefings_stored"] > 0:
            logger.warning("⚠️  Batch job completed with errors")
            sys.exit(0)  # Still exit 0 if we processed something
        else:
            logger.error("❌ Batch job failed")
            sys.exit(1)
    
    except Exception as e:
        logger.error(f"❌ Batch job failed with exception: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
