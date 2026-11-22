import os
from azure.storage.blob import BlobServiceClient
from dotenv import load_dotenv

load_dotenv()
account_name = os.getenv("AZURE_STORAGE_ACCOUNT_NAME")
account_key = os.getenv("AZURE_STORAGE_ACCOUNT_KEY")
conn_str = f"DefaultEndpointsProtocol=https;AccountName={account_name};AccountKey={account_key};EndpointSuffix=core.windows.net"

service_client = BlobServiceClient.from_connection_string(conn_str)
existing_containers = [c.name for c in service_client.list_containers()]
print("Existing containers:", existing_containers)

required = ["user-verification-documents", "user-profile-images"]
for r in required:
    if r not in existing_containers:
        print(f"Creating container '{r}'...")
        service_client.create_container(r)
        print(f"Container '{r}' created successfully!")
    else:
        print(f"Container '{r}' already exists.")
