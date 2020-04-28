# Discord GameBot class
# Matthew Kroesche

import discord
import os
import datetime
import asyncio

from GameBot.game import PING_DELAY




class GameBot(discord.Client):


    def __init__(self, game_classes, debug=False):
        discord.Client.__init__(self)
        self.games = [cls(self) for cls in game_classes]
        self.main_channel = None # The default channel to post messages in
        self.ping_channel = None # The default channel to ping
        self.last_ping = None # Keep a delay on pings in #off-topic so they don't flood it
        self.DEBUG = debug
        self.connected = False
        self.muted = []


    def init_channels(self):
        # Find the #game-corner and #game-talk channels
        if self.main_channel is None:
            self.main_channel = discord.utils.get(self.get_all_channels(), id=int(os.getenv('GAMEBOT_DEFAULT_CHANNEL')))
        if self.ping_channel is None:
            self.ping_channel = discord.utils.get(self.get_all_channels(), id=int(os.getenv('GAMEBOT_PING_CHANNEL')))
        

    async def on_ready(self):
        self.init_channels()
        if (not self.connected) or any([game.running for game in self.games]):
            await self.main_channel.send('%s is now online' % self.user.mention)
            if not self.connected:
                if self.last_ping is None:
                    # Find the last ping if any
                    now = datetime.datetime.utcnow()
                    async for message in self.ping_channel.history(after = now - PING_DELAY, oldest_first=False):
                        if message.author == self:
                            # The only reason we ever post in #game-talk is to ping.
                            self.last_ping = message.created_at
                            break
                await asyncio.gather(*[game.setup() for game in self.games])
                self.connected = True


    async def on_message(self, message):
        # Top-level coroutine to reply to bot commands
        # This bot does not reply to itself
        if message.author == self.user:
            return
        self.init_channels()
        # Figure out which game, if any, the message is referring to
        content = message.content.lower()
        for game in self.games:
            if content.startswith(game.prefix + ' '):
                command = content.split(None, 2)[1]
                if command in game.cmd_lookup:
                    await game.cmd_lookup[command](message)
                    break
        # If we're muted, delete this message
        if message.channel == self.main_channel:
            if any([muted.user == message.author for muted in self.muted]):
                await message.delete()


    def run(self):
        # Run the GameBot
        discord.Client.run(self, os.getenv('GAMEBOT_TOKEN'))
