[English](README.md) | [简体中文](README_zh.md)

# llm-discord-bot

A Discord chatbot that replies to @mentions via LLM APIs (DeepSeek, MiMo, and
other OpenAI-compatible providers) with conversation context.

Supports per-channel LLM model switching (`/switch_llm`) and character prompt
profiles (`/switch_prompt`).

## Prerequisites

- Python 3.12+
- LLM provider API key (DeepSeek / MiMo / any OpenAI-compatible API)
- A registered Discord Bot

## Installation

### 1. Clone the repository

```bash
git clone git@github.com:A1pha8977/llm-discord-bot.git
cd llm-discord-bot
```

### 2. Create a virtual environment

**Windows (PowerShell):**
```powershell
python -m venv .venv
.venv\Scripts\activate
```

**macOS / Linux:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

For development (includes linter, type checker):

```bash
pip install -r requirements-dev.txt
```

## Configuration

All configuration files are validated by `validate_all()` at startup.
Malformed configs cause an immediate error.

### 1. Create the `.env` file

```env
DISCORD_BOT_TOKEN=your_discord_bot_token
DEEPSEEK_API_KEY=sk-your-deepseek-api-key
# MIMO_API_KEY=your-mimo-api-key
```

API keys use the provider name in uppercase with `_API_KEY` suffix.
Example: `deepseek` → `DEEPSEEK_API_KEY`.

### 2. Create `config/llm_providers.yaml`

Defines LLM providers with model parameters (base_url, model_name, temperature, etc.).

```bash
cp config/llm_providers.example.yaml config/llm_providers.yaml
# Edit llm_providers.yaml
```

### 3. Create `config/llm_character.yaml`

Defines character prompt profiles (switchable per channel).

```bash
cp config/llm_character.example.yaml config/llm_character.yaml
# Edit llm_character.yaml
```

### 4. Create `config/bot.yaml`

Bot global defaults, including per-tool enable/disable and
global rate limiting.

```bash
cp config/bot.example.yaml config/bot.yaml
# Edit bot.yaml
```

Optional `enabled_tools` field — a mapping of tool name to `true`/`false`.
Only tools listed with `true` are available to the LLM; unlisted or
`false` tools are hidden from the LLM entirely.  Omit the key to keep
all tools enabled.

```yaml
enabled_tools:
  Tavilysearch: true   # web search enabled
  extract: true         # web content extraction enabled
  random: false         # random number tool disabled
  time: true            # time tool enabled
```

> `llm_providers.yaml`, `llm_character.yaml`, and `bot.yaml` are gitignored.
> Copy from `.example.yaml` and configure per deployment.

Global rate limiting controls LLM @mention call frequency via
`rate_limit` in `config/bot.yaml`.  At least one of `max_requests`
or `max_tokens` must be non-zero.

```yaml
rate_limit:
  max_requests: 50         # max API calls per window (0 = unlimited)
  max_tokens: 100000       # max tokens per window (0 = unlimited)
  window_seconds: 3600     # time window in seconds
  max_concurrency: 1       # max simultaneous LLM calls
```

| Field | Description |
|-------|-------------|
| `max_requests` | Max @mention calls per window (0 = unlimited) |
| `max_tokens` | Max cumulative tokens per window (0 = unlimited) |
| `window_seconds` | Time window length in seconds |
| `max_concurrency` | Max simultaneous LLM API calls |

When exceeded, the bot replies with the limit type and retry time.

Command permission management via `permission_levels` and `command_permissions`
in `config/bot.yaml`.

**Permission levels** (ordered high -> low):

| Level | Value | Description |
|-------|-------|-------------|
| owner | 4 | Equivalent to bot application owner |
| admin | 3 | Server administrators |
| user  | 2 | Trusted regular users |
| guest | 1 | Default for unrecognised users |
| block | 0 | Explicitly banned -- overrides everything |

`permission_levels` assigns user IDs to levels:

```yaml
permission_levels:
  users:
    owner: []
    admin: []
    user:  []
    guest: []
    block: []
  default_level: user
  min_context_level: guest
```

`command_permissions` sets the minimum level required per command.
Unlisted commands default to `guest` (everyone allowed).

```yaml
command_permissions:
  halt:
    min_level: owner
```

| Field | Description |
|-------|-------------|
| `users` | Maps each level to a list of Discord user snowflake IDs |
| `default_level` | Level assigned to users not listed in any level |
| `min_context_level` | Minimum level to appear in LLM conversation context |
| `commands.<name>.min_level` | Minimum level required to invoke a command |

### 5. (Optional) Edit `config/llm_base_prompt.yaml`

System prompt for the LLM: output format, scenario, comprehension rules, etc.
The default is ready to use.

## Running

```bash
python main.py
```

## Commands

| Command | Description |
|------|------|
| `@bot <message>` | Chat with the LLM |
| `/switch_llm <key>` | Switch the LLM model for the current channel |
| `/switch_llm` | List available LLM models |
| `/switch_prompt <profile>` | Switch the character prompt for the current channel |
| `/switch_prompt` | List available character profiles |
| `/usage` | View cumulative token usage |
| `/ping` | Return the server time |
| `/echo <text>` | Echo back the provided text |
| `/dice <n> ...` | Roll dice with N faces |
| `/whoami` | Show your display name |
| `/clear_context` | Clear conversation context for the current channel |
| `/halt` | Shut down the bot (configurable permission) |

## Tool Calling

The LLM can autonomously invoke the following tools for real-time data:

| Tool | Description |
|------|------|
| `Tavilysearch` | Web search for real-time information |
| `extract` | Extract readable text from web pages (text-only) |
| `random` | Generate random numbers (dice, draw lots, etc.) |
| `time` | Get the current date and time |

The LLM decides whether to call tools based on the user's question.
Multiple tools can be chained (e.g., search → extract page content → answer).

Individual tools can be disabled via `enabled_tools` in
`config/bot.yaml`.  Disabled tools are hidden from the LLM and won't
appear in the schema.

## Guild Whitelist

Configure `whitelist_guilds` in `config/bot.yaml` to restrict which Discord
servers the bot can join:

```yaml
whitelist_guilds: [123456789, 987654321]  # Allowed guild IDs
whitelist_guilds: []                       # Empty = no restriction
```

The bot will automatically leave any non-whitelisted guild.

## Project Structure

```
llm-discord-bot/
├── requirements.txt                # Runtime dependencies
├── requirements-dev.txt            # Development dependencies
├── main.py                         # Entry point
├── my_bot.py                       # Bot assembly
├── cogs/
│   ├── general_cog.py              # General-purpose commands
│   ├── llm_cog.py                  # LLM chat logic + per-channel state
│   └── guild_whitelist_cog.py      # Guild whitelist enforcement
├── services/
│   ├── chat_engine.py              # ChatEngine — formatting + LLM orchestration
│   ├── llm.py                      # LLMClient — OpenAI-compatible API wrapper
│   ├── llms.py                     # LLMClientFactory — batch client creation
│   ├── rate_limiter.py             # RateLimiter — request count + token tracking
│   └── tools/
│       ├── registry.py             # ToolRegistry — registration & schema generation
│       ├── random_tool.py          # Random number tool
│       ├── tavily_search.py        # Web search (Tavily API)
│       ├── time_tool.py            # Time query tool
│       └── extract_tool.py         # Web content extraction (trafilatura)
├── utils/
│   ├── config.py                   # Config loading & validate_all()
│   ├── logging.py                  # Logging setup
│   └── permissions.py              # Command permission enforcement
├── tests/
│   ├── test_rate_limiter.py         # RateLimiter unit tests
│   ├── test_registry.py            # ToolRegistry unit tests
│   ├── test_chat_engine.py         # ChatContext & ChatMessage unit tests
│   └── test_permissions.py          # Permission system unit tests
├── config/
│   ├── llm_base_prompt.yaml        # System prompt
│   ├── llm_character.yaml          # Character prompts (gitignored)
│   ├── llm_providers.yaml          # LLM providers (gitignored)
│   ├── bot.yaml                    # Bot defaults (gitignored)
│   ├── llm_character.example.yaml
│   ├── llm_providers.example.yaml
│   ├── bot.example.yaml
│   └── bot_whitelist.example.yaml
└── logs/
```
