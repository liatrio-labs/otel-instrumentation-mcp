"""Tests for Pythonic network utilities."""

import ipaddress
import os
import socket
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

import pytest

from otel_instrumentation_mcp.network_utils import (
    HostBindingManager,
    IPVersion,
    NetworkCapabilities,
    NetworkDetector,
    NetworkInterface,
    detect_ip_stack,
    get_optimal_host_binding,
    validate_host_binding,
)


class TestNetworkInterface:
    """Test NetworkInterface dataclass."""

    def test_ipv4_interface(self):
        """Test interface with IPv4 addresses."""
        addresses = {
            ipaddress.IPv4Address("192.168.1.1"),
            ipaddress.IPv4Address("10.0.0.1"),
        }
        interface = NetworkInterface(name="eth0", addresses=addresses)

        assert interface.has_ipv4 is True
        assert interface.has_ipv6 is False
        assert interface.has_global_ipv6 is False
        assert interface.has_non_loopback_ipv4 is True

    def test_ipv6_interface(self):
        """Test interface with IPv6 addresses."""
        addresses = {
            ipaddress.IPv6Address("2001:db8::1"),  # Documentation prefix
            ipaddress.IPv6Address("fe80::1"),  # Link-local
        }
        interface = NetworkInterface(name="eth0", addresses=addresses)

        assert interface.has_ipv4 is False
        assert interface.has_ipv6 is True
        assert (
            interface.has_global_ipv6 is True
        )  # 2001:db8::1 is usable (not loopback/link-local)
        assert interface.has_non_loopback_ipv4 is False

    def test_dual_stack_interface(self):
        """Test interface with both IPv4 and IPv6."""
        addresses = {
            ipaddress.IPv4Address("192.168.1.1"),
            ipaddress.IPv6Address("2001:db8::1"),
        }
        interface = NetworkInterface(name="eth0", addresses=addresses)

        assert interface.has_ipv4 is True
        assert interface.has_ipv6 is True
        assert interface.has_global_ipv6 is True
        assert interface.has_non_loopback_ipv4 is True

    def test_loopback_interface(self):
        """Test loopback interface."""
        addresses = {
            ipaddress.IPv4Address("127.0.0.1"),
            ipaddress.IPv6Address("::1"),
        }
        interface = NetworkInterface(name="lo", addresses=addresses)

        assert interface.has_ipv4 is True
        assert interface.has_ipv6 is True
        assert interface.has_global_ipv6 is False  # ::1 is not global
        assert interface.has_non_loopback_ipv4 is False  # 127.0.0.1 is loopback


class TestNetworkCapabilities:
    """Test NetworkCapabilities dataclass."""

    def test_ipv4_only_capabilities(self):
        """Test IPv4-only network capabilities."""
        interfaces = [
            NetworkInterface(
                name="eth0", addresses={ipaddress.IPv4Address("192.168.1.1")}
            )
        ]
        capabilities = NetworkCapabilities(
            interfaces=interfaces,
            socket_ipv4_available=True,
            socket_ipv6_available=False,
        )

        assert capabilities.has_ipv4 is True
        assert capabilities.has_ipv6 is False
        assert capabilities.is_dual_stack is False
        assert capabilities.preferred_binding == "0.0.0.0"

    def test_ipv6_only_capabilities(self):
        """Test IPv6-only network capabilities."""
        interfaces = [
            NetworkInterface(
                name="eth0", addresses={ipaddress.IPv6Address("2001:db8::1")}
            )
        ]
        capabilities = NetworkCapabilities(
            interfaces=interfaces,
            socket_ipv4_available=False,
            socket_ipv6_available=True,
        )

        assert capabilities.has_ipv4 is False
        assert capabilities.has_ipv6 is True
        assert capabilities.is_dual_stack is False
        assert capabilities.preferred_binding == "::"

    def test_dual_stack_capabilities(self):
        """Test dual-stack network capabilities."""
        interfaces = [
            NetworkInterface(
                name="eth0",
                addresses={
                    ipaddress.IPv4Address("192.168.1.1"),
                    ipaddress.IPv6Address("2001:db8::1"),
                },
            )
        ]
        capabilities = NetworkCapabilities(
            interfaces=interfaces,
            socket_ipv4_available=True,
            socket_ipv6_available=True,
        )

        assert capabilities.has_ipv4 is True
        assert capabilities.has_ipv6 is True
        assert capabilities.is_dual_stack is True
        assert capabilities.preferred_binding == "::"

    def test_no_network_capabilities(self):
        """Test fallback when no network is available."""
        capabilities = NetworkCapabilities(
            interfaces=[], socket_ipv4_available=False, socket_ipv6_available=False
        )

        assert capabilities.has_ipv4 is False
        assert capabilities.has_ipv6 is False
        assert capabilities.is_dual_stack is False
        assert capabilities.preferred_binding == "0.0.0.0"  # Fallback


class TestNetworkDetector:
    """Test NetworkDetector class."""

    def test_socket_family_detection(self):
        """Test socket family detection."""
        detector = NetworkDetector()

        # These should work on most systems
        ipv4_available = detector._test_socket_family(socket.AF_INET)
        ipv6_available = detector._test_socket_family(socket.AF_INET6)

        assert isinstance(ipv4_available, bool)
        assert isinstance(ipv6_available, bool)

    @patch("socket.socket")
    def test_socket_family_failure(self, mock_socket):
        """Test socket family detection failure."""
        mock_socket.side_effect = OSError("Socket creation failed")

        detector = NetworkDetector()
        result = detector._test_socket_family(socket.AF_INET)

        assert result is False

    @patch("socket.getaddrinfo")
    @patch("socket.gethostname")
    def test_get_network_interfaces_success(self, mock_hostname, mock_getaddrinfo):
        """Test successful network interface detection."""
        mock_hostname.return_value = "test-host"
        mock_getaddrinfo.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.1.1", 80)),
            (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("2001:db8::1", 80, 0, 0)),
        ]

        detector = NetworkDetector()
        interfaces = detector._get_network_interfaces()

        assert len(interfaces) == 1
        assert interfaces[0].name == "test-host"
        assert interfaces[0].has_ipv4 is True
        assert interfaces[0].has_ipv6 is True

    @patch("socket.getaddrinfo")
    @patch("socket.gethostname")
    def test_get_network_interfaces_fallback(self, mock_hostname, mock_getaddrinfo):
        """Test fallback to /proc/net when socket method fails."""
        mock_hostname.return_value = "test-host"
        mock_getaddrinfo.side_effect = socket.error("Network unreachable")

        detector = NetworkDetector()

        # Mock /proc/net files
        with patch.object(detector, "_get_interfaces_from_proc") as mock_proc:
            mock_proc.return_value = [
                NetworkInterface(
                    name="proc", addresses={ipaddress.IPv4Address("10.0.0.1")}
                )
            ]

            interfaces = detector._get_network_interfaces()

            assert len(interfaces) == 1
            assert interfaces[0].name == "proc"

    def test_read_proc_ipv4_addresses(self):
        """Test reading IPv4 addresses from /proc/net/route."""
        detector = NetworkDetector()

        # Mock /proc/net/route content
        route_content = """Iface	Destination	Gateway 	Flags	RefCnt	Use	Metric	Mask		MTU	Window	IRTT                                                       
eth0	0100000A	00000000	0001	0	0	0	00FFFFFF	0	0	0                                                                               
lo	0000007F	00000000	0001	0	0	0	000000FF	0	0	0"""

        with patch("pathlib.Path.exists", return_value=True):
            with patch("pathlib.Path.open", mock_open(read_data=route_content)):
                addresses = detector._read_proc_ipv4_addresses()

                # Should find 10.0.0.1 (0100000A in little-endian hex)
                expected = ipaddress.IPv4Address("10.0.0.1")
                assert expected in addresses

    def test_read_proc_ipv6_addresses(self):
        """Test reading IPv6 addresses from /proc/net/if_inet6."""
        detector = NetworkDetector()

        # Mock /proc/net/if_inet6 content
        inet6_content = """20010db8000000000000000000000001 02 40 00 80     eth0
00000000000000000000000000000001 01 80 10 80       lo
fe800000000000000000000000000001 02 40 20 80     eth0"""

        with patch("pathlib.Path.exists", return_value=True):
            with patch("pathlib.Path.open", mock_open(read_data=inet6_content)):
                addresses = detector._read_proc_ipv6_addresses()

                # Should find 2001:db8::1 (global scope)
                expected = ipaddress.IPv6Address("2001:db8::1")
                assert expected in addresses

                # Should not find loopback or link-local
                loopback = ipaddress.IPv6Address("::1")
                link_local = ipaddress.IPv6Address("fe80::1")
                assert loopback not in addresses
                assert link_local not in addresses

    def test_detect_capabilities_integration(self):
        """Test full capability detection."""
        detector = NetworkDetector()
        capabilities = detector.detect_capabilities()

        assert isinstance(capabilities, NetworkCapabilities)
        assert isinstance(capabilities.interfaces, list)
        assert isinstance(capabilities.socket_ipv4_available, bool)
        assert isinstance(capabilities.socket_ipv6_available, bool)


class TestHostBindingManager:
    """Test HostBindingManager class."""

    @patch.dict(os.environ, {"MCP_HOST": "192.168.1.1"})
    def test_explicit_host_override(self):
        """Test explicit host override via environment."""
        manager = HostBindingManager()
        binding = manager.get_optimal_binding()

        assert binding == "192.168.1.1"

    @patch.dict(os.environ, {}, clear=True)
    def test_auto_detection(self):
        """Test automatic detection when no override is set."""
        mock_detector = MagicMock()
        mock_capabilities = MagicMock()
        mock_capabilities.preferred_binding = "::"
        mock_capabilities.has_ipv4 = True
        mock_capabilities.has_ipv6 = True
        mock_detector.detect_capabilities.return_value = mock_capabilities

        manager = HostBindingManager(detector=mock_detector)
        binding = manager.get_optimal_binding()

        assert binding == "::"
        mock_detector.detect_capabilities.assert_called_once()

    def test_validate_binding_ipv4(self):
        """Test validation of IPv4 binding."""
        manager = HostBindingManager()

        # Test with localhost - should work on most systems
        result = manager.validate_binding("127.0.0.1")
        assert isinstance(result, bool)

    def test_validate_binding_ipv6_wildcard(self):
        """Test validation of IPv6 wildcard binding."""
        manager = HostBindingManager()

        result = manager.validate_binding("::")
        assert isinstance(result, bool)

    @patch("socket.socket")
    def test_validate_binding_failure(self, mock_socket):
        """Test validation failure."""
        mock_socket.return_value.__enter__.return_value.bind.side_effect = OSError(
            "Bind failed"
        )

        manager = HostBindingManager()
        result = manager.validate_binding("invalid-host")

        assert result is False


class TestBackwardCompatibility:
    """Test backward compatibility functions."""

    def test_get_optimal_host_binding(self):
        """Test backward compatibility function."""
        result = get_optimal_host_binding()
        assert isinstance(result, str)
        assert result in ["0.0.0.0", "::"]

    def test_validate_host_binding(self):
        """Test backward compatibility function."""
        result = validate_host_binding("127.0.0.1")
        assert isinstance(result, bool)

    def test_detect_ip_stack(self):
        """Test backward compatibility function."""
        ipv4, ipv6 = detect_ip_stack()
        assert isinstance(ipv4, bool)
        assert isinstance(ipv6, bool)


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_invalid_ip_address_parsing(self):
        """Test handling of invalid IP addresses."""
        manager = HostBindingManager()

        # These should not crash
        result1 = manager.validate_binding("not-an-ip")
        result2 = manager.validate_binding("")
        result3 = manager.validate_binding("999.999.999.999")

        assert result1 is False
        assert result2 is False
        assert result3 is False

    @patch("pathlib.Path.exists", return_value=False)
    def test_proc_files_not_available(self, mock_exists):
        """Test behavior when /proc files are not available."""
        detector = NetworkDetector()

        # Should not crash when /proc files don't exist
        ipv4_addrs = detector._read_proc_ipv4_addresses()
        ipv6_addrs = detector._read_proc_ipv6_addresses()

        assert isinstance(ipv4_addrs, set)
        assert isinstance(ipv6_addrs, set)
        assert len(ipv4_addrs) == 0
        assert len(ipv6_addrs) == 0
