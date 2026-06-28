# StudentVerse Backend API

Production-grade FastAPI backend for the StudentVerse mobile application, providing authentication, offers, QR-based redemption, and AI-powered recommendations.

---

## 🚀 Quick Start

### Prerequisites
- Python 3.11+
- Redis (local or cloud)
- Supabase project

### Installation

```bash
# Clone repository
git clone <repository-url>
cd sv-backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your credentials

# Run server
uvicorn app.main:app --reload --port 8000
```

### Access API Documentation
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

---

## 📋 Environment Variables

Required environment variables (see `.env.example`):

### Core Services
```bash
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_KEY=your-service-role-key
REDIS_URL=redis://localhost:6379
```

### Email (OTP Delivery)
```bash
RESEND_API_KEY=your-resend-api-key
RESEND_FROM=noreply@studentverse.ae
```

### AI Features (Optional)
```bash
OPENROUTER_API_KEY=your-openrouter-key
OPENROUTER_MODEL=google/gemini-2.0-flash-001
```

### Feature Flags
```bash
FEATURE_SV_ORBIT_ENABLED=true
FEATURE_ANALYTICS_ENABLED=true
```

---

## 🏗️ Architecture

### Tech Stack
- **Framework**: FastAPI (Python)
- **Database**: Supabase (PostgreSQL + Auth)
- **Cache**: Redis (Upstash)
- **Email**: Resend
- **AI**: OpenRouter (Gemini)
- **Hosting**: Railway

### Project Structure
```
sv-backend/
├── app/
│   ├── core/              # Core utilities (config, security, DB, Redis)
│   ├── shared/            # Shared schemas, enums, constants
│   └── modules/           # Feature modules
│       ├── auth/          # Authentication & user management
│       ├── offers/        # Offer browsing & search
│       ├── entitlements/  # QR redemption system
│       └── orbit/         # AI recommendations
├── docs/                  # Documentation
├── migrations/            # Database migrations
├── tests/                 # Test suite
└── scripts/               # Utility scripts
```

---

## 📚 API Modules

### 1. Authentication (`/auth`)
- OTP-based email verification
- JWT token management
- User profile management

### 2. Offers (`/offers`)
- Browse active offers
- Search and filter
- Featured offers

### 3. Entitlements (`/entitlements`)
- Claim offers
- Generate QR codes (30s TTL)
- Merchant validation
- Redemption confirmation
- Void logic (2-hour window)

### 4. Orbit AI (`/orbit`)
- AI-powered chat assistant
- Personalized recommendations
- Nearby offers with distance calculation

---

## 🧪 Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=app --cov-report=html

# Run specific test file
pytest tests/test_entitlements.py -v
```

---

## 🚢 Deployment

### Railway (Production)
1. Push to `main` branch
2. Railway auto-deploys
3. Configure environment variables in Railway dashboard

### Environment-Specific Settings
- **Development**: `ENVIRONMENT=development`, `DEBUG=true`
- **Production**: `ENVIRONMENT=production`, `DEBUG=false`

---

## 📖 Documentation

- **[Architecture](docs/architecture.md)**: System design and patterns
- **[API Overview](docs/api-overview.md)**: All endpoints and usage
- **[Redemption Flow](docs/redemption-flow.md)**: QR redemption system details
- **[Phases](docs/phases.md)**: Development roadmap

---

## 🔒 Security

- ✅ JWT-based authentication via Supabase
- ✅ Rate limiting on all endpoints
- ✅ Input validation with Pydantic
- ✅ No hardcoded secrets
- ✅ CORS configuration
- ✅ Row-level security (RLS) in Supabase

---

## 🤝 Contributing

### Code Standards
- Follow PEP 8
- Use type hints
- Write docstrings
- Maintain test coverage >80%

### Branch Strategy
- `main`: Production-ready code
- `develop`: Integration branch
- `feature/*`: New features
- `hotfix/*`: Production fixes

---

## 📞 Support

For questions or issues:
1. Check documentation in `docs/`
2. Review API docs at `/docs`
3. Contact the development team

---

**Built with ❤️ for StudentVerse**
