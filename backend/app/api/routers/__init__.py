from .health import router as health_router
from .devices import router as devices_router
from .activity import router as activity_router
from .domains import router as domains_router
from .domain_security import router as domain_security_router
from .classification import router as classification_router
from .alerts import router as alerts_router
from .analytics import router as analytics_router
from .realtime import router as realtime_router
from .auth import router as auth_router
from .router_dns import router as router_dns_router
from .openrouter import router as openrouter_router

__all__ = [
    "health_router", "devices_router", "activity_router",
    "domains_router", "domain_security_router",
    "classification_router", "alerts_router",
    "analytics_router", "realtime_router", "auth_router",
    "router_dns_router", "openrouter_router",
]
