"""Config flow for the xAI Conversation integration."""

from __future__ import annotations

from typing import Any

import grpc
import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigEntryState,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentryFlow,
    SubentryFlowResult,
)
from homeassistant.const import CONF_API_KEY, CONF_LLM_HASS_API, CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers import llm
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TemplateSelector,
)
from xai_sdk.aio.client import Client as XAIAsyncClient

from .const import (
    CONF_CHAT_MODEL,
    CONF_LIVE_SEARCH,
    CONF_MAX_SEARCH_RESULTS,
    CONF_MAX_TOKENS,
    CONF_PROMPT,
    CONF_REASONING_EFFORT,
    CONF_RECOMMENDED,
    CONF_TEMPERATURE,
    CONF_TOP_P,
    DEFAULT_AI_TASK_NAME,
    DEFAULT_CONVERSATION_NAME,
    DOMAIN,
    LOGGER,
    REASONING_OPTIONS,
    RECOMMENDED_AI_TASK_OPTIONS,
    RECOMMENDED_CHAT_MODEL,
    RECOMMENDED_CONVERSATION_OPTIONS,
    RECOMMENDED_LIVE_SEARCH,
    RECOMMENDED_MAX_SEARCH_RESULTS,
    RECOMMENDED_MAX_TOKENS,
    RECOMMENDED_REASONING_EFFORT,
    RECOMMENDED_TEMPERATURE,
    RECOMMENDED_TOP_P,
    XAI_MODELS,
)

STEP_USER_DATA_SCHEMA = vol.Schema({vol.Required(CONF_API_KEY): str})


async def validate_input(data: dict[str, Any]) -> None:
    """Validate the user input allows us to connect to xAI."""
    client = XAIAsyncClient(api_key=data[CONF_API_KEY], timeout=15)
    try:
        await client.models.list_language_models()
    except grpc.RpcError as err:
        msg = "cannot_connect"
        raise ValueError(msg) from err


class XAIConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for xAI Conversation."""

    VERSION = 1
    MINOR_VERSION = 0

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        if user_input is None:
            return self.async_show_form(
                step_id="user", data_schema=STEP_USER_DATA_SCHEMA
            )

        errors: dict[str, str] = {}

        self._async_abort_entries_match(user_input)
        try:
            await validate_input(user_input)
        except ValueError as err:
            errors["base"] = str(err)
        except Exception:  # noqa: BLE001
            LOGGER.exception("Unexpected exception validating API key")
            errors["base"] = "unknown"
        else:
            return self.async_create_entry(
                title="xAI",
                data=user_input,
                subentries=[
                    {
                        "subentry_type": "conversation",
                        "data": RECOMMENDED_CONVERSATION_OPTIONS,
                        "title": DEFAULT_CONVERSATION_NAME,
                        "unique_id": None,
                    },
                    {
                        "subentry_type": "ai_task",
                        "data": RECOMMENDED_AI_TASK_OPTIONS,
                        "title": DEFAULT_AI_TASK_NAME,
                        "unique_id": None,
                    },
                ],
            )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, _config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        """Return subentries supported by this integration."""
        return {
            "conversation": XAIConversationFlowHandler,
            "ai_task": XAIaiTaskDataFlowHandler,
        }


class XAIConversationFlowHandler(ConfigSubentryFlow):
    """Flow for managing xAI conversation subentries."""

    options: dict[str, Any]

    @property
    def _subentry_type(self) -> str:
        """Return the subentry type."""
        return "conversation"

    @property
    def _is_new(self) -> bool:
        """Return if this is a new subentry."""
        return self.source == "user"

    async def async_step_user(
        self, _user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Initialize options for a new subentry."""
        self.options = RECOMMENDED_CONVERSATION_OPTIONS.copy()
        return await self.async_step_init()

    async def async_step_reconfigure(
        self, _user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Handle reconfiguration of a subentry."""
        self.options = self._get_reconfigure_subentry().data.copy()
        return await self.async_step_init()

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Show the initial configuration step."""
        if self._get_entry().state != ConfigEntryState.LOADED:
            return self.async_abort(reason="entry_not_loaded")

        options = self.options

        hass_apis: list[SelectOptionDict] = [
            SelectOptionDict(label=api.name, value=api.id)
            for api in llm.async_get_apis(self.hass)
        ]

        if (suggested_llm := options.get(CONF_LLM_HASS_API)) and isinstance(
            suggested_llm, str
        ):
            options[CONF_LLM_HASS_API] = [suggested_llm]

        step_schema: dict[Any, Any] = {}

        if self._is_new:
            default_name = DEFAULT_CONVERSATION_NAME
            step_schema[vol.Required(CONF_NAME, default=default_name)] = str

        step_schema.update(
            {
                vol.Optional(
                    CONF_PROMPT,
                    description={
                        "suggested_value": options.get(
                            CONF_PROMPT, llm.DEFAULT_INSTRUCTIONS_PROMPT
                        )
                    },
                ): TemplateSelector(),
                vol.Optional(CONF_LLM_HASS_API): SelectSelector(
                    SelectSelectorConfig(options=hass_apis, multiple=True)
                ),
            }
        )

        step_schema[
            vol.Required(CONF_RECOMMENDED, default=options.get(CONF_RECOMMENDED, True))
        ] = bool

        if user_input is not None:
            if not user_input.get(CONF_LLM_HASS_API):
                user_input.pop(CONF_LLM_HASS_API, None)

            prompt = user_input.get(CONF_PROMPT)
            if prompt:
                options[CONF_PROMPT] = prompt
            else:
                options.pop(CONF_PROMPT, None)

            if llm_apis := user_input.get(CONF_LLM_HASS_API):
                options[CONF_LLM_HASS_API] = llm_apis
            else:
                options.pop(CONF_LLM_HASS_API, None)

            if user_input[CONF_RECOMMENDED]:
                if self._is_new:
                    title = user_input.get(CONF_NAME, DEFAULT_CONVERSATION_NAME)
                    return self.async_create_entry(title=title, data=options)
                return self.async_update_and_abort(
                    self._get_entry(),
                    self._get_reconfigure_subentry(),
                    data=options,
                )

            options.update(user_input)
            return await self.async_step_advanced()

        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(step_schema),
                options,
            ),
        )

    async def async_step_advanced(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Show advanced configuration when recommended settings are disabled."""
        options = self.options

        # Create model options for dropdown
        model_options: list[SelectOptionDict] = [
            SelectOptionDict(value=model["id"], label=model["name"])
            for model in XAI_MODELS
        ]

        step_schema: dict[Any, Any] = {
            vol.Required(
                CONF_CHAT_MODEL,
                default=options.get(CONF_CHAT_MODEL, RECOMMENDED_CHAT_MODEL),
            ): SelectSelector(
                SelectSelectorConfig(
                    options=model_options,
                    mode=SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Optional(
                CONF_MAX_TOKENS,
                default=options.get(CONF_MAX_TOKENS, RECOMMENDED_MAX_TOKENS),
            ): vol.All(int, vol.Range(min=1)),
            vol.Optional(
                CONF_TEMPERATURE,
                default=options.get(CONF_TEMPERATURE, RECOMMENDED_TEMPERATURE),
            ): NumberSelector(NumberSelectorConfig(min=0, max=2, step=0.05)),
            vol.Optional(
                CONF_TOP_P,
                default=options.get(CONF_TOP_P, RECOMMENDED_TOP_P),
            ): NumberSelector(NumberSelectorConfig(min=0, max=1, step=0.05)),
            # Always show reasoning effort field - only used for supporting models
            vol.Optional(
                CONF_REASONING_EFFORT,
                default=options.get(
                    CONF_REASONING_EFFORT, RECOMMENDED_REASONING_EFFORT
                ),
            ): SelectSelector(
                SelectSelectorConfig(
                    options=REASONING_OPTIONS,
                    translation_key=CONF_REASONING_EFFORT,
                )
            ),
            vol.Optional(
                CONF_LIVE_SEARCH,
                default=options.get(CONF_LIVE_SEARCH, RECOMMENDED_LIVE_SEARCH),
            ): bool,
            vol.Optional(
                CONF_MAX_SEARCH_RESULTS,
                default=options.get(
                    CONF_MAX_SEARCH_RESULTS, RECOMMENDED_MAX_SEARCH_RESULTS
                ),
            ): NumberSelector(NumberSelectorConfig(min=1, max=50, step=1)),
        }

        if user_input is not None:
            options.update(user_input)
            if self._is_new:
                title = options.pop(CONF_NAME, DEFAULT_CONVERSATION_NAME)
                return self.async_create_entry(title=title, data=options)
            return self.async_update_and_abort(
                self._get_entry(),
                self._get_reconfigure_subentry(),
                data=options,
            )

        return self.async_show_form(
            step_id="advanced",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(step_schema),
                options,
            ),
        )


class XAIaiTaskDataFlowHandler(ConfigSubentryFlow):
    """Flow for managing xAI AI task subentries."""

    options: dict[str, Any]

    @property
    def _subentry_type(self) -> str:
        """Return the subentry type."""
        return "ai_task"

    @property
    def _is_new(self) -> bool:
        """Return if this is a new subentry."""
        return self.source == "user"

    async def async_step_user(
        self, _user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Initialize options for a new subentry."""
        self.options = RECOMMENDED_AI_TASK_OPTIONS.copy()
        return await self.async_step_init()

    async def async_step_reconfigure(
        self, _user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Handle reconfiguration of a subentry."""
        self.options = self._get_reconfigure_subentry().data.copy()
        return await self.async_step_init()

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Show the initial configuration step."""
        if self._get_entry().state != ConfigEntryState.LOADED:
            return self.async_abort(reason="entry_not_loaded")

        options = self.options

        step_schema: dict[Any, Any] = {}

        if self._is_new:
            default_name = DEFAULT_AI_TASK_NAME
            step_schema[vol.Required(CONF_NAME, default=default_name)] = str

        step_schema[
            vol.Required(CONF_RECOMMENDED, default=options.get(CONF_RECOMMENDED, True))
        ] = bool

        if user_input is not None:
            if user_input[CONF_RECOMMENDED]:
                if self._is_new:
                    title = user_input.get(CONF_NAME, DEFAULT_AI_TASK_NAME)
                    return self.async_create_entry(title=title, data=options)
                return self.async_update_and_abort(
                    self._get_entry(),
                    self._get_reconfigure_subentry(),
                    data=options,
                )

            options.update(user_input)
            return await self.async_step_advanced()

        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(step_schema),
                options,
            ),
        )

    async def async_step_advanced(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Show advanced configuration when recommended settings are disabled."""
        options = self.options

        # Create model options for dropdown
        model_options: list[SelectOptionDict] = [
            SelectOptionDict(value=model["id"], label=model["name"])
            for model in XAI_MODELS
        ]

        step_schema: dict[Any, Any] = {
            vol.Required(
                CONF_CHAT_MODEL,
                default=options.get(CONF_CHAT_MODEL, RECOMMENDED_CHAT_MODEL),
            ): SelectSelector(
                SelectSelectorConfig(
                    options=model_options,
                    mode=SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Optional(
                CONF_MAX_TOKENS,
                default=options.get(CONF_MAX_TOKENS, RECOMMENDED_MAX_TOKENS),
            ): vol.All(int, vol.Range(min=1)),
            vol.Optional(
                CONF_TEMPERATURE,
                default=options.get(CONF_TEMPERATURE, RECOMMENDED_TEMPERATURE),
            ): NumberSelector(NumberSelectorConfig(min=0, max=2, step=0.05)),
            vol.Optional(
                CONF_TOP_P,
                default=options.get(CONF_TOP_P, RECOMMENDED_TOP_P),
            ): NumberSelector(NumberSelectorConfig(min=0, max=1, step=0.05)),
            # Always show reasoning effort field - only used for supporting models
            vol.Optional(
                CONF_REASONING_EFFORT,
                default=options.get(
                    CONF_REASONING_EFFORT, RECOMMENDED_REASONING_EFFORT
                ),
            ): SelectSelector(
                SelectSelectorConfig(
                    options=REASONING_OPTIONS,
                    translation_key=CONF_REASONING_EFFORT,
                )
            ),
            vol.Optional(
                CONF_LIVE_SEARCH,
                default=options.get(CONF_LIVE_SEARCH, RECOMMENDED_LIVE_SEARCH),
            ): bool,
            vol.Optional(
                CONF_MAX_SEARCH_RESULTS,
                default=options.get(
                    CONF_MAX_SEARCH_RESULTS, RECOMMENDED_MAX_SEARCH_RESULTS
                ),
            ): NumberSelector(NumberSelectorConfig(min=1, max=50, step=1)),
        }

        if user_input is not None:
            options.update(user_input)
            if self._is_new:
                title = options.pop(CONF_NAME, DEFAULT_AI_TASK_NAME)
                return self.async_create_entry(title=title, data=options)
            return self.async_update_and_abort(
                self._get_entry(),
                self._get_reconfigure_subentry(),
                data=options,
            )

        return self.async_show_form(
            step_id="advanced",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(step_schema),
                options,
            ),
        )
