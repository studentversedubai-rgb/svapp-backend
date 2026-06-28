"""
Integration Tests

Place integration tests for API endpoints here.

Example structure:
tests/integration/
  ├── test_auth_endpoints.py
  ├── test_offers_endpoints.py
  ├── test_entitlements_endpoints.py
  └── ...

Example test:

```python
import pytest
from fastapi.testclient import TestClient

def test_send_otp(client):
    response = client.post("/api/v1/auth/send-otp", json={
        "email": "test@university.edu"
    })
    
    assert response.status_code == 200
    assert response.json()["success"] == True

def test_get_offers(client, auth_headers):
    response = client.get("/api/v1/offers", headers=auth_headers)
    
    assert response.status_code == 200
    assert "items" in response.json()
```
"""
