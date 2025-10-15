from aiogram import Router

from .handlers import admin, info, onboarding, ping

router = Router(name="root-router")
router.include_router(ping.router)
router.include_router(info.router)
router.include_router(admin.router)
router.include_router(onboarding.router)

__all__ = ["router"]
