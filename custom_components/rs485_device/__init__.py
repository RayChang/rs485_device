"""The RS-485 Device integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_COVERS,
    CONF_DEVICE,
    CONF_HOST,
    CONF_NAME,
    CONF_PORT,
    CONF_SENSORS,
    CONF_SLAVE,
    CONF_STATE,
    CONF_SWITCHES,
    Platform,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .const import CURTAIN_MODEL, DOMAIN, SENSORS_MODEL, SWITCH_MODEL
from .modbus_client import ModbusClient
from .rs485_tcp_publisher import RS485TcpPublisher

PLATFORMS: dict[str, list[Platform]] = {
    CONF_SWITCHES: [Platform.SWITCH],
    CONF_COVERS: [Platform.COVER],
    CONF_SENSORS: [Platform.SENSOR, Platform.BINARY_SENSOR],
}


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """獲取裝置註冊表。."""

    # 從 entry.data 中獲取所配置的裝置類型
    device_type = entry.data[CONF_DEVICE]

    device_registry = dr.async_get(hass)

    _model = None
    _domain_data = {"watchdog_task": None}
    if device_type == CONF_SWITCHES:
        _model = SWITCH_MODEL
        _domain_data.update(
            {
                CONF_STATE: None,
                CONF_SWITCHES: None,
            }
        )
    elif device_type == CONF_COVERS:
        _model = CURTAIN_MODEL
    elif device_type == CONF_SENSORS:
        _model = entry.data[SENSORS_MODEL]

    # 在裝置註冊表中創建一個新的裝置
    device = device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.data[CONF_SLAVE])},
        name=entry.data[CONF_NAME],
        model=_model,
    )

    hass.data.setdefault(
        DOMAIN,
        {
            "rs485_tcp_publisher": RS485TcpPublisher(
                host=entry.data[CONF_HOST], port=entry.data[CONF_PORT], byte_length=12
            ),
            "modbus_client": ModbusClient(
                host=entry.data[CONF_HOST], port=entry.data[CONF_PORT]
            ),
        },
    )
    hass.data[DOMAIN][entry.entry_id] = {CONF_DEVICE: device, **_domain_data}

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS[device_type])

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    device_type = entry.data[CONF_DEVICE]

    if unload_ok := await hass.config_entries.async_unload_platforms(
        entry, PLATFORMS[device_type]
    ):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
