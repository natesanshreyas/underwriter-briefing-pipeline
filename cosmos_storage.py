#!/usr/bin/env python3
"""
Cosmos DB Storage Layer for Underwriter Briefings

Stores and retrieves briefings from Azure Cosmos DB.
Partition key: broker_company (for efficient querying by company)
"""

import json
import os
from datetime import datetime
from typing import Optional, List, Dict
from azure.cosmos import CosmosClient, PartitionKey, exceptions
from azure.identity import DefaultAzureCredential


class BriefingStorage:
    """Manages Cosmos DB operations for underwriter briefings."""

    def __init__(self, endpoint: str, database_name: str = "UnderwriterDB", container_name: str = "Briefings"):
        """
        Initialize Cosmos DB client using Managed Identity.

        Args:
            endpoint: Cosmos DB endpoint URL
            database_name: Database name (default: UnderwriterDB)
            container_name: Container name (default: Briefings)
        """
        self.client = CosmosClient(endpoint, credential=DefaultAzureCredential())
        self.database_name = database_name
        self.container_name = container_name
        
        # Initialize database and container
        self.database = self.client.create_database_if_not_exists(id=database_name)
        self.container = self.database.create_container_if_not_exists(
            id=container_name,
            partition_key=PartitionKey(path="/metadata/broker_company")
            # Note: Serverless accounts don't support offer_throughput
        )
    
    def store_briefing(self, briefing_dict: dict) -> dict:
        """
        Store a briefing in Cosmos DB.
        
        Args:
            briefing_dict: Briefing JSON from UnderwriterBriefing.to_dict()
        
        Returns:
            Stored document with id and _etag
        """
        # Add unique ID (email + timestamp)
        if "id" not in briefing_dict:
            email = briefing_dict["metadata"]["broker_email"]
            timestamp = datetime.utcnow().isoformat()
            briefing_dict["id"] = f"{email}_{timestamp}".replace("@", "_").replace(".", "_").replace(":", "_")
        
        # Add storage metadata
        briefing_dict["metadata"]["stored_at"] = datetime.utcnow().isoformat()
        briefing_dict["metadata"]["version"] = "1.0"
        
        try:
            # Upsert (insert or update if exists)
            response = self.container.upsert_item(body=briefing_dict)
            print(f"✅ Stored briefing: {response['id']}")
            return response
        except exceptions.CosmosHttpResponseError as e:
            print(f"❌ Failed to store briefing: {e.message}")
            raise
    
    def get_briefing_by_id(self, briefing_id: str, broker_company: str) -> Optional[dict]:
        """
        Retrieve a briefing by ID.
        
        Args:
            briefing_id: Unique briefing ID
            broker_company: Company name (partition key)
        
        Returns:
            Briefing dict or None if not found
        """
        try:
            item = self.container.read_item(
                item=briefing_id,
                partition_key=broker_company
            )
            return item
        except exceptions.CosmosResourceNotFoundError:
            print(f"⚠️  Briefing not found: {briefing_id}")
            return None
        except exceptions.CosmosHttpResponseError as e:
            print(f"❌ Error retrieving briefing: {e.message}")
            raise
    
    def get_briefings_by_email(self, broker_email: str, limit: int = 10) -> List[dict]:
        """
        Get all briefings for a broker email (most recent first).
        
        Args:
            broker_email: Broker's email address
            limit: Max results to return
        
        Returns:
            List of briefing dicts
        """
        query = f"""
        SELECT * FROM c 
        WHERE c.metadata.broker_email = @email
        ORDER BY c.metadata.stored_at DESC
        OFFSET 0 LIMIT @limit
        """
        
        parameters = [
            {"name": "@email", "value": broker_email},
            {"name": "@limit", "value": limit}
        ]
        
        try:
            items = list(self.container.query_items(
                query=query,
                parameters=parameters,
                enable_cross_partition_query=True
            ))
            return items
        except exceptions.CosmosHttpResponseError as e:
            print(f"❌ Query failed: {e.message}")
            raise
    
    def get_briefings_by_company(self, broker_company: str, limit: int = 10) -> List[dict]:
        """
        Get all briefings for a company (most recent first).
        
        Args:
            broker_company: Company name
            limit: Max results to return
        
        Returns:
            List of briefing dicts
        """
        query = f"""
        SELECT * FROM c 
        WHERE c.metadata.broker_company = @company
        ORDER BY c.metadata.stored_at DESC
        OFFSET 0 LIMIT @limit
        """
        
        parameters = [
            {"name": "@company", "value": broker_company},
            {"name": "@limit", "value": limit}
        ]
        
        try:
            items = list(self.container.query_items(
                query=query,
                parameters=parameters,
                partition_key=broker_company  # More efficient - uses partition key
            ))
            return items
        except exceptions.CosmosHttpResponseError as e:
            print(f"❌ Query failed: {e.message}")
            raise
    
    def search_briefings(self, search_term: str, limit: int = 20) -> List[dict]:
        """
        Search briefings by keyword (across all text fields).
        
        Args:
            search_term: Search keyword
            limit: Max results
        
        Returns:
            List of matching briefings
        """
        # Note: For production, use Azure Cognitive Search for full-text search
        # This is a basic CONTAINS query for demo purposes
        query = f"""
        SELECT * FROM c 
        WHERE CONTAINS(LOWER(c.metadata.broker_email), LOWER(@term))
           OR CONTAINS(LOWER(c.metadata.broker_company), LOWER(@term))
           OR ARRAY_LENGTH(ARRAY(
                SELECT VALUE s 
                FROM s IN c.sections["1_executive_summary"].bullets 
                WHERE CONTAINS(LOWER(s), LOWER(@term))
           )) > 0
        ORDER BY c.metadata.stored_at DESC
        OFFSET 0 LIMIT @limit
        """
        
        parameters = [
            {"name": "@term", "value": search_term},
            {"name": "@limit", "value": limit}
        ]
        
        try:
            items = list(self.container.query_items(
                query=query,
                parameters=parameters,
                enable_cross_partition_query=True
            ))
            return items
        except exceptions.CosmosHttpResponseError as e:
            print(f"❌ Search failed: {e.message}")
            raise
    
    def delete_briefing(self, briefing_id: str, broker_company: str) -> bool:
        """
        Delete a briefing.
        
        Args:
            briefing_id: Unique ID
            broker_company: Company (partition key)
        
        Returns:
            True if deleted, False if not found
        """
        try:
            self.container.delete_item(item=briefing_id, partition_key=broker_company)
            print(f"✅ Deleted briefing: {briefing_id}")
            return True
        except exceptions.CosmosResourceNotFoundError:
            print(f"⚠️  Briefing not found: {briefing_id}")
            return False
        except exceptions.CosmosHttpResponseError as e:
            print(f"❌ Delete failed: {e.message}")
            raise


def get_cosmos_config() -> dict:
    """Load Cosmos DB config from environment or secrets.json."""
    config = {
        "endpoint": os.getenv("COSMOS_ENDPOINT"),
        "database": os.getenv("COSMOS_DATABASE", "UnderwriterDB"),
        "container": os.getenv("COSMOS_CONTAINER", "Briefings"),
    }

    if not config["endpoint"]:
        try:
            with open("secrets.json", "r") as f:
                secrets = json.load(f)
                config["endpoint"] = config["endpoint"] or secrets.get("COSMOS_ENDPOINT")
                config["database"] = config["database"] or secrets.get("COSMOS_DATABASE", "UnderwriterDB")
                config["container"] = config["container"] or secrets.get("COSMOS_CONTAINER", "Briefings")
        except FileNotFoundError:
            pass

    return config


if __name__ == "__main__":
    """Test Cosmos DB connection and basic operations."""
    
    # Load config
    cfg = get_cosmos_config()
    
    if not cfg["endpoint"]:
        print("❌ Cosmos DB endpoint not configured.")
        print("\nAdd to secrets.json:")
        print('  "COSMOS_ENDPOINT": "https://your-cosmos.documents.azure.com:443/"')
        exit(1)

    # Initialize storage
    print(f"🔌 Connecting to Cosmos DB: {cfg['endpoint']}")
    storage = BriefingStorage(
        endpoint=cfg["endpoint"],
        database_name=cfg["database"],
        container_name=cfg["container"]
    )
    
    print("✅ Connected successfully!")
    print(f"📦 Database: {cfg['database']}")
    print(f"📦 Container: {cfg['container']}")
    
    # Test with sample briefing
    sample_briefing = {
        "metadata": {
            "broker_email": "test@example.com",
            "broker_name": "Test Broker",
            "broker_company": "Test Company",
            "thread_size": 1,
        },
        "sections": {
            "1_executive_summary": {
                "bullets": ["Test briefing created"]
            }
        }
    }
    
    print("\n📝 Testing storage...")
    stored = storage.store_briefing(sample_briefing)
    print(f"   ID: {stored['id']}")
    
    print("\n🔍 Testing retrieval...")
    retrieved = storage.get_briefing_by_id(stored['id'], "Test Company")
    if retrieved:
        print(f"   ✅ Retrieved: {retrieved['metadata']['broker_email']}")
    
    print("\n🗑️  Cleaning up test data...")
    storage.delete_briefing(stored['id'], "Test Company")
    
    print("\n✨ Cosmos DB integration ready!")
