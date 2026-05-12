from supabase import create_client, Client
from app.config import settings

_client: Client | None = None


def get_supabase_client() -> Client | None:
    global _client
    if _client is not None:
        return _client
    if settings.supabase_url and settings.supabase_service_role_key:
        try:
            _client = create_client(settings.supabase_url, settings.supabase_service_role_key)
            return _client
        except Exception:
            return None
    return None


async def check_supabase_connected() -> bool:
    client = get_supabase_client()
    if not client:
        return False
    try:
        client.table("projects").select("id", count="exact").limit(1).execute()
        return True
    except Exception:
        return False
