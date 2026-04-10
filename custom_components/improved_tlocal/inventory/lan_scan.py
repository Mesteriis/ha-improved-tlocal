"""LAN scanning helpers for ImprovedTLocal."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence

from ..const import DEFAULT_SCAN_MAX_CONCURRENCY
from ..models import NetworkEndpoint, utcnow_iso


async def async_scan_open_ports(
    networks: Sequence[str],
    ports: Sequence[int],
    *,
    timeout: float,
    max_concurrency: int = DEFAULT_SCAN_MAX_CONCURRENCY,
    scan_source: str = "tcp_scan",
) -> list[NetworkEndpoint]:
    """Scan the provided networks for open TCP ports."""
    semaphore = asyncio.Semaphore(max_concurrency)
    found: list[NetworkEndpoint] = []

    async def _probe(ip: str, port: int) -> None:
        try:
            async with semaphore:
                _, writer = await asyncio.wait_for(asyncio.open_connection(ip, port), timeout=timeout)
                found.append(
                    NetworkEndpoint(
                        ip=ip,
                        port=port,
                        scan_source=scan_source,
                        last_seen_at=utcnow_iso(),
                    )
                )
                writer.close()
                if hasattr(writer, "wait_closed"):
                    await writer.wait_closed()
        except Exception:
            return

    tasks = []
    for network in networks:
        for host in range(1, 255):
            ip = f"{network}.{host}"
            for port in ports:
                tasks.append(asyncio.create_task(_probe(ip, port)))

    if tasks:
        await asyncio.gather(*tasks)

    found.sort(key=lambda endpoint: (endpoint.ip, endpoint.port))
    return found
