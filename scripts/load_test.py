"""Tiny async load test: python scripts/load_test.py URL API_KEY [requests] [concurrency]."""

import asyncio
import statistics
import sys
import time

import httpx


async def main(url: str, key: str, n: int, conc: int) -> None:
    sem = asyncio.Semaphore(conc)
    lat: list[float] = []
    codes: dict[int, int] = {}

    async with httpx.AsyncClient(headers={"X-API-Key": key}, timeout=30) as client:

        async def one():
            async with sem:
                t = time.perf_counter()
                r = await client.get(url)
                lat.append(time.perf_counter() - t)
                codes[r.status_code] = codes.get(r.status_code, 0) + 1

        t0 = time.perf_counter()
        await asyncio.gather(*(one() for _ in range(n)))
        wall = time.perf_counter() - t0

    lat.sort()
    q = lambda p: lat[min(len(lat) - 1, int(p * len(lat)))] * 1000  # noqa: E731
    print(f"requests={n} concurrency={conc} wall={wall:.2f}s rps={n / wall:.1f}")
    print(
        f"latency ms: p50={q(0.5):.1f} p95={q(0.95):.1f} p99={q(0.99):.1f} max={lat[-1] * 1000:.1f}"
    )
    print(f"status codes: {codes} mean={statistics.mean(lat) * 1000:.1f}ms")


if __name__ == "__main__":
    a = sys.argv
    asyncio.run(main(a[1], a[2], int(a[3]) if len(a) > 3 else 200, int(a[4]) if len(a) > 4 else 10))
