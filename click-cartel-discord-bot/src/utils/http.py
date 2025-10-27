def get(url, headers=None, params=None):
    import aiohttp
    import asyncio

    async def fetch(session, url):
        async with session.get(url, headers=headers, params=params) as response:
            response.raise_for_status()
            return await response.text()

    async with aiohttp.ClientSession() as session:
        return await fetch(session, url)

def post(url, data, headers=None):
    import aiohttp
    import asyncio

    async def send(session, url, data):
        async with session.post(url, json=data, headers=headers) as response:
            response.raise_for_status()
            return await response.json()

    async with aiohttp.ClientSession() as session:
        return asyncio.run(send(session, url, data))

def handle_rate_limit(response):
    if response.status == 429:
        retry_after = int(response.headers.get("Retry-After", 1))
        asyncio.sleep(retry_after)