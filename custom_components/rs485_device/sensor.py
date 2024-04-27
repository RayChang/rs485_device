"""RS485 Sensor component."""

from dataclasses import dataclass
from datetime import timedelta
import logging
from typing import Any, Final

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_SLAVE, PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN, SENSORS_MODEL
from .modbus_client import ModbusClient
from .rs485_tcp_publisher import RS485TcpPublisher

_LOGGER = logging.getLogger(__name__)
SCAN_INTERVAL = timedelta(seconds=3)


@dataclass(frozen=True, kw_only=True)
class RS485SensorEntityDescription(SensorEntityDescription):
    """針對 RS485 的感應器擴充屬性."""

    address: int | None = None


SENSOR_TYPES: Final = {
    "SD123-HPR05": (
        RS485SensorEntityDescription(
            key="human_radar",
            name="Human Radar Detection",
            device_class="presence",
            address=12,
            icon="mdi:radar",
            native_unit_of_measurement="",
        ),
        RS485SensorEntityDescription(
            key="human_motion",
            name="Human Motion",
            device_class="motion",
            address=13,
            icon="mdi:motion-sensor",
            native_unit_of_measurement=PERCENTAGE,
        ),
    ),
    "SD123-HPR06": ["temperature", "humidity"],
}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """通過配置條目設置感應器."""

    # 從 entry.data 中獲取配置數據
    config = {
        **entry.data,
        "entry_id": entry.entry_id,
    }

    sensor_model: str = entry.data.get(SENSORS_MODEL, "SD123-HPR05")
    sensors = []
    RS485SensorEntity = (
        sensor_model == "SD123-HPR05" and RS485ModbusSensor or RS485Sensor
    )
    for description in SENSOR_TYPES[sensor_model]:
        sensors.append(RS485SensorEntity(hass, config, description))
    async_add_entities(sensors, True)


class RS485ModbusSensor(SensorEntity):
    """RS485 Modbus Sensor entity."""

    _attr_has_entity_name = True
    entity_description: RS485SensorEntityDescription

    def __init__(
        self,
        hass: HomeAssistant,
        config: dict[str, Any],
        description: RS485SensorEntityDescription,
    ) -> None:
        """Initialize the RS485Sensor."""
        self.hass = hass
        self.entity_description = description
        self._state = None
        self._slave: int = config.get(CONF_SLAVE, 0)
        self._entry_id: str = config.get("entry_id", "")
        self._unique_id: str = (
            f"{self._entry_id}_{self.entity_description.key}_{self._slave}"
        )
        self._modbus_client: ModbusClient = self.hass.data[DOMAIN]["modbus_client"]
        self.coordinator = DataUpdateCoordinator(
            hass,
            _LOGGER,
            name=self.entity_description.name,
            update_method=self.async_update,
            update_interval=timedelta(seconds=5),
        )

    @property
    def unique_id(self) -> str:
        """返回實體的唯一 ID."""
        return self._unique_id

    @property
    def name(self) -> str:
        """返回實體的名稱."""
        return self.entity_description.name

    @property
    def device_class(self):
        """Return the class of this device, from component DEVICE_CLASSES."""
        return self.entity_description.device_class

    @property
    def native_unit_of_measurement(self):
        """Return the unit of measurement of this entity, if any."""
        if self.entity_description.key == "human_radar":
            return None
        return self.entity_description.native_unit_of_measurement

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information for this entity."""
        device = self.hass.data[DOMAIN][self._entry_id]["device"]
        return {
            "identifiers": device.identifiers,
            "name": device.name,
            "manufacturer": device.manufacturer,
            "model": device.model,
            "connections": device.connections,
        }

    @property
    def native_value(self) -> StateType:
        """更新實體的狀態."""
        return self._state

    @property
    def state(self) -> dict[str, Any]:
        """返回传感器的当前状态，映射为具体描述."""
        if self.entity_description.key == "human_radar":
            return {0: "無人", 1: "靜止", 2: "活動"}.get(self._state, "未知")

        return self._state

    @property
    def device_state_attributes(self) -> dict[str, Any]:
        """返回設備的其他狀態屬性."""
        if self.entity_description.key == "human_radar":
            return {
                "description": {0: "無人", 1: "靜止", 2: "活動"}.get(
                    self._state, "未知"
                )
            }
        return {}

    async def async_added_to_hass(self):
        """When entity is added to hass."""
        await super().async_added_to_hass()
        await self.coordinator.async_refresh()

    async def async_update(self):
        """更新狀態."""
        self._state = await self.hass.async_add_executor_job(
            self._modbus_client.read_holding_registers,
            self._slave,
            self.entity_description.address,
            1,
        )
        if self._state is not None:
            self._state = self._state[0]
            _LOGGER.info("🚧 Sensor Update 🚧 %s", self._state)


class RS485Sensor(SensorEntity):
    """RS485 Modbus Sensor entity."""

    _attr_has_entity_name = True
    entity_description: SensorEntityDescription

    def __init__(
        self,
        hass: HomeAssistant,
        config: dict[str, Any],
        description: SensorEntityDescription,
    ) -> None:
        """Initialize the RS485Sensor."""
        self.hass = hass
        self.entity_description = description
        self._state = 0
        self._slave: int = config.get(CONF_SLAVE, 0)
        self._entry_id: str = config.get("entry_id", "")
        self._unique_id: str = (
            f"{self._entry_id}_{self.entity_description.key}_{self._slave}"
        )
        self._publisher: RS485TcpPublisher = self.hass.data[DOMAIN][
            "rs485_tcp_publisher"
        ]

    @property
    def unique_id(self) -> str:
        """返回實體的唯一 ID."""
        return self._unique_id

    @property
    def name(self) -> str:
        """返回實體的名稱."""
        return self.entity_description.name

    @property
    def device_class(self):
        """Return the class of this device, from component DEVICE_CLASSES."""
        return self.entity_description.device_class

    @property
    def native_unit_of_measurement(self):
        """Return the unit of measurement of this entity, if any."""
        if self.entity_description.key == "human_radar":
            return None
        return self.entity_description.native_unit_of_measurement

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information for this entity."""
        device = self.hass.data[DOMAIN][self._entry_id]["device"]
        return {
            "identifiers": device.identifiers,
            "name": device.name,
            "manufacturer": device.manufacturer,
            "model": device.model,
            "connections": device.connections,
        }

    @property
    def native_value(self) -> StateType:
        """更新實體的狀態."""
        return self._state

    async def async_added_to_hass(self):
        """當實體添加到 Home Assistant 時，設置狀態更新的計劃."""
        # 當實體添加到 Home Assistant 時，起始連接 rs-485 伺服器

        _LOGGER.info("🚧 Added to hass 🚧 %s", self.entity_description.name)

    async def async_update(self):
        """更新狀態."""
        _LOGGER.info("🚧 Sensor Update 🚧 %s", self._state)
        self.schedule_update_ha_state()
