# StudentVerse Backend

## Overview

Production-grade backend for the StudentVerse mobile application (iOS & Android, built with React Native). This repository serves as the central API layer for all StudentVerse services including authentication, offers, entitlements, SV Orbit (AI planner), and SV Pay (payments).

## Tech Stack

- **Framework**: FastAPI (Python)
- **Database**: Supabase (PostgreSQL + Auth)
- **Cache/Session**: Redis
- **Hosting**: Railway
- **Authentication**: Supabase Auth (JWT-based, mobile-optimized)

## Key Architectural Principles

### Authentication Rules
- **Supabase Auth** handles all password management and JWT issuance
- User email is **immutable** and must be a **university email**
- Mobile app uses **persistent login** with JWT refresh tokens
- Backend verifies JWTs but does NOT store passwords

### Repository Structure
- **Single monorepo** for all backend services
- **Domain-driven modules** for clean separation of concerns
- **Feature flags** for SV Pay and future features
- **Investor-grade** code quality and documentation

## Development Phases

### Phase 0A: Foundation
- Auth flow (OTP + registration)
- User profiles
- Basic offer listing

### Phase 0B: Core Features
- Entitlements system
- State machine for redemption flow
- Validator PWA integration

### Phase 1: SV Orbit (AI Planner)
- Partner-only retrieval (no hallucinations)
- Scoring and orchestration
- LLM-powered presentation layer

### Phase 1.5: Analytics & Insights
- Usage tracking
- Partner analytics
- User behavior insights

### Phase 2: SV Pay (Feature Flagged)
- Payment processing (disabled by default)
- PSP/issuer abstraction
- Transaction management

## Project Structure

```
studentverse-backend/
├── app/                    # Main FastAPI application
│   ├── core/              # Core utilities (config, security, DB, Redis)
│   ├── shared/            # Shared schemas, enums, utils
│   └── modules/           # Domain modules (auth, users, offers, etc.)
├── migrations/            # Database migrations
├── tests/                 # Unit, integration, and E2E tests
├── docs/                  # Architecture and API documentation
├── scripts/               # Utility scripts
├── Dockerfile             # Container configuration
├── railway.toml           # Railway deployment config
├── requirements.txt       # Python dependencies
├── .env.example           # Environment variables template
└── .gitignore            # Git ignore rules
```

## Team Collaboration

### For Backend Developers

1. **Branch Strategy**
   - `main`: Production-ready code
   - `develop`: Integration branch
   - `feature/*`: Individual features
   - `hotfix/*`: Production fixes

2. **Module Ownership**
   - Each developer can own specific modules
   - Use clear PR descriptions
   - Tag teammates for cross-module changes

3. **Code Standards**
   - Follow PEP 8 for Python
   - Use type hints everywhere
   - Write docstrings for all public functions
   - Keep modules isolated (minimal cross-dependencies)

4. **Testing Requirements**
   - Unit tests for all services
   - Integration tests for API endpoints
   - Maintain >80% code coverage

## Local Development Setup

### Prerequisites
```bash
# Python 3.11+
# Redis (local or Docker)
# Supabase project credentials
```

### Installation
```bash
# Clone repository
git clone <repository-url>
cd studentverse-backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy environment template
cp .env.example .env
# Edit .env with your credentials

# Run migrations
# [Migration command placeholder]

# Start development server
uvicorn app.main:app --reload --port 8000
```

### Environment Variables
See `.env.example` for required configuration:
- Supabase URL and keys
- Redis connection string
- JWT secret
- Feature flags
- Railway deployment settings

## API Documentation

Once running, access:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## Deployment

Deployment is automated via Railway:
1. Push to `main` branch
2. Railway automatically builds and deploys
3. Environment variables managed in Railway dashboard

## Documentation

See `docs/` folder for detailed documentation:
- `architecture.md`: System architecture and design decisions
- `auth-flow.md`: Mobile authentication flow
- `phases.md`: Detailed phase breakdown
- `api-contracts.md`: Frontend-backend API agreements
- `decisions.md`: Architectural Decision Records (ADRs)

## Support

For questions or issues:
1. Check documentation in `docs/`
2. Review existing issues/PRs
3. Contact team leads

---

**Built with ❤️ for StudentVerse**
