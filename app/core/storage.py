"""
Azure Blob Storage Module

Replaces Supabase storage. Uses azure-storage-blob SDK.
Container names come from config (VERIFICATION_BUCKET_NAME, PROFILE_IMAGE_BUCKET_NAME).
"""

import os
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

_ACCOUNT_NAME: str = os.getenv("AZURE_STORAGE_ACCOUNT_NAME", "").strip()
_ACCOUNT_KEY: str = os.getenv("AZURE_STORAGE_ACCOUNT_KEY", "").strip()
_CONTAINER_BASE_URL: str = os.getenv("AZURE_STORAGE_CONTAINER_BASE_URL", "").strip()


def _get_connection_string() -> str:
    """Build and return the Azure Storage connection string. Raises RuntimeError if env vars missing."""
    if not _ACCOUNT_NAME or not _ACCOUNT_KEY:
        raise RuntimeError(
            "AZURE_STORAGE_ACCOUNT_NAME and AZURE_STORAGE_ACCOUNT_KEY must be set "
            "in the environment for Azure Blob Storage operations."
        )
    return (
        f"DefaultEndpointsProtocol=https;"
        f"AccountName={_ACCOUNT_NAME};"
        f"AccountKey={_ACCOUNT_KEY};"
        f"EndpointSuffix=core.windows.net"
    )


def _warn_if_unconfigured() -> None:
    if not _ACCOUNT_NAME or not _ACCOUNT_KEY:
        print(
            "WARNING: AZURE_STORAGE_ACCOUNT_NAME or AZURE_STORAGE_ACCOUNT_KEY is not set. "
            "Blob storage operations will fail at runtime."
        )


_warn_if_unconfigured()


def upload_blob(
    container_name: str,
    blob_path: str,
    data: bytes,
    content_type: str,
) -> str:
    """
    Upload *data* to *blob_path* inside *container_name*.

    Returns the full public URL of the uploaded blob.
    Raises RuntimeError if storage credentials are not configured.
    """
    from azure.storage.blob import BlobServiceClient, ContentSettings

    connection_string = _get_connection_string()
    service_client = BlobServiceClient.from_connection_string(connection_string)
    blob_client = service_client.get_blob_client(container=container_name, blob=blob_path)

    blob_client.upload_blob(
        data,
        overwrite=True,
        content_settings=ContentSettings(content_type=content_type),
    )

    url = get_blob_url(container_name, blob_path)
    print(f"INFO: Uploaded blob to {url}")
    return url


def delete_blob(container_name: str, blob_path: str) -> None:
    """
    Delete *blob_path* from *container_name*.

    Logs a warning if the blob does not exist; does not raise.
    Raises RuntimeError if storage credentials are not configured.
    """
    from azure.storage.blob import BlobServiceClient
    from azure.core.exceptions import ResourceNotFoundError

    connection_string = _get_connection_string()
    service_client = BlobServiceClient.from_connection_string(connection_string)
    blob_client = service_client.get_blob_client(container=container_name, blob=blob_path)

    try:
        blob_client.delete_blob()
        print(f"INFO: Deleted blob {container_name}/{blob_path}")
    except ResourceNotFoundError:
        print(
            f"WARNING: Attempted to delete blob {container_name}/{blob_path} "
            "but it was not found — skipping."
        )


def get_blob_url(container_name: str, blob_path: str) -> str:
    """
    Return the full URL for a blob without making any network call.

    Format: {AZURE_STORAGE_CONTAINER_BASE_URL}/{container_name}/{blob_path}
    """
    base = _CONTAINER_BASE_URL.rstrip("/")
    return f"{base}/{container_name}/{blob_path}"
