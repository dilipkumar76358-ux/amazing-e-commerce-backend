from fastapi import APIRouter
from app.core.config import settings

router = APIRouter()


@router.get("/health", tags=["Health"])
async def health_check():
    supabase_configured = bool(
        settings.SUPABASE_URL
        and not settings.SUPABASE_URL.startswith("https://placeholder")
    )
    return {
        "status": "healthy",
        "service": "amazing-e-commerce-backend",
        "version": "1.0.0",
        "phase": "Phase 1 - Database & Environment",
        "database": {
            "supabase_configured": supabase_configured,
            "supabase_url": settings.SUPABASE_URL if supabase_configured else "not_configured"
        }
    }
