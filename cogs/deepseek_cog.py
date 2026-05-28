from discord.ext import commands
from services.deepseek import get_deep_seek_client


MAX_CONTEXT_TOKENS = 3000

def _estimate_tokens(messages: list[dict]) -> int:
    return sum(len(str(m.get("content", ""))) for m in messages) // 4


class DeepSeekCog(commands.Cog):

    def __init__(self):
        self.llm_client = get_deep_seek_client()
        self.contexts: dict[int, list[dict]] = {} #TODO

    async def cog_load(self) -> None:
        return await super().cog_load()

    @commands.command()
    async def ask(self, ctx: commands.Context, *, prompt: str):
        channel_id = ctx.channel.id
        user_id = ctx.author.id
        user_name = ctx.author.display_name

        # await self._maybe_compress(channel_id) TODO: 需要更好的压缩逻辑

        async with ctx.typing():
            try:
                response = await self.llm_client.chat_text(
                    messages=[
                        {"role": "system", "content": "You are a helpful assistant."},
                        {"role": "user", "content": prompt}
                    ]
                    # + self.contexts[channel_id],  # type: ignore[arg-type] TODO: 注入上下文
                )
            except Exception as e:
                # TODO: pop from context when enabled
                await ctx.reply(f"DeepSeek API 错误: {e}")
                return

        # self.contexts[channel_id].append({"role": "assistant", "content": response})

        await ctx.reply(response)


    async def _maybe_compress(self, channel_id: int):
        msgs = self.contexts[channel_id]
        if _estimate_tokens(msgs) < MAX_CONTEXT_TOKENS:
            return
        if len(msgs) < 6:
            return

        recent = msgs[-4:]
        old = msgs[:-4]

        try:
            summary = await self.llm_client.compress(old)  # type: ignore[arg-type]
        except Exception:
            return

        self.contexts[channel_id] = [
            {
                "role": "user",
                "content": f"[之前的对话摘要]: {summary}",
            }
        ] + recent

    @staticmethod
    def _split_message(text: str, limit: int = 2000) -> list[str]:
        chunks = []
        while len(text) > limit:
            split_at = text.rfind("\n", 0, limit)
            if split_at == -1:
                split_at = limit
            chunks.append(text[:split_at])
            text = text[split_at:].lstrip()
        if text:
            chunks.append(text)
        return chunks
