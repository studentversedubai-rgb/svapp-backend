# Database Migrations

## Overview

This directory contains database migration files for the StudentVerse backend.

## Migration Strategy

We use **Alembic** for database migrations with Supabase PostgreSQL.

## Setup

### Initialize Alembic (if not already done)
```bash
alembic init migrations
```

### Configure Alembic
Edit `alembic.ini` to point to your Supabase database:
```ini
sqlalchemy.url = postgresql://user:password@host:port/database
```

## Creating Migrations

### Auto-generate migration from models
```bash
alembic revision --autogenerate -m "Description of changes"
```

### Create empty migration
```bash
alembic revision -m "Description of changes"
```

## Applying Migrations

### Upgrade to latest
```bash
alembic upgrade head
```

### Upgrade to specific revision
```bash
alembic upgrade <revision_id>
```

### Downgrade one revision
```bash
alembic downgrade -1
```

## Migration Best Practices

1. **Always review auto-generated migrations** before applying
2. **Test migrations locally** before applying to staging/production
3. **Include both upgrade and downgrade** operations
4. **Keep migrations small and focused** on single changes
5. **Never modify applied migrations** - create new ones instead

## Migration Workflow

### Development
1. Modify models in `app/modules/*/models.py`
2. Generate migration: `alembic revision --autogenerate -m "Add field"`
3. Review generated migration in `migrations/versions/`
4. Apply migration: `alembic upgrade head`
5. Test changes
6. Commit migration file to git

### Staging
1. Pull latest code with migrations
2. Apply migrations: `alembic upgrade head`
3. Verify database schema
4. Test application

### Production
1. **Backup database first**
2. Apply migrations: `alembic upgrade head`
3. Monitor for errors
4. Rollback if needed: `alembic downgrade -1`

## Common Migration Tasks

### Adding a new table
```python
def upgrade():
    op.create_table(
        'table_name',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id')
    )

def downgrade():
    op.drop_table('table_name')
```

### Adding a column
```python
def upgrade():
    op.add_column('users', sa.Column('phone_number', sa.String(), nullable=True))

def downgrade():
    op.drop_column('users', 'phone_number')
```

### Adding an index
```python
def upgrade():
    op.create_index('idx_users_email', 'users', ['email'])

def downgrade():
    op.drop_index('idx_users_email', 'users')
```

## Troubleshooting

### Migration fails
1. Check database connection
2. Review migration SQL
3. Check for conflicting changes
4. Rollback and fix: `alembic downgrade -1`

### Out of sync
```bash
# Stamp current database state
alembic stamp head

# Or start fresh (DANGER: drops all tables)
alembic downgrade base
alembic upgrade head
```

## Initial Schema

The initial migration should create:
- `users` table
- `offers` table
- `entitlements` table
- Necessary indexes and constraints

See `versions/` directory for migration files.

---

**Note**: Always coordinate migrations with team members to avoid conflicts.
