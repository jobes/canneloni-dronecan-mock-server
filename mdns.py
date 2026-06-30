import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from zeroconf import ServiceInfo
from zeroconf.asyncio import AsyncZeroconf

logger = logging.getLogger(__name__)


@asynccontextmanager
async def mdns_service(service_info: ServiceInfo) -> AsyncIterator[None]:
    """Async context manager that registers an mDNS service and cleans up on exit."""
    azc = AsyncZeroconf()
    await azc.async_register_service(service_info)
    logger.debug('mDNS service registered: %s', service_info.name)
    try:
        yield
    finally:
        await azc.async_unregister_service(service_info)
        await azc.async_close()
        logger.debug('mDNS service unregistered: %s', service_info.name)
