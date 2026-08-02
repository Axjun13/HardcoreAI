import socket

import pytest
from fastapi import HTTPException

from api.routers.components import _image_url_target, _require_public_addresses


def test_component_image_proxy_accepts_public_hosts():
    host, port = _image_url_target("https://example.com/component.jpg")
    addresses = [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443)),
    ]

    assert (host, port) == ("example.com", 443)
    _require_public_addresses(addresses)


@pytest.mark.parametrize(
    "address",
    ["127.0.0.1", "10.0.0.4", "169.254.169.254", "::1"],
)
def test_component_image_proxy_rejects_non_public_hosts(address):
    family = socket.AF_INET6 if ":" in address else socket.AF_INET
    addresses = [
        (family, socket.SOCK_STREAM, 6, "", (address, 443)),
    ]

    with pytest.raises(HTTPException) as exc:
        _require_public_addresses(addresses)

    assert exc.value.status_code == 400
