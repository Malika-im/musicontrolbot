"""
Security and validation utilities.
Includes webhook secret verification and SSRF-safe URL validation.
"""

import hmac
import ipaddress
import socket
from urllib.parse import urlparse
from app.core.exceptions import SSRFSecurityError
from app.core.logging import logger


def verify_webhook_secret(received_secret: str | None, expected_secret: str) -> bool:
    """
    Perform a constant-time comparison of the Telegram webhook secret token.
    Prevents timing attacks.
    """
    if not received_secret or not expected_secret:
        return False
    return hmac.compare_digest(received_secret, expected_secret)


def validate_safe_url(url: str) -> str:
    """
    Validate that an external download URL is safe and does not target internal IP addresses (SSRF).
    Only allows http/https schemes on public IP addresses.
    """
    try:
        parsed = urlparse(url)
    except Exception as exc:
        raise SSRFSecurityError(f"Некорректный формат URL: {exc}", "Некорректная ссылка на аудио.")

    if parsed.scheme.lower() not in ("http", "https"):
        raise SSRFSecurityError(
            f"Неподдерживаемый протокол {parsed.scheme}",
            "Поддерживаются только безопасные ссылки HTTP и HTTPS."
        )

    hostname = parsed.hostname
    if not hostname:
        raise SSRFSecurityError("URL не содержит имени хоста", "Ссылка не содержит адреса сервера.")

    # Reject localhost / metadata strings explicitly
    blocked_hosts = {
        "localhost", "127.0.0.1", "::1", "0.0.0.0",
        "metadata.google.internal", "instance-data", "metadata"
    }
    if hostname.lower() in blocked_hosts:
        raise SSRFSecurityError(
            f"Запрещен доступ к локальному хосту: {hostname}",
            "Доступ к внутренним сетевым адресам запрещен."
        )

    # Resolve IP addresses for hostname
    try:
        addr_info = socket.getaddrinfo(hostname, parsed.port or 80, proto=socket.IPPROTO_TCP)
    except socket.gaierror as e:
        raise SSRFSecurityError(
            f"Не удалось разрешить адрес сервера: {e}",
            "Не удалось получить доступ к указанному серверу."
        )

    for item in addr_info:
        sockaddr = item[4]
        ip_str = sockaddr[0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            continue

        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            logger.warning(f"SSRF attempt blocked: host {hostname} resolved to private/restricted IP {ip_str}")
            raise SSRFSecurityError(
                f"IP-адрес {ip_str} является приватным или зарезервированным",
                "Скачивание файлов из локальных или защищенных сетей запрещено."
            )

    return url
