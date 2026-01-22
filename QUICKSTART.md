# 🚀 Quick Start Guide

## For Backend Developers

This is a **production-grade backend scaffold** for StudentVerse. All structure is in place - you just need to implement the business logic!

---

## ⚡ 5-Minute Setup

### 1. Install Dependencies
```bash
# Create virtual environment
python -m venv venv

# Activate (Windows)
venv\Scripts\activate

# Activate (Mac/Linux)
source venv/bin/activate

# Install packages
pip install -r requirements.txt
```

### 2. Configure Environment
```bash
# Copy template
copy .env.example .env

# Edit .env and add:
# - SUPABASE_URL
# - SUPABASE_ANON_KEY
# - SUPABASE_SERVICE_KEY
# - REDIS_URL
# - JWT_SECRET
```

### 3. Run Locally
```bash
uvicorn app.main:app --reload --port 8000
```

### 4. View API Docs
```
http://localhost:8000/docs
```

---

## 📖 What to Read First

1. **README.md** - Project overview
2. **STRUCTURE.md** - Complete repository structure
3. **docs/architecture.md** - System architecture
4. **docs/phases.md** - Development phases
5. **docs/api-contracts.md** - API specifications

---

## 🎯 Where to Start

### Developer 1: Start Here
```
1. app/core/config.py - Implement configuration loading
2. app/core/database.py - Set up Supabase connection
3. app/core/redis.py - Set up Redis connection
4. app/modules/auth/service.py - Implement OTP logic
5. app/modules/auth/router.py - Wire up auth endpoints
```

### Developer 2: Start Here
```
1. app/core/security.py - Implement JWT verification
2. app/modules/users/models.py - Define User model
3. app/modules/users/service.py - Implement user CRUD
4. app/modules/users/router.py - Wire up user endpoints
```

---

## 🔧 Key Files to Implement

### Phase 0A (Weeks 1-2)
- [ ] `app/core/config.py` - Load environment variables
- [ ] `app/core/security.py` - JWT verification
- [ ] `app/core/database.py` - Supabase connection
- [ ] `app/core/redis.py` - Redis connection
- [ ] `app/modules/auth/service.py` - OTP send/verify
- [ ] `app/modules/users/service.py` - User CRUD
- [ ] `app/modules/users/models.py` - User model

### Phase 0B (Weeks 3-4)
- [ ] `app/modules/offers/models.py` - Offer model
- [ ] `app/modules/offers/service.py` - Offer logic
- [ ] `app/modules/entitlements/models.py` - Entitlement model
- [ ] `app/modules/entitlements/state_machine.py` - State machine
- [ ] `app/modules/entitlements/service.py` - Entitlement logic
- [ ] `app/modules/validation/service.py` - QR scanning

---

## 🧪 Testing

### Run Tests
```bash
# All tests
pytest

# With coverage
pytest --cov=app --cov-report=html

# Specific test file
pytest tests/unit/test_auth_service.py
```

### Write Tests
```python
# tests/unit/test_auth_service.py
import pytest
from app.modules.auth.service import AuthService

@pytest.mark.asyncio
async def test_validate_email():
    service = AuthService()
    assert await service.validate_university_email("student@uni.edu") == True
```

---

## 📦 Database Migrations

### Create Migration
```bash
alembic revision --autogenerate -m "Add users table"
```

### Apply Migration
```bash
alembic upgrade head
```

### Rollback
```bash
alembic downgrade -1
```

---

## 🚢 Deployment

### Railway Setup
1. Connect GitHub repository
2. Add environment variables in Railway dashboard
3. Push to `main` branch
4. Railway auto-deploys

### Environment Variables
```
SUPABASE_URL=your-project.supabase.co
SUPABASE_ANON_KEY=your-anon-key
SUPABASE_SERVICE_KEY=your-service-key
REDIS_URL=redis://...
JWT_SECRET=your-secret
ALLOWED_EMAIL_DOMAINS=student.university.edu
FEATURE_SV_PAY_ENABLED=false
FEATURE_SV_ORBIT_ENABLED=true
```

---

## 🤝 Team Workflow

### Daily Routine
1. Pull latest changes: `git pull origin develop`
2. Create feature branch: `git checkout -b feature/auth-otp`
3. Implement feature
4. Write tests
5. Commit: `git commit -m "Implement OTP sending"`
6. Push: `git push origin feature/auth-otp`
7. Create PR for review
8. Merge after approval

### Code Review Checklist
- [ ] Type hints added
- [ ] Docstrings written
- [ ] Tests passing
- [ ] No hardcoded values
- [ ] Error handling implemented
- [ ] Logging added

---

## 🐛 Common Issues

### Import Errors
```bash
# Make sure you're in virtual environment
venv\Scripts\activate

# Reinstall dependencies
pip install -r requirements.txt
```

### Database Connection Failed
```bash
# Check .env file has correct Supabase credentials
# Test connection manually
```

### Redis Connection Failed
```bash
# Check Redis is running
# Verify REDIS_URL in .env
```

---

## 📞 Need Help?

1. Check `docs/` folder for detailed documentation
2. Review `STRUCTURE.md` for repository overview
3. Look at placeholder comments in files
4. Ask your teammate!

---

## ✅ Success Criteria

### Phase 0A Complete When:
- ✅ Mobile app can register with OTP
- ✅ Mobile app can login
- ✅ JWT tokens work
- ✅ User profile can be retrieved
- ✅ Deployed to Railway

### Phase 0B Complete When:
- ✅ Students can browse offers
- ✅ Students can claim offers
- ✅ Entitlements created correctly
- ✅ QR codes generated
- ✅ Validators can redeem

---

## 🎉 Let's Build!

You have everything you need to start building. The structure is clean, the documentation is comprehensive, and the path forward is clear.

**Start with Phase 0A and let's ship this! 🚀**

---

**Questions?** Check the docs or ask your teammate!
