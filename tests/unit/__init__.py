"""
Unit Tests

Place unit tests for individual functions and classes here.

Example structure:
tests/unit/
  ├── test_auth_service.py
  ├── test_user_service.py
  ├── test_entitlement_state_machine.py
  └── ...

Example test:

```python
import pytest
from app.modules.auth.service import AuthService

@pytest.mark.asyncio
async def test_validate_university_email():
    service = AuthService()
    
    # Valid university email
    assert await service.validate_university_email("student@university.edu") == True
    
    # Invalid email
    assert await service.validate_university_email("user@gmail.com") == False
```
"""
