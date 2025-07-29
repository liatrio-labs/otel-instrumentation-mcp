"""Pythonic network utilities for automatic IP stack detection."""

import ipaddress
import logging
import socket
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import List, Optional, Set, Union

logger = logging.getLogger(__name__)


class IPVersion(Enum):
    """IP version enumeration."""

    IPV4 = 4
    IPV6 = 6


@dataclass(frozen=True)
class NetworkInterface:
    """Represents a network interface with its addresses."""

    name: str
    addresses: Set[Union[ipaddress.IPv4Address, ipaddress.IPv6Address]]

    @property
    def has_ipv4(self) -> bool:
        """Check if interface has IPv4 addresses."""
        return any(isinstance(addr, ipaddress.IPv4Address) for addr in self.addresses)

    @property
    def has_ipv6(self) -> bool:
        """Check if interface has IPv6 addresses."""
        return any(isinstance(addr, ipaddress.IPv6Address) for addr in self.addresses)

    @property
    def has_global_ipv6(self) -> bool:
        """Check if interface has global IPv6 addresses."""
        return any(
            isinstance(addr, ipaddress.IPv6Address)
            and not addr.is_loopback
            and not addr.is_link_local
            and not addr.is_multicast
            and not addr.is_unspecified
            for addr in self.addresses
        )

    @property
    def has_non_loopback_ipv4(self) -> bool:
        """Check if interface has non-loopback IPv4 addresses."""
        return any(
            isinstance(addr, ipaddress.IPv4Address) and not addr.is_loopback
            for addr in self.addresses
        )


@dataclass(frozen=True)
class NetworkCapabilities:
    """Represents the network capabilities of the system."""

    interfaces: List[NetworkInterface]
    socket_ipv4_available: bool
    socket_ipv6_available: bool

    @property
    def has_ipv4(self) -> bool:
        """System has IPv4 capability."""
        return self.socket_ipv4_available and any(
            iface.has_non_loopback_ipv4 for iface in self.interfaces
        )

    @property
    def has_ipv6(self) -> bool:
        """System has IPv6 capability."""
        return self.socket_ipv6_available and any(
            iface.has_global_ipv6 for iface in self.interfaces
        )

    @property
    def is_dual_stack(self) -> bool:
        """System supports both IPv4 and IPv6."""
        return self.has_ipv4 and self.has_ipv6

    @property
    def preferred_binding(self) -> str:
        """Get the preferred host binding address."""
        if self.is_dual_stack or self.has_ipv6:
            return "::"  # IPv6 wildcard (accepts both IPv4 and IPv6)
        elif self.has_ipv4:
            return "0.0.0.0"  # IPv4 wildcard
        else:
            logger.warning("No network capabilities detected, falling back to IPv4")
            return "0.0.0.0"


class NetworkDetector:
    """Pythonic network capability detection."""

    def __init__(self):
        self._proc_net_path = Path("/proc/net")

    def detect_capabilities(self) -> NetworkCapabilities:
        """
        Detect network capabilities using multiple methods.

        Returns:
            NetworkCapabilities: Detected network capabilities
        """
        interfaces = self._get_network_interfaces()
        socket_ipv4 = self._test_socket_family(socket.AF_INET)
        socket_ipv6 = self._test_socket_family(socket.AF_INET6)

        return NetworkCapabilities(
            interfaces=interfaces,
            socket_ipv4_available=socket_ipv4,
            socket_ipv6_available=socket_ipv6,
        )

    def _get_network_interfaces(self) -> List[NetworkInterface]:
        """
        Get network interfaces using Python's socket module.

        This is more Pythonic than parsing command output.
        """
        interfaces = []

        try:
            # Use socket.getaddrinfo to discover available addresses
            # This is more reliable than parsing /proc or command output
            hostname = socket.gethostname()

            # Get all addresses for this host
            addr_infos = socket.getaddrinfo(
                hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM
            )

            # Group addresses by interface (simplified - using hostname as interface)
            addresses = set()
            for addr_info in addr_infos:
                try:
                    ip_addr = ipaddress.ip_address(addr_info[4][0])
                    addresses.add(ip_addr)
                except ValueError:
                    continue  # Skip invalid addresses

            if addresses:
                interfaces.append(NetworkInterface(name=hostname, addresses=addresses))

        except (socket.error, OSError) as e:
            logger.debug(f"Could not get network interfaces via socket: {e}")

        # Fallback: try to get interfaces from /proc/net (Linux-specific)
        if not interfaces:
            interfaces.extend(self._get_interfaces_from_proc())

        return interfaces

    def _get_interfaces_from_proc(self) -> List[NetworkInterface]:
        """
        Fallback method to read interfaces from /proc/net.

        This is Linux-specific but more reliable than subprocess.
        """
        interfaces = []

        try:
            # Read IPv4 addresses from /proc/net/fib_trie or /proc/net/route
            ipv4_addrs = self._read_proc_ipv4_addresses()
            ipv6_addrs = self._read_proc_ipv6_addresses()

            all_addresses = ipv4_addrs | ipv6_addrs
            if all_addresses:
                interfaces.append(
                    NetworkInterface(name="proc", addresses=all_addresses)
                )

        except (OSError, IOError) as e:
            logger.debug(f"Could not read /proc/net: {e}")

        return interfaces

    def _read_proc_ipv4_addresses(self) -> Set[ipaddress.IPv4Address]:
        """Read IPv4 addresses from /proc/net files."""
        addresses = set()

        # Try reading from /proc/net/route (more reliable than fib_trie)
        route_file = self._proc_net_path / "route"
        if route_file.exists():
            try:
                with route_file.open() as f:
                    next(f)  # Skip header
                    for line in f:
                        parts = line.strip().split()
                        if len(parts) >= 2:
                            # Convert hex IP to dotted decimal
                            try:
                                hex_ip = parts[1]
                                if hex_ip != "00000000":  # Skip default route
                                    ip_int = int(hex_ip, 16)
                                    # Convert from little-endian
                                    ip_bytes = ip_int.to_bytes(4, "little")
                                    addr = ipaddress.IPv4Address(ip_bytes)
                                    if not addr.is_loopback:
                                        addresses.add(addr)
                            except (ValueError, OverflowError):
                                continue
            except IOError:
                pass

        return addresses

    def _read_proc_ipv6_addresses(self) -> Set[ipaddress.IPv6Address]:
        """Read IPv6 addresses from /proc/net/if_inet6."""
        addresses = set()

        inet6_file = self._proc_net_path / "if_inet6"
        if inet6_file.exists():
            try:
                with inet6_file.open() as f:
                    for line in f:
                        parts = line.strip().split()
                        if len(parts) >= 4:
                            try:
                                # Format: address device_number prefix_len scope_value flags interface_name
                                hex_addr = parts[0]
                                scope = int(parts[3], 16)

                                # Skip link-local (scope 0x20) and loopback (scope 0x10)
                                if scope not in (0x10, 0x20):
                                    # Convert hex to IPv6 address
                                    addr_str = ":".join(
                                        hex_addr[i : i + 4] for i in range(0, 32, 4)
                                    )
                                    addr = ipaddress.IPv6Address(addr_str)
                                    # Accept any non-loopback, non-link-local IPv6 address
                                    if not addr.is_loopback and not addr.is_link_local:
                                        addresses.add(addr)
                            except (ValueError, IndexError):
                                continue
            except IOError:
                pass

        return addresses

    def _test_socket_family(self, family: int) -> bool:
        """
        Test if a socket family is available.

        Args:
            family: Socket family (AF_INET or AF_INET6)

        Returns:
            bool: True if family is available
        """
        try:
            with socket.socket(family, socket.SOCK_STREAM) as sock:
                if family == socket.AF_INET:
                    sock.bind(("127.0.0.1", 0))
                else:  # AF_INET6
                    sock.bind(("::1", 0))
                return True
        except (OSError, socket.error):
            return False


class HostBindingManager:
    """Manages host binding configuration with environment override support."""

    def __init__(self, detector: Optional[NetworkDetector] = None):
        self.detector = detector or NetworkDetector()

    def get_optimal_binding(self) -> str:
        """
        Get the optimal host binding address.

        Returns:
            str: Host binding address
        """
        # Check for explicit override
        import os

        explicit_host = os.getenv("MCP_HOST")
        if explicit_host:
            logger.info(f"Using explicit host binding: {explicit_host}")
            return explicit_host

        # Auto-detect optimal binding
        capabilities = self.detector.detect_capabilities()
        binding = capabilities.preferred_binding

        logger.info(
            f"Auto-detected network: IPv4={capabilities.has_ipv4}, "
            f"IPv6={capabilities.has_ipv6}, binding={binding}"
        )

        return binding

    def validate_binding(self, host: str) -> bool:
        """
        Validate that a host binding will work.

        Args:
            host: Host address to validate

        Returns:
            bool: True if binding is valid
        """
        try:
            # Parse the address to determine family
            try:
                addr = ipaddress.ip_address(host)
                family = socket.AF_INET6 if addr.version == 6 else socket.AF_INET
            except ValueError:
                # Handle special cases like "::" and "0.0.0.0"
                if host == "::":
                    family = socket.AF_INET6
                elif host == "0.0.0.0":
                    family = socket.AF_INET
                else:
                    return False

            # Test binding
            with socket.socket(family, socket.SOCK_STREAM) as sock:
                if family == socket.AF_INET6 and host == "::":
                    # Enable dual-stack for IPv6 wildcard
                    sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
                sock.bind((host, 0))
                return True

        except (OSError, socket.error) as e:
            logger.warning(f"Host binding validation failed for {host}: {e}")
            return False


# Convenience functions for backward compatibility
def get_optimal_host_binding() -> str:
    """Get optimal host binding (backward compatibility)."""
    manager = HostBindingManager()
    return manager.get_optimal_binding()


def validate_host_binding(host: str) -> bool:
    """Validate host binding (backward compatibility)."""
    manager = HostBindingManager()
    return manager.validate_binding(host)


def detect_ip_stack() -> tuple[bool, bool]:
    """Detect IP stack capabilities (backward compatibility)."""
    detector = NetworkDetector()
    capabilities = detector.detect_capabilities()
    return capabilities.has_ipv4, capabilities.has_ipv6
