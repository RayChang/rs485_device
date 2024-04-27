"""Constants for the RS-485 Device integration."""

from typing import Final

from homeassistant.const import CONF_COVERS, CONF_SENSORS, CONF_SWITCHES

DOMAIN: Final = "rs485_device"
MODBUS_HUB: Final = "rs-485_device_hub"
CURTAIN_MODEL: Final = "CMD82-5S"
SENSOR_MODEL: Final = ["SD123-HPR05", "SD123-HPR06"]
SWITCH_MODEL: Final = "LP-F8"
DEFAULT_NAME: Final = {
    CONF_SWITCHES: "Wall Switch",
    CONF_COVERS: "Curtain",
    CONF_SENSORS: "Sensor",
}

# 按鈕數量
KEY_COUNT: Final = list(range(1, 7))

# 含有繼電器
HAS_RELAY: Final = "has_relay"

SENSORS_MODEL: Final = "sensors_model"

# 設備類型
DEVICE_TYPE: Final = {
    CONF_SWITCHES: CONF_SWITCHES,
    CONF_COVERS: CONF_COVERS,
    CONF_SENSORS: CONF_SENSORS,
}
