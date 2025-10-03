# xAI Conversation for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/release/fabianluque/xai-conversation.svg)](https://github.com/fabianluque/xai-conversation/releases)
[![License](https://img.shields.io/github/license/fabianluque/xai-conversation.svg)](LICENSE)

Interact with xAI's Grok models directly from Home Assistant's Conversation platform. The integration uses the official [`xai-sdk`](https://pypi.org/project/xai-sdk/) to provide fast responses, optional reasoning, and live search enrichment while keeping configuration in the Home Assistant UI.

## ✨ Features

### Conversation Agents
- **Multiple Grok models** supported:
  - `grok-4-fast-reasoning` - Fast model with reasoning capabilities
  - `grok-4-fast-non-reasoning` - Fast model optimized for speed (recommended)
  - `grok-4` - Full Grok 4 with reasoning
  - `grok-3` - Grok 3 with reasoning
  - `grok-3-mini` - Smaller Grok 3 with reasoning
  - `grok-2-image` - Image generation model
- **Streaming responses** for real-time interaction
- **Live search** with configurable max results (1-50) to fetch fresh information
- **Reasoning effort control** (low, medium, high) for models that support it
- Full support for **Home Assistant LLM tools** and conversation history
- **Image attachments** support in conversations
- Advanced tuning: max tokens, temperature, top-p, custom system prompts

### AI Task Support
- **Generate structured data** with automatic JSON schema validation
- **Generate images** using `grok-2-image` model
- Support for **attachments** in AI tasks
- Seamless integration with Home Assistant's AI Task platform

## 🔑 Requirements

- Home Assistant 2024.2.0 or newer.
- An xAI API key with access to the Grok models.

## 📦 Installation

### HACS (Recommended)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=fabianluque&repository=xai-conversation&category=integration)

1. Ensure [HACS](https://hacs.xyz/) is installed in your Home Assistant instance.
2. Click the button above **OR** manually add the repository:
   - In Home Assistant, go to **HACS → Integrations**.
   - Click the three dots menu in the top right and select **Custom repositories**.
   - Add this repository URL: `https://github.com/fabianluque/xai-conversation`
   - Set the category to **Integration** and click **Add**.
3. Find **xAI Conversation** in the HACS integrations list and click **Download**.
4. Restart Home Assistant.

### Manual Installation

1. Copy the `custom_components/xai_conversation` folder into your Home Assistant `config/custom_components` directory.
2. Restart Home Assistant to load the new integration.
3. (Optional) If you manage dependencies manually, ensure `xai-sdk==1.2.0` is available to Home Assistant.

## ⚙️ Configuration

1. In Home Assistant, navigate to **Settings → Devices & Services → Add Integration**.
2. Search for **xAI Conversation** and enter your xAI API key.
3. Two entries are created automatically:
   - **xAI Conversation** - A conversation agent for chat interactions
   - **xAI AI Task** - An AI task entity for structured data and image generation
4. You can add additional entries or reconfigure existing ones from the entry's **Configure** menu.

### Conversation Agent Options

When you uncheck **Use recommended settings**, the following fields become editable:

| Option | Description | Default |
| --- | --- | --- |
| **Chat model** | Grok model to use for the conversation. | `grok-4-fast-non-reasoning` |
| **Max tokens** | Upper bound for generated response length. | `4096` |
| **Temperature** | Sampling temperature for creativity (0-2). | `0.7` |
| **Top-p** | Nucleus sampling threshold (0-1). | `1.0` |
| **Reasoning effort** | Controls Grok's reasoning depth (low/medium/high). Only applies to reasoning models. | `medium` |
| **Live search** | If enabled, Grok augments responses with real-time information. | Disabled |
| **Max search results** | Maximum number of search results to include (1-50). Only applies when live search is enabled. | `5` |
| **Prompt** | Custom system prompt to scope the agent. | Home Assistant default |
| **Home Assistant LLM APIs** | Allow the agent to call built-in Home Assistant tools. | Assist API |

### AI Task Options

AI Task entities support the same configuration options as conversation agents (except Prompt and LLM APIs):

- **Generate Data**: Returns structured JSON data based on your schema. Uses the configured chat model with JSON schema validation.
- **Generate Image**: Creates images using `grok-2-image` model based on text prompts. Returns base64-encoded image data (JPEG or PNG).

When configuring an AI Task entity, you can choose any model, but `grok-2-image` is required for image generation tasks.

## � Usage Examples

### Conversation Agent

Use the conversation agent in Home Assistant's Assist:

1. Go to **Settings → Voice assistants → Assist**
2. Select your xAI Conversation agent
3. Start chatting! Try:
   - "What's the weather like today?"
   - "Turn on the living room lights"
   - "Create an automation to..."

### Structured Data Generation

Use the AI Task service to generate structured data:

```yaml
action: ai_task.generate_data
data:
  task_name: Count cats and dogs
  instructions: Count how many dogs and cats are in the image
  entity_id: ai_task.xai_ai_task
  structure:
    dogs:
      selector:
        number:
    cats:
      selector:
        number:
  attachments:
    media_content_id: media-source://ai_task/image/my_pet_photo.jpg
    media_content_type: image/jpeg
```

Returns:
```yaml
conversation_id: 01K6NX2SKDF31DTGNS8GCXPBKK
data:
  dogs: 1
  cats: 1
```

You can use various selector types in the structure:
- `number` - For numeric values
- `text` - For text strings
- `boolean` - For true/false values
- `select` - For dropdown selections
- And more Home Assistant selectors

### Image Generation

Generate images using the AI Task service:

```yaml
service: ai_task.generate_image
target:
  entity_id: ai_task.xai_ai_task
data:
  prompt: "A futuristic smart home with holographic displays and ambient lighting"
```

**Note**: For image generation, ensure your AI Task entity is configured to use the `grok-2-image` model.

### Using Live Search

Enable live search for up-to-date information:

1. Configure your conversation or AI task entity
2. Uncheck "Use recommended settings"
3. Enable "Live search"
4. Set "Max search results" (1-50)
5. Ask questions requiring current data:
   - "What are the latest tech news?"
   - "Who won the game last night?"

### Reasoning Effort

For complex tasks with reasoning models (`grok-4`, `grok-3`, etc.):

1. Configure your entity with a reasoning model
2. Set reasoning effort to "high" for complex problems
3. Ask complex questions:
   - "Analyze my energy usage patterns and suggest optimizations"
   - "Help me debug why my automation isn't working"

## �🛠️ Development & Testing

- Run `./scripts/develop` to spin up a Home Assistant instance with this integration for manual testing.
- Run `./scripts/lint` before committing to ensure Home Assistant style checks pass.
- Project dependencies are listed in `requirements.txt`.

## ❓ Troubleshooting

- **`cannot_connect` error during setup** – confirm your API key is valid and has Grok access.
- **Slow or missing answers** – disable live search to isolate network latency, or lower max tokens for shorter replies.
- Check Home Assistant logs (`config/home-assistant.log`) for detailed integration traces.

Enjoy chatting with Grok from your smart home! 🏠🤖

