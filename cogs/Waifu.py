import discord
from discord.ext import commands, tasks
import aiohttp
import asyncio
import json
import time
from typing import Optional, Dict
from discord.ui import View, Button, Modal, TextInput

class ConfigModal(Modal):
    def __init__(self):
        super().__init__(title="Auto-Waifu Configuration")
        self.channel_id = TextInput(label="Channel ID", placeholder="Enter channel ID")
        self.add_item(self.channel_id)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        cog = interaction.client.get_cog("Waifu")
        await cog.setAutoWaifu(interaction, self.channel_id.value)

class WaifuView(View):
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="Auto-Waifu Setup", style=discord.ButtonStyle.green, custom_id="autoWaifuAdd")
    async def autoWaifuAdd(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = ConfigModal()
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Auto-Waifu Delete", style=discord.ButtonStyle.red, custom_id="autoWaifuDel")
    async def autoWaifuDel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await self.cog.delAutoWaifu(interaction)

    @discord.ui.button(label="Auto-Waifu Config", style=discord.ButtonStyle.blurple, custom_id="autoWaifuConfig")
    async def autoWaifuConfig(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await self.cog.configAutoWaifu(interaction)

class Waifu(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.waifu_channels: Dict[str, str] = {}
        self.session: Optional[aiohttp.ClientSession] = None
        self.image_cache = []
        self.cache_size = 50
        self.last_save = time.time()
        self.save_interval = 300 
        self.api_base_url = 'https://api.waifu.pics/sfw/waifu'
        self.rate_limit = 1
        self.last_request = 0
        self.view = WaifuView(self)

    async def initSession(self):
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()

    async def cog_load(self):
        await self.initSession()
        self.loadChannels()
        self.auto_sendWaifu.start()
        self.fill_cache.start()
        self.bot.add_view(self.view)

    async def cog_unload(self):
        self.auto_sendWaifu.cancel()
        self.fill_cache.cancel()
        if self.session:
            await self.session.close()
        self.saveChannels()

    def loadChannels(self):
        try:
            with open('waifu.json', 'r') as f:
                self.waifu_channels = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            self.waifu_channels = {}

    def saveChannels(self):
        with open('waifu.json', 'w') as f:
            json.dump(self.waifu_channels, f)

    async def fetchImages(self):
        current_time = time.time()
        if current_time - self.last_request < 1 / self.rate_limit:
            await asyncio.sleep(1 / self.rate_limit - (current_time - self.last_request))
        
        async with self.session.get(self.api_base_url) as response:
            self.last_request = time.time()
            if response.status == 200:
                data = await response.json()
                return data['url']
        return None

    @tasks.loop(seconds=30)
    async def auto_sendWaifu(self):
        if not self.waifu_channels:
            return
        image_url = await self.fetchImages()
        if image_url:
            embed = self.waifuEmbed(image_url) 
            tasks = []
            for guild_id, channel_id in self.waifu_channels.items():
                channel = self.bot.get_channel(int(channel_id))
                if channel:
                    tasks.append(self.sendWaifu(channel, embed))
            
            await asyncio.gather(*tasks)

    @tasks.loop(minutes=1)
    async def fill_cache(self):
        needed_images = self.cache_size - len(self.image_cache)
        if needed_images <= 0:
            return
        tasks = [self.fetchImages() for _ in range(min(needed_images, 5))]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, str):
                self.image_cache.append(result)

    @auto_sendWaifu.before_loop
    @fill_cache.before_loop
    async def before_auto_sendWaifu(self):
        await self.bot.wait_until_ready()
        await self.initSession()

    def waifuEmbed(self, url):
        embed = discord.Embed(color=discord.Color.blurple())
        embed.set_image(url=url)
        return embed

    async def sendWaifu(self, channel, embed):
        try:
            message = await channel.send(embed=embed)
            await asyncio.gather(
                message.add_reaction('👍'),
                message.add_reaction('👎')
            )
        except discord.errors.Forbidden:
            pass

    async def setAutoWaifu(self, interaction: discord.Interaction, channel_id: str):
        guild_id = str(interaction.guild_id)
        try:
            channel = interaction.guild.get_channel(int(channel_id))
            if channel is None:
                await interaction.followup.send("❌ Invalid Channel ID Provided, Please Try Again!")
                return

            if guild_id in self.waifu_channels:
                await interaction.followup.send("❌ This Guild Already Has Auto-Waifu Enabled.")
                return

            self.waifu_channels[guild_id] = channel_id
            self.saveChannels()
            await interaction.followup.send(f"✅ Added Auto-Waifu For This Guild In {channel.mention}.")
        except ValueError:
            await interaction.followup.send("❌ Invalid Channel ID Provided, Please Try Again!")

    async def delAutoWaifu(self, interaction: discord.Interaction):
        guild_id = str(interaction.guild_id)
        if guild_id in self.waifu_channels:
            del self.waifu_channels[guild_id]
            self.saveChannels()
            await interaction.followup.send("")
        else:
            await interaction.followup.send("This guild doesn't have an auto-waifu channel set.")

    async def configAutoWaifu(self, interaction: discord.Interaction):
        guild_id = str(interaction.guild_id)
        if guild_id in self.waifu_channels:
            channel_id = self.waifu_channels[guild_id]
            channel = interaction.guild.get_channel(int(channel_id))
            if channel:
                await interaction.followup.send(f"Auto-waifu is currently enabled for channel: {channel.mention}")
            else:
                await interaction.followup.send("Auto-waifu is enabled, but the channel no longer exists.")
        else:
            await interaction.followup.send("Auto-waifu is not enabled for this guild.")

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    async def setup(self, ctx):
        await ctx.send("Setup your Auto-Waifu for this server!", view=self.view)

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction, user):
        if (user.bot or reaction.message.author != self.bot.user or 
            reaction.emoji not in ('👍', '👎')):
            return

        if reaction.emoji == '👎' and reaction.count > 5:
            try:    
                await reaction.message.delete()
                await reaction.message.channel.send("Image deleted due to negative feedback.")
            except (discord.errors.NotFound, discord.errors.Forbidden):
                pass

async def setup(bot):
    await bot.add_cog(Waifu(bot))
