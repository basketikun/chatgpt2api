from __future__ import annotations

import ipaddress
import mimetypes
import socket
from urllib.parse import ParseResult, urljoin, urlparse

from curl_cffi import requests
from curl_cffi.const import CurlOpt
from fastapi import HTTPException

from services.proxy_service import proxy_settings

DOWNLOAD_CHUNK_BYTES = 64 * 1024
MAX_REDIRECTS = 5


def _limit_label(max_bytes: int) -> str:
    return f"{max(1, max_bytes // (1024 * 1024))}MB"


def _public_target(url: str) -> tuple[ParseResult, list[str]]:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or not parsed.hostname:
        raise HTTPException(status_code=400, detail={"error": "image_url must be an http or https URL"})
    if parsed.username is not None or parsed.password is not None:
        raise HTTPException(status_code=400, detail={"error": "image_url credentials are not allowed"})
    try:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": "image_url has an invalid port"}) from exc

    host = parsed.hostname
    literal_address = False
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        try:
            resolved = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        except OSError as exc:
            raise HTTPException(status_code=400, detail={"error": "image_url host could not be resolved"}) from exc
        addresses = []
        for family, _socktype, _protocol, _canonical_name, sockaddr in resolved:
            if family not in {socket.AF_INET, socket.AF_INET6} or not sockaddr:
                continue
            try:
                address = ipaddress.ip_address(sockaddr[0])
            except ValueError:
                continue
            if address not in addresses:
                addresses.append(address)
    else:
        literal_address = True
        addresses = [literal]

    if not addresses or any(not address.is_global for address in addresses):
        raise HTTPException(status_code=400, detail={"error": "image_url target must use a public IP address"})
    if literal_address:
        return parsed, []

    resolved_addresses = ",".join(
        f"[{address}]" if address.version == 6 else str(address)
        for address in addresses
    )
    return parsed, [f"{host}:{port}:{resolved_addresses}"]


def _response_mime_type(response: requests.Response, parsed_path: str) -> str:
    header_type = str(response.headers.get("content-type") or "").split(";", 1)[0].strip().lower()
    guessed_type = mimetypes.guess_type(parsed_path)[0] or ""
    if header_type.startswith("image/"):
        return header_type
    if header_type and header_type not in {"application/octet-stream", "binary/octet-stream"}:
        raise HTTPException(status_code=400, detail={"error": "image_url must point to an image"})
    if guessed_type.startswith("image/"):
        return guessed_type
    if not header_type or header_type in {"application/octet-stream", "binary/octet-stream"}:
        return "image/png"
    raise HTTPException(status_code=400, detail={"error": "image_url must point to an image"})


def _read_limited(response: requests.Response, max_bytes: int) -> bytes:
    limit_label = _limit_label(max_bytes)
    content_length = str(response.headers.get("content-length") or "").strip()
    if content_length.isdigit() and int(content_length) > max_bytes:
        raise HTTPException(status_code=400, detail={"error": f"image_url exceeds {limit_label} limit"})

    chunks: list[bytes] = []
    total = 0
    for chunk in response.iter_content(chunk_size=DOWNLOAD_CHUNK_BYTES):
        if not chunk:
            continue
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(status_code=400, detail={"error": f"image_url exceeds {limit_label} limit"})
        chunks.append(bytes(chunk))
    data = b"".join(chunks)
    if not data:
        raise HTTPException(status_code=400, detail={"error": "image_url returned empty content"})
    return data


def download_public_image(
    url: str,
    *,
    max_bytes: int,
    timeout_seconds: float,
    user_agent: str,
) -> tuple[bytes, str, str]:
    current_url = str(url or "").strip()
    for redirect_count in range(MAX_REDIRECTS + 1):
        parsed, resolve_entries = _public_target(current_url)
        session_kwargs = proxy_settings.build_session_kwargs(
            resource=True,
            upstream=True,
            verify=True,
        )
        if resolve_entries:
            curl_options = dict(session_kwargs.pop("curl_options", {}) or {})
            curl_options[CurlOpt.RESOLVE] = resolve_entries
            session_kwargs["curl_options"] = curl_options
        session = requests.Session(**session_kwargs)
        response = None
        try:
            response = session.get(
                current_url,
                headers={"Accept": "image/*,*/*;q=0.8", "User-Agent": user_agent},
                timeout=timeout_seconds,
                allow_redirects=False,
                stream=True,
            )
            if response.status_code in {301, 302, 303, 307, 308}:
                if redirect_count >= MAX_REDIRECTS:
                    raise HTTPException(status_code=400, detail={"error": "image_url has too many redirects"})
                location = str(response.headers.get("location") or "").strip()
                if not location:
                    raise HTTPException(status_code=400, detail={"error": "image_url redirect has no location"})
                current_url = urljoin(current_url, location)
                continue
            if not 200 <= response.status_code < 300:
                raise HTTPException(
                    status_code=400,
                    detail={"error": f"image_url fetch failed: HTTP {response.status_code}"},
                )
            data = _read_limited(response, max(1, int(max_bytes)))
            return data, parsed.path, _response_mime_type(response, parsed.path)
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=400, detail={"error": f"image_url fetch failed: {exc}"}) from exc
        finally:
            if response is not None:
                try:
                    response.close()
                except Exception:
                    pass
            try:
                session.close()
            except Exception:
                pass
    raise HTTPException(status_code=400, detail={"error": "image_url has too many redirects"})
