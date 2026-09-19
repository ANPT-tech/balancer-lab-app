import argparse
import asyncio
from collections import Counter

import httpx


async def one(client: httpx.AsyncClient, url: str, delay_ms: int) -> str:
    response = await client.get(f"{url.rstrip('/')}/api/async-work", params={"delay_ms": delay_ms})
    response.raise_for_status()
    data = response.json()
    header_node = response.headers.get("X-Backend-Node")
    assert header_node == data["instance_id"]
    return data["instance_id"]


async def main(url: str, count: int) -> None:
    async with httpx.AsyncClient(timeout=10) as client:
        nodes = await asyncio.gather(
            *(one(client, url, 200 + (i % 4) * 100) for i in range(count))
        )

    result = Counter(nodes)
    print(f"URL: {url}")
    print(f"Responses: {count}")
    for node, n in sorted(result.items()):
        print(f"{node}: {n} ({n / count:.1%})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("url", help="Base URL, for example http://localhost")
    parser.add_argument("-n", "--count", type=int, default=20)
    args = parser.parse_args()
    asyncio.run(main(args.url, args.count))
