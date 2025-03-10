"""
Demo platform that offers a fake climate device.

For more details about this platform, please refer to the documentation
https://home-assistant.io/components/demo/
"""

import logging
from typing import Optional, List

import voluptuous as vol
from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate import PLATFORM_SCHEMA
from homeassistant.components.climate.const import (
    SUPPORT_TARGET_TEMPERATURE, SUPPORT_FAN_MODE,
    SUPPORT_SWING_MODE,
    SUPPORT_TARGET_HUMIDITY, HVAC_MODE_OFF, HVAC_MODE_HEAT, HVAC_MODE_COOL, HVAC_MODE_HEAT_COOL, HVAC_MODE_AUTO,
    HVAC_MODE_DRY,
    HVAC_MODE_FAN_ONLY)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import TEMP_CELSIUS, ATTR_TEMPERATURE, CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant, Event
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event

from .const import DOMAIN
from .ds_air_service.config import Config
from .ds_air_service.ctrl_enum import EnumControl
from .ds_air_service.dao import AirCon, AirConStatus
from .ds_air_service.display import display

SUPPORT_FLAGS = SUPPORT_TARGET_TEMPERATURE | SUPPORT_FAN_MODE | SUPPORT_SWING_MODE \
                | SUPPORT_SWING_MODE | SUPPORT_TARGET_HUMIDITY
FAN_LIST = ['最弱', '稍弱', '中等', '稍强', '最强', '自动']
SWING_LIST = ['➡️', '↘️', '⬇️', '↙️', '⬅️', '↔️', '🔄']

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Optional(CONF_HOST): cv.string,
    vol.Optional(CONF_PORT): cv.port
})

_LOGGER = logging.getLogger(__name__)


def _log(s: str):
    s = str(s)
    for i in s.split("\n"):
        _LOGGER.debug(i)


async def async_setup_entry(
        hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the Demo climate devices."""

    from .ds_air_service.service import Service
    climates = []
    for aircon in Service.get_aircons():
        climates.append(DsAir(aircon))
    async_add_entities(climates)
    link = entry.options.get("link")
    sensor_map = {}
    if link is not None:
        for i in link:
            if i.get("sensor") is not None:
                climate = None
                for j in climates:
                    if i.get("climate") == j.name:
                        climate = j
                        break
                if sensor_map.get(i.get("sensor")) is not None:
                    sensor_map[i.get("sensor")].append(climate)
                else:
                    sensor_map[i.get("sensor")] = [climate]

    async def listener(event: Event):
        for climate in sensor_map[event.data.get("entity_id")]:
            climate.update_cur_temp(event.data.get("new_state").state)

    remove_listener = async_track_state_change_event(hass, list(sensor_map.keys()), listener)
    hass.data[DOMAIN]["listener"] = remove_listener
    for entity_id in sensor_map.keys():
        state = hass.states.get(entity_id)
        if state is not None:
            for climate in sensor_map[entity_id]:
                climate.update_cur_temp(state.state)


class DsAir(ClimateEntity):
    """Representation of a demo climate device."""

    def __init__(self, aircon: AirCon):
        _log('create aircon:')
        _log(str(aircon.__dict__))
        _log(str(aircon.status.__dict__))
        """Initialize the climate device."""
        self._name = aircon.alias
        self._device_info = aircon
        self._unique_id = aircon.unique_id
        self._link_cur_temp = False
        self._cur_temp = None
        from .ds_air_service.service import Service
        Service.register_status_hook(aircon, self._status_change_hook)

    def _status_change_hook(self, **kwargs):
        _log('hook:')
        if kwargs.get('aircon') is not None:
            aircon: AirCon = kwargs['aircon']
            aircon.status = self._device_info.status
            self._device_info = aircon
            _log(display(self._device_info))

        if kwargs.get('status') is not None:
            status: AirConStatus = self._device_info.status
            new_status: AirConStatus = kwargs['status']
            if new_status.mode is not None:
                status.mode = new_status.mode
            if new_status.switch is not None:
                status.switch = new_status.switch
            if new_status.humidity is not None:
                status.humidity = new_status.humidity
            if new_status.air_flow is not None:
                status.air_flow = new_status.air_flow
            if new_status.fan_direction1 is not None:
                status.fan_direction1 = new_status.fan_direction1
            if new_status.fan_direction2 is not None:
                status.fan_direction2 = new_status.fan_direction2
            if new_status.setted_temp is not None:
                status.setted_temp = new_status.setted_temp
            if new_status.current_temp is not None:
                status.current_temp = new_status.current_temp
            if new_status.breathe is not None:
                status.breathe = new_status.breathe
            _log(display(self._device_info.status))
        self.schedule_update_ha_state()

    def update_cur_temp(self, value):
        self._link_cur_temp = value is not None
        try:
            self._cur_temp = float(value)
        except ValueError:
            """Ignore"""
        self.schedule_update_ha_state()

    @property
    def should_poll(self):
        """Return the polling state."""
        return False

    @property
    def name(self):
        """Return the name of the climate device."""
        return self._name

    @property
    def temperature_unit(self):
        """Return the unit of measurement."""
        return TEMP_CELSIUS

    @property
    def target_humidity(self):
        """Return the humidity we try to reach."""
        return self._device_info.status.humidity.value

    @property
    def hvac_action(self):
        """Return current operation ie. heat, cool, idle."""
        return None

    @property
    def hvac_mode(self) -> str:
        """Return hvac operation ie. heat, cool mode.

        Need to be one of HVAC_MODE_*.
        """
        if self._device_info.status.switch == EnumControl.Switch.OFF:
            return HVAC_MODE_OFF
        else:
            return EnumControl.get_mode_name(self._device_info.status.mode.value)

    @property
    def hvac_modes(self):
        """Return the list of supported features."""
        li = []
        aircon = self._device_info
        if aircon.cool_mode:
            li.append(HVAC_MODE_COOL)
        if aircon.heat_mode or aircon.pre_heat_mode:
            li.append(HVAC_MODE_HEAT)
        if aircon.auto_dry_mode or aircon.dry_mode or aircon.more_dry_mode:
            li.append(HVAC_MODE_DRY)
        if aircon.ventilation_mode:
            li.append(HVAC_MODE_FAN_ONLY)
        if aircon.relax_mode or aircon.auto_mode:
            li.append(HVAC_MODE_AUTO)
        if aircon.sleep_mode:
            li.append(HVAC_MODE_HEAT_COOL)
        li.append(HVAC_MODE_OFF)
        return li

    @property
    def current_temperature(self):
        """Return the current temperature."""
        if self._link_cur_temp:
            return self._cur_temp
        else:
            if Config.is_c611:
                return None
            else:
                return self._device_info.status.current_temp / 10

    @property
    def target_temperature(self):
        """Return the temperature we try to reach."""
        return self._device_info.status.setted_temp / 10

    @property
    def target_temperature_step(self):
        """Return the supported step of target temperature."""
        return 1

    @property
    def target_temperature_high(self):
        """Return the highbound target temperature we try to reach."""
        return None

    @property
    def target_temperature_low(self):
        """Return the lowbound target temperature we try to reach."""
        return None

    @property
    def current_humidity(self):
        """Return the current humidity."""
        return None

    @property
    def preset_mode(self) -> Optional[str]:
        """Return the current preset mode, e.g., home, away, temp.

        Requires SUPPORT_PRESET_MODE.
        """
        return None

    @property
    def preset_modes(self) -> Optional[List[str]]:
        """Return a list of available preset modes.

        Requires SUPPORT_PRESET_MODE.
        """
        return None

    @property
    def is_aux_heat(self):
        """Return true if aux heat is on."""
        return None

    @property
    def fan_mode(self):
        """Return the fan setting."""
        return EnumControl.get_air_flow_name(self._device_info.status.air_flow.value)

    @property
    def fan_modes(self) -> Optional[List[str]]:
        """Return the list of available fan modes.

        Requires SUPPORT_FAN_MODE.
        """
        return FAN_LIST

    @property
    def swing_mode(self):
        """Return the swing setting."""
        return EnumControl.get_fan_direction_name(self._device_info.status.fan_direction1.value)

    @property
    def swing_modes(self) -> Optional[List[str]]:
        """Return the list of available swing modes.

        Requires SUPPORT_SWING_MODE.
        """
        return SWING_LIST

    def set_temperature(self, **kwargs):
        """Set new target temperatures."""
        if kwargs.get(ATTR_TEMPERATURE) is not None:
            status = self._device_info.status
            new_status = AirConStatus()
            if status.switch == EnumControl.Switch.ON \
                    and status.mode not in [EnumControl.Mode.VENTILATION, EnumControl.Mode.MOREDRY]:
                status.setted_temp = round(kwargs.get(ATTR_TEMPERATURE)) * 10
                new_status.setted_temp = round(kwargs.get(ATTR_TEMPERATURE)) * 10
                from .ds_air_service.service import Service
                Service.control(self._device_info, new_status)
        self.schedule_update_ha_state()

    def set_humidity(self, humidity):
        """Set new humidity level."""
        status = self._device_info.status
        new_status = AirConStatus()
        if status.switch == EnumControl.Switch.ON \
                and status.mode in [EnumControl.Mode.RELAX, EnumControl.Mode.SLEEP]:
            status.humidity = EnumControl.Humidity(humidity)
            new_status.humidity = EnumControl.Humidity(humidity)
            from .ds_air_service.service import Service
            Service.control(self._device_info, new_status)
        self.schedule_update_ha_state()

    def set_fan_mode(self, fan_mode):
        """Set new fan mode."""
        status = self._device_info.status
        new_status = AirConStatus()
        if status.switch == EnumControl.Switch.ON \
                and status.mode not in [EnumControl.Mode.MOREDRY, EnumControl.Mode.SLEEP]:
            status.air_flow = EnumControl.get_air_flow_enum(fan_mode)
            new_status.air_flow = EnumControl.get_air_flow_enum(fan_mode)
            from .ds_air_service.service import Service
            Service.control(self._device_info, new_status)
        self.schedule_update_ha_state()

    def set_hvac_mode(self, hvac_mode: str) -> None:
        """Set new target hvac mode."""
        aircon = self._device_info
        status = aircon.status
        new_status = AirConStatus()
        if hvac_mode == HVAC_MODE_OFF:
            status.switch = EnumControl.Switch.OFF
            new_status.switch = EnumControl.Switch.OFF
            from .ds_air_service.service import Service
            Service.control(self._device_info, new_status)
        else:
            status.switch = EnumControl.Switch.ON
            new_status.switch = EnumControl.Switch.ON
            m = EnumControl.Mode
            mode = None
            if hvac_mode == HVAC_MODE_COOL:
                mode = m.COLD
            elif hvac_mode == HVAC_MODE_HEAT:
                if aircon.heat_mode:
                    mode = m.HEAT
                else:
                    mode = m.PREHEAT
            elif hvac_mode == HVAC_MODE_DRY:
                if aircon.auto_dry_mode:
                    mode = m.AUTODRY
                elif aircon.more_dry_mode:
                    mode = m.MOREDRY
                else:
                    mode = m.DRY
            elif hvac_mode == HVAC_MODE_FAN_ONLY:
                mode = m.VENTILATION
            elif hvac_mode == HVAC_MODE_AUTO:
                if aircon.auto_mode:
                    mode = m.AUTO
                else:
                    mode = m.RELAX
            elif hvac_mode == HVAC_MODE_HEAT_COOL:
                mode = m.SLEEP
            status.mode = mode
            new_status.mode = mode
            from .ds_air_service.service import Service
            Service.control(self._device_info, new_status)
        self.schedule_update_ha_state()

    def set_swing_mode(self, swing_mode):
        """Set new swing mode."""
        status = self._device_info.status
        new_status = AirConStatus()
        if status.switch == EnumControl.Switch.ON:
            status.fan_direction1 = self._device_info.status.fan_direction1
            new_status.fan_direction1 = self._device_info.status.fan_direction1
            status.fan_direction2 = EnumControl.get_fan_direction_enum(swing_mode)
            new_status.fan_direction2 = EnumControl.get_fan_direction_enum(swing_mode)
            from .ds_air_service.service import Service
            Service.control(self._device_info, new_status)
        self.schedule_update_ha_state()

    def set_preset_mode(self, preset_mode: str) -> None:
        pass

    def turn_aux_heat_on(self) -> None:
        pass

    def turn_aux_heat_off(self) -> None:
        pass

    @property
    def supported_features(self) -> int:
        """Return the list of supported features."""
        return SUPPORT_FLAGS

    @property
    def min_temp(self):
        """Return the minimum temperature."""
        return 16

    @property
    def max_temp(self):
        """Return the maximum temperature."""
        return 32

    @property
    def min_humidity(self):
        return 1

    @property
    def max_humidity(self):
        return 3

    @property
    def device_info(self) -> Optional[DeviceInfo]:
        return {
            "identifiers": {(DOMAIN, self.unique_id)},
            "name": "空调%s" % self._name,
            "manufacturer": "DAIKIN INDUSTRIES, Ltd."
        }

    @property
    def unique_id(self) -> Optional[str]:
        return self._unique_id
