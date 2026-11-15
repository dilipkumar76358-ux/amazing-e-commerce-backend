from typing import Optional
from supabase import create_client, Client
from app.core.config import settings

_supabase_client: Optional[Client] = None


def get_supabase() -> Optional[Client]:
    """Provides a singleton instance of the Supabase Client."""
    global _supabase_client
    if _supabase_client is None:
        if (
            settings.SUPABASE_URL
            and settings.SUPABASE_ANON_KEY
            and not settings.SUPABASE_URL.startswith("https://placeholder")
        ):
            _supabase_client = create_client(
                settings.SUPABASE_URL,
                settings.SUPABASE_SERVICE_ROLE_KEY or settings.SUPABASE_ANON_KEY
            )
    return _supabase_client
