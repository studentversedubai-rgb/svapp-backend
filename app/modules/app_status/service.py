"""
App Status Service

Reads the single-row app_status table. Writes happen on the dashboard side
via the Supabase service-role key, so this module only exposes a read path.
"""

import logging
from app.core.database import get_supabase_client
from app.core.redis import redis_manager
from app.modules.app_status.schemas import AppStatus

logger = logging.getLogger(__name__)


_DEFAULT = AppStatus(mode='normal')
_BAITNA_VISIBILITY_KEY = 'sv:app:feature:baitna_visible'


def get_baitna_visibility() -> bool:
    return redis_manager.get(_BAITNA_VISIBILITY_KEY) != 'false'


def set_baitna_visibility(visible: bool) -> bool:
    return redis_manager.set(_BAITNA_VISIBILITY_KEY, 'true' if visible else 'false')


def _with_baitna_visibility(status: AppStatus) -> AppStatus:
    return status.model_copy(update={'baitna_visible': get_baitna_visibility()})


async def get_app_status() -> AppStatus:
    """Return the current app status, falling back to a safe default if unreachable."""
    supabase = get_supabase_client()
    if supabase is None:
        logger.warning("Supabase client unavailable; returning default app_status")
        return _with_baitna_visibility(_DEFAULT)

    try:
        res = (
            supabase.table('app_status')
            .select('*')
            .eq('singleton', True)
            .limit(1)
            .execute()
        )
        rows = res.data or []
        if not rows:
            return _with_baitna_visibility(_DEFAULT)
        return _with_baitna_visibility(AppStatus(**rows[0]))
    except Exception as exc:
        logger.error(f"Failed to read app_status: {exc}")
        return _with_baitna_visibility(_DEFAULT)
