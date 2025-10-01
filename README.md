# xAI Conversation for Home Assistant

Interact with xAI's Grok models directly from Home Assistant's Conversation platform. The integration uses the official [`xai-sdk`](https://pypi.org/project/xai-sdk/) to provide fast responses, optional reasoning, and live search enrichment while keeping configuration in the Home Assistant UI.

## ✨ Features

- Works out of the box with the recommended **`grok-4-fast-non-reasoning`** model.
- Live search toggle to let Grok fetch fresh information when needed.
- Full support for Home Assistant LLM tools, prompts, and conversation history.
- Advanced tuning of tokens, sampling temperature/top-p, and reasoning effort per conversation subentry.

## 🔑 Requirements

- Home Assistant 2025.2.4 or newer.
- An xAI API key with access to the Grok models.

## 📦 Installation

1. Copy the `custom_components/xai_conversation` folder into your Home Assistant `config/custom_components` directory.
2. Restart Home Assistant to load the new integration.
3. (Optional) If you manage dependencies manually, ensure `xai-sdk==1.2.0` is available to Home Assistant.

## ⚙️ Configuration

1. In Home Assistant, navigate to **Settings → Devices & Services → Add Integration**.
2. Search for **xAI Conversation** and enter your xAI API key.
3. A recommended conversation agent is created automatically with safe defaults.
4. You can add additional conversation entries or reconfigure existing ones from the entry's **Configure** menu.

### Advanced options

When you uncheck **Use recommended settings**, the following fields become editable:

| Option | Description | Default |
| --- | --- | --- |
| **Chat model** | Grok model to use for the conversation. | `grok-4-fast-non-reasoning` |
| **Max tokens** | Upper bound for generated response length. | `4096` |
| **Temperature** | Sampling temperature for creativity. | `0.7` |
| **Top-p** | Nucleus sampling threshold. | `1.0` |
| **Reasoning effort** | Controls Grok's reasoning depth. | `medium` |
| **Live search** | If enabled, Grok augments responses with real-time information. | Enabled |
| **Prompt** | Custom system prompt to scope the agent. | Home Assistant default |
| **Home Assistant LLM APIs** | Allow the agent to call built-in Home Assistant tools. | Assist API |

Live search is always visible in the advanced view so you can toggle it per subentry even if other fields stay at their defaults.

## 🛠️ Development & Testing

- Run `./scripts/develop` to spin up a Home Assistant instance with this integration for manual testing.
- Run `./scripts/lint` before committing to ensure Home Assistant style checks pass.
- Project dependencies are listed in `requirements.txt`.

## ❓ Troubleshooting

- **`cannot_connect` error during setup** – confirm your API key is valid and has Grok access.
- **Slow or missing answers** – disable live search to isolate network latency, or lower max tokens for shorter replies.
- Check Home Assistant logs (`config/home-assistant.log`) for detailed integration traces.

Enjoy chatting with Grok from your smart home! 🏠🤖

