"""The xAI Conversation integration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY, Platform
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.httpx_client import get_async_client

from .client import XAIClientError, XAIRestClient
from .const import LOGGER

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.typing import ConfigType

PLATFORMS: Final = (Platform.CONVERSATION, Platform.AI_TASK)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN := "xai_conversation")


type XAIConfigEntry = ConfigEntry[XAIRestClient]


async def async_setup(_hass: HomeAssistant, _config: ConfigType) -> bool:
    """Set up the xAI Conversation integration."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: XAIConfigEntry) -> bool:
    """Set up xAI Conversation from a config entry."""
    client = XAIRestClient(entry.data[CONF_API_KEY], get_async_client(hass))

    try:
        await client.list_models()
    except XAIClientError as err:
        LOGGER.error("Unable to connect to xAI: %s", err)
        raise ConfigEntryNotReady(err) from err

    entry.runtime_data = client

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_update_options))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: XAIConfigEntry) -> bool:
    """Unload xAI Conversation entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_update_options(hass: HomeAssistant, entry: XAIConfigEntry) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)
