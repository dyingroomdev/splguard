from __future__ import annotations

import logging
from datetime import datetime

import discord
from discord import app_commands
from discord.ext import commands

from ..config import settings

logger = logging.getLogger(__name__)


class DiscordBotRunner:
    """Lightweight Discord bot that mirrors core SPL Guard messaging."""

    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.members = True
        self.bot = commands.Bot(command_prefix="/", intents=intents)
        self._token = settings.discord_bot_token
        self._guild_id = settings.discord_guild_id
        self._guild_object = discord.Object(id=self._guild_id) if self._guild_id else None
        self._welcome_channel_id = settings.discord_welcome_channel_id
        self._admin_ids = set(settings.discord_admin_ids)
        self._presale_price = "0.1 SOL = 75 018.75 TDL"
        self._token_logo_url = (
            "https://media.discordapp.net/attachments/1437749931187245070/"
            "1437778658864402573/logo_tdl.png?ex=69147b38&is=691329b8&hm="
            "370d4d1f9e9f6f5441c107cc654762b493f840ab464a6130ede7ac096a75a68d&="
            "&format=webp&quality=lossless"
        )
        self._presale_link = "https://presale.splshield.com/"
        self._channel_mentions = {
            "rules": self._channel_mention(settings.discord_rules_channel_id),
            "presale": self._channel_mention(settings.discord_presale_info_channel_id),
            "announcement": self._channel_mention(settings.discord_announcement_channel_id),
            "roadmap": self._channel_mention(settings.discord_roadmap_channel_id),
        }
        self._admin_role_id = settings.discord_say_admin_role_id

        self._register_events()
        self._register_commands()

    def _register_events(self) -> None:
        @self.bot.event
        async def on_ready() -> None:  # pragma: no cover - Discord runtime callback
            logger.info("discord_bot_ready", extra={"user": str(self.bot.user)})
            if self._guild_id:
                logger.info("discord_guild_registered", extra={"guild_id": self._guild_id})

        @self.bot.event
        async def setup_hook() -> None:  # pragma: no cover - Discord runtime callback
            if self._guild_object:
                await self.bot.tree.sync(guild=self._guild_object)
            else:
                await self.bot.tree.sync()

        @self.bot.event
        async def on_member_join(member: discord.Member) -> None:  # pragma: no cover
            if self._guild_id and member.guild.id != self._guild_id:
                return
            if not self._welcome_channel_id:
                return
            await self._send_welcome_message(member)

    def _register_commands(self) -> None:
        @self.bot.tree.command(
            name="sale",
            description="Show current presale details.",
            guild=self._guild_object,
        )
        async def sale(interaction: discord.Interaction) -> None:
            if self._guild_id and interaction.guild_id != self._guild_id:
                await interaction.response.send_message(
                    "This command is not available in this server.", ephemeral=True
                )
                return
            embed = self._build_sale_embed()
            view = self._build_sale_view()
            await interaction.response.send_message(embed=embed, view=view)

        @self.bot.tree.command(
            name="ca",
            description="Share the TDL contract address.",
            guild=self._guild_object,
        )
        async def ca(interaction: discord.Interaction) -> None:
            if self._guild_id and interaction.guild_id != self._guild_id:
                await interaction.response.send_message(
                    "This command is not available in this server.", ephemeral=True
                )
                return
            mint = settings.tdl_mint
            if not mint:
                await interaction.response.send_message(
                    "The TDL mint address is not configured.", ephemeral=True
                )
                return
            embed = self._build_contract_embed(mint)
            view = self._build_contract_view(mint)
            await interaction.response.send_message(embed=embed, view=view)

        @self.bot.tree.command(
            name="say",
            description="Admin broadcast to a selected text channel.",
            guild=self._guild_object,
        )
        @app_commands.describe(
            channel="Target text channel",
            message="Message to send (set blank to use the rich editor).",
            attachment="Optional image or file to include in the post.",
            use_embed="Render the text inside a styled embed.",
            use_modal="Open a rich text editor (multi-line) before sending.",
        )
        async def say(
            interaction: discord.Interaction,
            channel: discord.TextChannel,
            message: str | None = None,
            attachment: discord.Attachment | None = None,
            use_embed: bool = False,
            use_modal: bool = False,
        ) -> None:
            if not self._is_admin(interaction):
                await interaction.response.send_message(
                    "You do not have permission to run this command.", ephemeral=True
                )
                return
            if self._guild_id and channel.guild.id != self._guild_id:
                await interaction.response.send_message(
                    "This channel is not part of the configured SPL Shield server.",
                    ephemeral=True,
                )
                return
            text = message or ""
            if use_modal or (not text.strip() and attachment is None):
                view = _BroadcastModalLauncher(
                    runner=self,
                    channel=channel,
                    attachment=attachment,
                    use_embed=use_embed,
                    initial_text=text,
                    invoker_id=interaction.user.id,
                )
                await interaction.response.send_message(
                    "Click **Open Editor** to paste your formatted message.",
                    ephemeral=True,
                    view=view,
                )
                return
            await interaction.response.defer(ephemeral=True)
            try:
                await self._dispatch_broadcast(
                    channel=channel,
                    text=text,
                    attachment=attachment,
                    use_embed=use_embed,
                )
            except ValueError as exc:
                await interaction.followup.send(str(exc), ephemeral=True)
                return
            except discord.DiscordException as exc:
                await interaction.followup.send(
                    f"Discord rejected the broadcast: {exc}", ephemeral=True
                )
                return
            await interaction.followup.send(
                f"Posted your message to {channel.mention}.", ephemeral=True
            )

    async def start(self) -> None:
        if not self._token:
            logger.info("discord_bot_disabled", extra={"reason": "token not provided"})
            return
        await self.bot.start(self._token)

    async def stop(self) -> None:
        if self.bot.is_closed():
            return
        await self.bot.close()

    async def _send_welcome_message(self, member: discord.Member) -> None:
        if not self._welcome_channel_id:
            return
        channel = self.bot.get_channel(self._welcome_channel_id)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(self._welcome_channel_id)
            except discord.DiscordException as exc:  # pragma: no cover
                logger.warning("discord_welcome_channel_fetch_failed", extra={"error": str(exc)})
                return
        if isinstance(channel, (discord.TextChannel, discord.Thread)):
            content, embed = self._build_welcome_message(member)
            await channel.send(content, embed=embed)

    def _is_admin(self, interaction: discord.Interaction) -> bool:
        user = interaction.user
        if isinstance(user, discord.Member):
            if self._admin_role_id and any(role.id == self._admin_role_id for role in user.roles):
                return True
            if user.guild_permissions.administrator:
                return True
        if not self._admin_ids:
            return False
        return user.id in self._admin_ids

    def _build_welcome_message(self, member: discord.Member) -> tuple[str, discord.Embed]:
        rules = self._channel_mentions["rules"] or "#rules"
        presale = self._channel_mentions["presale"] or "#presale-info"
        announcement = self._channel_mentions["announcement"] or "#announcement"
        roadmap = self._channel_mentions["roadmap"] or "#roadmap"
        content = (
            f"👋 Welcome {member.mention} to **SPL Shield**!\n"
            f"Please read {rules} and don't forget to check out {presale}, "
            f"{announcement}, {roadmap}."
        )
        embed = discord.Embed(color=discord.Color.dark_teal())
        embed.set_image(
            url=(
                "https://media.discordapp.net/attachments/1437749931187245070/"
                "1437767523595456615/Cover_facebook.png?ex=691470da&is=69131f5a&hm="
                "27fa85a4d10ebed8726e5d2b93e7baef70de3b37d38623dc46633021a9f57437&="
                "&format=webp&quality=lossless"
            )
        )
        return content, embed

    def _build_sale_embed(self) -> discord.Embed:
        supply = settings.tdl_supply_display or "10 B TDL"
        mint = settings.tdl_mint or "Not set"
        embed = discord.Embed(
            title="💎 Token Essentials",
            color=discord.Color.from_str("#2BD4A2"),
            description="Presale is LIVE — secure your allocation before the cap hits.",
        )
        embed.set_thumbnail(url=self._token_logo_url)
        embed.add_field(
            name="Ends",
            value=f"**{self._format_datetime(settings.presale_end_iso)}**",
            inline=True,
        )
        embed.add_field(
            name="Presale Price",
            value=f"`{self._presale_price}`",
            inline=True,
        )
        embed.add_field(name="\u200b", value="\u200b", inline=False)
        utilities = [
            "**Ticker:** TDL",
            f"**Total Supply:** {supply}",
            f"**Contract Address:** `{mint}`",
        ]
        embed.add_field(name="💰 Token Utilities", value="\n".join(utilities), inline=False)
        embed.add_field(
            name="🚀 Presale Portal",
            value=f"[Join Now]({self._presale_link})",
            inline=False,
        )
        embed.set_footer(text="SPL Shield · Built for Safe Degens.")
        return embed

    def _build_sale_view(self) -> discord.ui.View:
        view = discord.ui.View()
        view.add_item(
            discord.ui.Button(
                label="Join Presale",
                url=self._presale_link,
                emoji="💎",
            )
        )
        return view

    def _build_contract_embed(self, mint: str) -> discord.Embed:
        explorer = f"https://solscan.io/token/{mint}"
        embed = discord.Embed(
            title="TDL Contract Address",
            description="Verified mint for SPL Shield’s TDL token.",
            color=discord.Color.from_str("#5C7CFA"),
        )
        embed.set_thumbnail(url=self._token_logo_url)
        embed.add_field(name="Mint", value=f"`{mint}`", inline=False)
        embed.add_field(name="Explorer", value=f"[View on Solscan]({explorer})", inline=False)
        embed.set_footer(text="Share this mint only. Beware of spoofed contracts.")
        return embed

    def _build_contract_view(self, mint: str) -> discord.ui.View:
        explorer = f"https://solscan.io/token/{mint}"
        view = discord.ui.View()
        view.add_item(
            discord.ui.Button(
                label="Open on Solscan",
                url=explorer,
                emoji="🧾",
            )
        )
        return view

    @staticmethod
    def _format_datetime(value: str | None) -> str:
        if not value:
            return "TBA"
        try:
            dt = datetime.fromisoformat(value)
        except ValueError:
            return value
        label = dt.strftime("%b %d, %Y")
        return label

    @staticmethod
    def _channel_mention(channel_id: int | None) -> str | None:
        if not channel_id:
            return None
        return f"<#{channel_id}>"

    @staticmethod
    def _is_image_filename(filename: str | None) -> bool:
        if not filename:
            return False
        lowered = filename.lower()
        return lowered.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp"))

    @staticmethod
    def _build_say_embed(text: str) -> discord.Embed:
        embed = discord.Embed(
            description=text or "\u200b",
            color=discord.Color.from_str("#5865F2"),
        )
        embed.set_author(name="SPL Shield Broadcast")
        embed.set_footer(text="SPL Shield · Official Updates")
        return embed

    async def _dispatch_broadcast(
        self,
        channel: discord.TextChannel,
        text: str,
        attachment: discord.Attachment | None,
        use_embed: bool,
    ) -> None:
        message_text = text.replace("\r\n", "\n")
        trimmed = message_text.strip()
        if not trimmed and attachment is None:
            raise ValueError("Provide a message or attach a file to broadcast.")
        if len(message_text) > 1900:
            raise ValueError("Message too long; please keep it below 1,900 characters.")
        file = None
        if attachment is not None:
            file = await attachment.to_file()
        send_kwargs: dict[str, object] = {}
        embed: discord.Embed | None = None
        if use_embed:
            embed = self._build_say_embed(message_text)
            send_kwargs["embed"] = embed
        elif message_text:
            send_kwargs["content"] = message_text
        if file:
            if embed and self._is_image_filename(file.filename):
                embed.set_image(url=f"attachment://{file.filename}")
            send_kwargs["file"] = file
        await channel.send(**send_kwargs)


class _BroadcastModal(discord.ui.Modal, title="SPL Shield Broadcast"):
    def __init__(
        self,
        runner: DiscordBotRunner,
        channel: discord.TextChannel,
        attachment: discord.Attachment | None,
        use_embed: bool,
        initial_text: str,
    ) -> None:
        super().__init__()
        self._runner = runner
        self._channel = channel
        self._attachment = attachment
        self._use_embed = use_embed
        self.message_input = discord.ui.TextInput(
            label="Message",
            style=discord.TextStyle.paragraph,
            required=False,
            default=initial_text,
            placeholder="Paste your richly formatted text here…",
        )
        self.add_item(self.message_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        text = self.message_input.value or ""
        if not text.strip() and self._attachment is None:
            await interaction.response.send_message(
                "Please provide text in the editor or attach a file before submitting.",
                ephemeral=True,
            )
            return
        await interaction.response.defer(ephemeral=True)
        try:
            await self._runner._dispatch_broadcast(
                channel=self._channel,
                text=text,
                attachment=self._attachment,
                use_embed=self._use_embed,
            )
        except ValueError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return
        except discord.DiscordException as exc:
            await interaction.followup.send(
                f"Discord rejected the broadcast: {exc}", ephemeral=True
            )
            return
        await interaction.followup.send(
            f"Posted your message to {self._channel.mention}.", ephemeral=True
        )


class _BroadcastModalLauncher(discord.ui.View):
    def __init__(
        self,
        runner: DiscordBotRunner,
        channel: discord.TextChannel,
        attachment: discord.Attachment | None,
        use_embed: bool,
        initial_text: str,
        invoker_id: int,
    ) -> None:
        super().__init__(timeout=300)
        self._runner = runner
        self._channel = channel
        self._attachment = attachment
        self._use_embed = use_embed
        self._initial_text = initial_text
        self._invoker_id = invoker_id

    @discord.ui.button(label="Open Editor", style=discord.ButtonStyle.primary)
    async def open_editor(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        if interaction.user.id != self._invoker_id:
            await interaction.response.send_message(
                "Only the admin who ran the command can open this editor.", ephemeral=True
            )
            return
        modal = _BroadcastModal(
            runner=self._runner,
            channel=self._channel,
            attachment=self._attachment,
            use_embed=self._use_embed,
            initial_text=self._initial_text,
        )
        await interaction.response.send_modal(modal)
