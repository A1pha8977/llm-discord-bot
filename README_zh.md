[English](README.md) | [简体中文](README_zh.md)

# llm-discord-bot

一个 Discord 聊天机器人，被 @ 时通过 LLM API（DeepSeek / MiMo 等 OpenAI 兼容接口）
生成带对话上下文的回复。

支持按频道热切换 LLM 模型（`/switch_llm`）、角色扮演提示词（`/switch_prompt`）。

## 前置条件

- Python 3.12+
- LLM 服务商 API key（DeepSeek / MiMo / 其他兼容接口）
- 已注册的 Discord Bot

## 安装

### 1. 克隆仓库

```bash
git clone git@github.com:A1pha8977/llm-discord-bot.git
cd llm-discord-bot
```

### 2. 创建虚拟环境

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

### 3. 安装依赖

```bash
pip install -r requirements.txt
```

开发依赖（包含 linter、类型检查器）：

```bash
pip install -r requirements-dev.txt
```

## 配置

所有配置文件启动时由 `validate_all()` 校验，格式错误会立即报错。

### 1. 创建 `.env` 文件

```env
DISCORD_BOT_TOKEN=your_discord_bot_token
DEEPSEEK_API_KEY=sk-your-deepseek-api-key
# MIMO_API_KEY=your-mimo-api-key
```

API key 按提供商名大写加 `_API_KEY` 后缀。例：`deepseek` → `DEEPSEEK_API_KEY`。

### 2. 创建 `config/llm_providers.yaml`

定义 LLM 提供商及模型参数（base_url、model_name、temperature 等）。

```bash
cp config/llm_providers.example.yaml config/llm_providers.yaml
# 编辑 llm_providers.yaml
```

### 3. 创建 `config/llm_character.yaml`

定义角色扮演提示词（按频道切换）。

```bash
cp config/llm_character.example.yaml config/llm_character.yaml
# 编辑 llm_character.yaml
```

### 4. 创建 `config/bot.yaml`

Bot 全局默认值，包含工具启用/禁用配置和全局限流。

```bash
cp config/bot.example.yaml config/bot.yaml
# 编辑 bot.yaml
```

可选字段 `enabled_tools` — 工具名到 `true`/`false` 的映射。只有标记为
`true` 的工具才会对 LLM 可见；未列出或为 `false` 的工具将被完全隐藏。
省略此字段则所有工具默认启用。

```yaml
enabled_tools:
  Tavilysearch: true   # 启用联网搜索
  extract: true         # 启用网页提取
  random: false         # 禁用随机数工具
  time: true            # 启用时间工具
```

> `llm_providers.yaml`、`llm_character.yaml`、`bot.yaml` 被 `.gitignore` 忽略，
> 不进入版本控制。每个部署环境需从 `.example.yaml` 复制后独立配置。

全局限流通过 `config/bot.yaml` 中的 `rate_limit` 节控制 LLM
@mention 调用频率。`max_requests` 和 `max_tokens` 至少一项需大于 0。

```yaml
rate_limit:
  max_requests: 50         # 时间窗口内最大调用次数（0 = 不限）
  max_tokens: 100000       # 时间窗口内最大 token 数（0 = 不限）
  window_seconds: 3600     # 时间窗口长度（秒）
  max_concurrency: 1       # 最大同时 LLM 调用数
```

| 字段 | 说明 |
|------|------|
| `max_requests` | 时间窗口内最大调用次数（0 = 不限） |
| `max_tokens` | 时间窗口内最大累计 token 数（0 = 不限） |
| `window_seconds` | 时间窗口长度（秒） |
| `max_concurrency` | 最大同时 LLM API 调用数 |

超出限制时，Bot 会回复限制类型和重试时间。

命令权限管理通过 `config/bot.yaml` 的 `permission_levels` 和 `command_permissions` 配置。

**权限等级**（从高到低）：

| 等级 | 数值 | 说明 |
|------|------|------|
| owner | 4 | 最高权限，相当于 Bot 应用所有者 |
| admin | 3 | 服务器管理员 |
| user  | 2 | 受信任的普通用户 |
| guest | 1 | 未识别用户的默认等级 |
| block | 0 | 显式封禁，优先级高于一切 |

`permission_levels` 将用户 ID 分配到各等级：

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

`command_permissions` 设置每个命令所需的最低等级。
未列出的命令默认 `guest`（所有人可用）。

```yaml
command_permissions:
  halt:
    min_level: owner
```

| 字段 | 说明 |
|------|------|
| `users` | 每个等级对应的 Discord 用户 snowflake ID 列表 |
| `default_level` | 未在列表中出现的用户的默认等级 |
| `min_context_level` | 出现在 LLM 对话上下文中的最低等级 |
| `commands.<name>.min_level` | 调用命令所需的最低等级 |

### 5. （可选）编辑 `config/llm_base_prompt.yaml`

系统提示词：输出格式、场景、理解规则等。默认已可用。

## 运行

```bash
python main.py
```

## 命令

| 命令 | 说明 |
|------|------|
| `@bot <message>` | 与 LLM 对话 |
| `/switch_llm <key>` | 切换当前频道使用的 LLM 模型 |
| `/switch_llm` | 列出可用的 LLM 模型 |
| `/switch_prompt <profile>` | 切换当前频道的角色扮演 |
| `/switch_prompt` | 列出可用的角色预设 |
| `/usage` | 查看累计 token 使用量 |
| `/ping` | 返回服务器时间 |
| `/echo <text>` | 回声 |
| `/dice <n> ...` | 掷 n 面骰子 |
| `/whoami` | 显示你的名字 |
| `/clear_context` | 清除当前频道的对话上下文 |
| `/halt` | 关闭 Bot（权限可配置） |

## 工具调用

Bot 支持 LLM 自主调用以下工具获取实时数据：

| 工具 | 说明 |
|------|------|
| `Tavilysearch` | 联网搜索获取实时信息 |
| `extract` | 从网页提取正文内容（仅限文本页面） |
| `random` | 生成随机数（掷骰子、抽签等） |
| `time` | 获取当前日期和时间 |

LLM 会根据用户问题自动决定是否调用工具，多个工具可串联使用
（例如：搜索 → 提取网页正文 → 基于内容回答）。

各个工具可通过 `config/bot.yaml` 中的 `enabled_tools` 单独禁用。
禁用的工具对 LLM 不可见，不会出现在 schema 中。

## 服务器白名单

`config/bot.yaml` 中配置 `whitelist_guilds` 字段可限制 Bot 可加入的 Discord 服务器：

```yaml
whitelist_guilds: [123456789, 987654321]  # 允许的服务器 ID 列表
whitelist_guilds: []                       # 空列表 = 不限制
```

配置后 Bot 会拒绝加入未在列表中的服务器。

## 项目结构

```
llm-discord-bot/
├── requirements.txt                # 运行时依赖
├── requirements-dev.txt            # 开发依赖
├── main.py                         # 入口
├── my_bot.py                       # Bot 实例组装
├── cogs/
│   ├── general_cog.py              # 基础命令
│   ├── llm_cog.py                  # LLM 对话逻辑 + 频道状态管理
│   └── guild_whitelist_cog.py      # 服务器白名单管理
├── services/
│   ├── chat_engine.py              # ChatEngine — 核心引擎（格式化 + 调 LLM）
│   ├── llm.py                      # LLMClient — 底层 API 封装
│   ├── llms.py                     # LLMClientFactory — 按 YAML 批量构建客户端
│   ├── rate_limiter.py             # RateLimiter — 请求次数 + Token 跟踪
│   └── tools/
│       ├── registry.py             # ToolRegistry — 工具注册 & schema 生成
│       ├── random_tool.py          # 随机数工具
│       ├── tavily_search.py        # 联网搜索（Tavily API）
│       ├── time_tool.py            # 时间查询
│       └── extract_tool.py         # 网页正文提取（trafilatura）
├── utils/
│   ├── config.py                   # 配置加载 & validate_all()
│   ├── logging.py                  # 日志设置
│   └── permissions.py              # 命令权限管理
├── tests/
│   ├── test_rate_limiter.py         # RateLimiter 单元测试
│   ├── test_registry.py            # ToolRegistry 单元测试
│   ├── test_chat_engine.py         # ChatContext & ChatMessage 单元测试
│   └── test_permissions.py          # 权限系统单元测试
├── config/
│   ├── llm_base_prompt.yaml        # 系统提示词
│   ├── llm_character.yaml          # 角色提示词（本地，gitignored）
│   ├── llm_providers.yaml          # LLM 提供商（本地，gitignored）
│   ├── bot.yaml                    # Bot 默认值（本地，gitignored）
│   ├── llm_character.example.yaml
│   ├── llm_providers.example.yaml
│   ├── bot.example.yaml
│   └── bot_whitelist.example.yaml
└── logs/
```
