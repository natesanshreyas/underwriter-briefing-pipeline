#!/usr/bin/env python3
"""
Delta Token Store - persists Graph delta query tokens per mailbox
in Azure Blob Storage so they survive pod restarts.
"""

import json
import logging
from typing import Optional

from azure.storage.blob import BlobServiceClient
from azure.core.exceptions import ResourceNotFoundError

logger = logging.getLogger("delta_token_store")

CONTAINER_NAME = "delta-tokens"


class DeltaTokenStore:
    def __init__(self, connection_string: str):
        self._client = BlobServiceClient.from_connection_string(connection_string)
        self._container = self._client.get_container_client(CONTAINER_NAME)
        self._ensure_container()

    def _ensure_container(self) -> None:
        try:
            self._container.create_container()
            logger.info("Created blob container: %s", CONTAINER_NAME)
        except Exception:
            pass  # Already exists

    def get(self, mailbox_id: str) -> Optional[str]:
        """Return the stored delta token for a mailbox, or None."""
        blob = self._container.get_blob_client(f"{mailbox_id}.json")
        try:
            data = json.loads(blob.download_blob().readall())
            return data.get("deltaToken")
        except ResourceNotFoundError:
            return None
        except Exception as exc:
            logger.warning("Could not read delta token for %s: %s", mailbox_id, exc)
            return None

    def set(self, mailbox_id: str, delta_token: str) -> None:
        """Persist the delta token for a mailbox."""
        blob = self._container.get_blob_client(f"{mailbox_id}.json")
        blob.upload_blob(
            json.dumps({"deltaToken": delta_token, "mailboxId": mailbox_id}),
            overwrite=True,
        )
        logger.debug("Saved delta token for mailbox %s", mailbox_id)
