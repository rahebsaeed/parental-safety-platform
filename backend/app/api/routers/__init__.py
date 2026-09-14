from .health import router as health_router
from .devices import router as devices_router
from .activity import router as activity_router
from .domains import router as domains_router
from .classification import router as classification_router
from .alerts import router as alerts_router
from .analytics import router as analytics_router
from .realtime import router as realtime_router
from .auth import router as auth_router

__all__ = [
    "health_router",
    "devices_router",
    "activity_router",
    "domains_router",
    "classification_router",
    "alerts_router",
    "analytics_router",
    "realtime_router",
    "auth_router",
]
