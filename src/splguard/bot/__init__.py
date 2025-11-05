from aiogram import Router

from .handlers import admin, info, onboarding, ping, zealy

router = Router(name="root-router")
router.include_router(ping.router)
router.include_router(info.router)
router.include_router(admin.router)
router.include_router(onboarding.router)
router.include_router(zealy.router)

__all__ = ["router"]
