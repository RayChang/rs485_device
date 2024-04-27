"""Client to interact with a Modbus device."""

import logging

from pymodbus.client import ModbusTcpClient

_LOGGER = logging.getLogger(__name__)


class ModbusClient:
    """Client to interact with a Modbus device."""

    def __init__(self, host: str, port: int) -> None:
        """Initialize the Modbus client with host and port."""
        self.client = ModbusTcpClient(host, port)

    def connect(self) -> bool:
        """Connect to the Modbus device."""
        return self.client.connect()

    def read_holding_registers(
        self, slave: int, address: int, count: int
    ) -> list[int] | None:
        """Read holding registers from the Modbus device."""
        response = self.client.read_holding_registers(address, count, slave)
        if not response.isError():
            return response.registers

        _LOGGER.error("Error reading holding registers: %s", response)
        return None

    def write_register(self, slave: int, address: int, value: int) -> bool:
        """Write a value to a register on the Modbus device."""
        response = self.client.write_register(address, value, slave)
        if not response.isError():
            return True

        _LOGGER.error("Error writing register: %s", response)
        return False

    def close(self):
        """Close the connection to the Modbus device."""
        self.client.close()
