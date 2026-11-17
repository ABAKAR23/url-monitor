import ipaddress

IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address


def is_forbidden_ip(ip: IPAddress) -> bool:
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return not ip.is_global or ip.is_multicast


def is_forbidden_host(host: str) -> bool:
    """Contrôle sans DNS fait à la création ; le worker revérifie l'IP résolue avant chaque ping."""
    host = host.strip("[]").rstrip(".").lower()
    if host == "localhost" or host.endswith(".localhost"):
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return is_forbidden_ip(ip)
