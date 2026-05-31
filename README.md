# llm-discord-bot

一个 Discord 聊天机器人，被 @ 时通过 LLM API 生成带上下文的回复。
支持 DeepSeek、MiMo 等 OpenAI 兼容接口。

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

## 配置

### 1. 创建 `.env` 文件

```env
DISCORD_BOT_TOKEN=your_discord_bot_token
DEEPSEEK_API_KEY=sk-your-deepseek-api-key

# 若使用 MiMo，替换为：
# MIMO_API_KEY=your-mimo-api-key
```

### 2. 编辑 `config/llm_base_prompt.yaml`

配置 AI 的系统行为：输出格式、场景、对话规则等。

### 3. （可选）编辑 `config/llm_character.yaml`

配置 AI 的角色扮演设定。

## 运行

```bash
python main.py
```

## 项目结构

```
llm-discord-bot/
├── main.py
├── my_bot.py
├── cogs/
│   ├── general_cog.py
│   └── llm_cog.py
├── services/
│   ├── llm.py
│   ├── deepseek.py
│   ├── mimo.py
│   └── content.py
├── utils/
│   ├── config.py
│   └── logging.py
├── config/
│   ├── llm_base_prompt.yaml
│   ├── llm_character.yaml
│   └── tools.json
└── logs/
```