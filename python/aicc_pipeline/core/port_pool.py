"""Dynamic port allocation pool for multi-call support."""
from typing import Dict, Tuple, Optional
import threading
import logging

logger = logging.getLogger("aicc.port_pool")


class PortPool:
    """Thread-safe dynamic port allocation pool."""

    def __init__(self, start: int = 20000, end: int = 30000):
        """
        Initialize port pool.

        Args:
            start: Starting port number (even, for customer)
            end: Ending port number
        """
        self.available = set(range(start, end, 2))  # Even ports for customer, odd for agent
        self.allocated: Dict[str, Tuple[int, int]] = {}
        self._port_to_call: Dict[int, str] = {}  # Maps port -> call_id for lookup
        self._lock = threading.Lock()
        logger.info(f"PortPool initialized with {len(self.available)} port pairs")

    def allocate(self, call_id: str) -> Tuple[int, int]:
        """
        Allocate a port pair for a call.

        Args:
            call_id: Unique call identifier

        Returns:
            Tuple of (customer_port, agent_port)

        Raises:
            ValueError: If port pool exhausted
        """
        with self._lock:
            if not self.available:
                raise ValueError("Port pool exhausted - no available ports")
            customer_port = min(self.available)  # Use min() for deterministic behavior
            self.available.remove(customer_port)
            agent_port = customer_port + 1
            self.allocated[call_id] = (customer_port, agent_port)
            self._port_to_call[customer_port] = call_id
            self._port_to_call[agent_port] = call_id
            logger.info(f"Allocated ports {customer_port}/{agent_port} for call {call_id}")
            return customer_port, agent_port

    def release(self, call_id: str) -> None:
        """Release ports back to the pool."""
        with self._lock:
            if call_id in self.allocated:
                ports = self.allocated.pop(call_id)
                self._port_to_call.pop(ports[0], None)
                self._port_to_call.pop(ports[1], None)
                self.available.add(ports[0])
                logger.info(f"Released ports {ports[0]}/{ports[1]} for call {call_id}")

    def get_call_id_by_port(self, port: int) -> Optional[str]:
        """Look up call_id by port number for incoming UDP packets."""
        with self._lock:
            return self._port_to_call.get(port)

    @property
    def available_count(self) -> int:
        """Number of available port pairs."""
        with self._lock:
            return len(self.available)

    @property
    def allocated_count(self) -> int:
        """Number of allocated port pairs."""
        with self._lock:
            return len(self.allocated)
