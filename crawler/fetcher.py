import time
import socket
import ssl
import aiohttp


TIMEOUT_SECONDS = 5
AGENT_CARD_PATH = "/.well-known/agent.json"
REQUIRED_FIELDS = {"name", "url"}


async def fetch_agent_card(domain: str) -> dict:
    url = f"https://{domain}{AGENT_CARD_PATH}"
    start = time.monotonic()

    result = {
        "success": False,
        "domain": domain,
        "url": url,
        "status_code": None,
        "response_time_ms": None,
        "card": None,
        "error": None,
        "dns_resolves": True,
        "ssl_valid": True,
    }

    try:
        socket.getaddrinfo(domain, 443)
    except (socket.gaierror, UnicodeError, OSError):
        result["dns_resolves"] = False
        result["error"] = "DNS resolution failed"
        result["response_time_ms"] = int((time.monotonic() - start) * 1000)
        return result

    timeout = aiohttp.ClientTimeout(total=TIMEOUT_SECONDS)

    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, headers={"User-Agent": "Chiwawa-Crawler/0.1"}) as response:
                result["status_code"] = response.status
                result["response_time_ms"] = int((time.monotonic() - start) * 1000)

                if response.status != 200:
                    result["error"] = f"HTTP {response.status}"
                    return result

                try:
                    card = await response.json(content_type=None)
                except Exception:
                    result["error"] = "Invalid JSON response"
                    return result

                missing = REQUIRED_FIELDS - set(card.keys())
                if missing:
                    result["error"] = f"Card missing required fields: {missing}"
                    return result

                result["success"] = True
                result["card"] = card

    except aiohttp.ClientSSLError:
        result["ssl_valid"] = False
        result["error"] = "SSL certificate error"
        result["response_time_ms"] = int((time.monotonic() - start) * 1000)
    except aiohttp.ClientConnectorError as e:
        result["error"] = f"Connection error: {str(e)}"
        result["response_time_ms"] = int((time.monotonic() - start) * 1000)
    except TimeoutError:
        result["error"] = "Request timed out"
        result["response_time_ms"] = int((time.monotonic() - start) * 1000)
    except Exception as e:
        result["error"] = f"Unexpected error: {str(e)}"
        result["response_time_ms"] = int((time.monotonic() - start) * 1000)

    return result
