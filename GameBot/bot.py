# Discord GameBot class
# Matthew Kroesche

import discord
import os




class GameBot(discord.Client):


    def __init__(self, game_classes, debug=False):
        discord.Client.__init__(self)
        self.games = [cls(self) for cls in game_classes]
        self.main_channel = None # The default channel to post messages in
        self.last_ping = None # Keep a delay on pings in #off-topic so they don't flood it
        self.DEBUG = debug
        self.connected = False
        

    async def on_ready(self):
        # Find the main channel
        if self.main_channel is None:
            self.main_channel = discord.utils.get(self.get_all_channels(), id=int(os.getenv('GAMEBOT_DEFAULT_CHANNEL')))
        if (not self.connected) or any([game.running for game in self.games]):
            await self.main_channel.send('%s is now online' % self.user.mention)
            self.connected = True
            for game in self.games:
                await game.setup()


    async def on_message(self, message):
        # Top-level coroutine to reply to bot commands
        # This bot does not reply to itself
        if message.author == self.user:
            return
        # Find the main channel
        if self.main_channel is None:
            self.main_channel = discord.utils.get(self.get_all_channels(), id=int(os.getenv('GAMEBOT_DEFAULT_CHANNEL')))
        # Figure out which game, if any, the message is referring to
        content = message.content.lower()
        for game in self.games:
            if content.startswith(game.prefix + ' '):
                command = content.split(None, 2)[1]
                if command in game.cmd_lookup:
                    await game.cmd_lookup[command](message)


    def run(self):
        # Run the GameBot
        discord.Client.run(self, os.getenv('GAMEBOT_TOKEN'))
