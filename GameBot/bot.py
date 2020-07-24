# Discord GameBot class
# Matthew Kroesche

import discord
import os
import re
import datetime
import asyncio

from GameBot.game import PING_DELAY

ONLINE_NOTIFS = False # Disable these for now because everyone keeps griping about them
DAD_JOKES = True # Disable these if you value your sanity




class GameBot(discord.Client):


    def __init__(self, game_classes, debug=False):
        discord.Client.__init__(self)
        self.games = [cls(self) for cls in game_classes]
        self.main_channels = {}
        self.ping_channels = {}
        self.last_ping = {} # Keep a delay on pings so they don't flood the channel
        self.DEBUG = debug
        self.connected = False
        self.muted = []


    def init_channels(self):
        # Find the #game-corner and #game-talk channels
        for guild in self.guilds:
            if guild.id not in self.main_channels:
                channel = (discord.utils.get(self.get_all_channels(), guild=guild, name='game-corner') or \
                           discord.utils.get(self.get_all_channels(), guild=guild, name='general') or \
                           discord.utils.get(self.get_all_channels(), guild=guild))
                self.main_channels[guild.id] = channel
            if guild.id not in self.ping_channels:
                channel = discord.utils.get(self.get_all_channels(), guild=guild, name='game-talk')
                self.ping_channels[guild.id] = channel
                self.last_ping[guild.id] = None
        

    async def on_ready(self):
        self.init_channels()
        if (not self.connected) or any([game.running for game in self.games]):
            for channel in self.main_channels.values():
                if channel and ONLINE_NOTIFS:
                    await channel.send('%s is now online' % self.user.mention)
            if not self.connected:
                for id, channel in self.ping_channels.items():
                    if channel:
                        if self.last_ping[id] is None:
                            # Find the last ping if any
                            now = datetime.datetime.utcnow()
                            async for message in channel.history(after = now - PING_DELAY, oldest_first=False):
                                if message.author == self.user:
                                    # The only reason we ever post in #game-talk is to ping.
                                    self.last_ping[id] = message.created_at
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
        matching_games = []
        for game in self.games:
            if content.startswith(game.prefix + ' '):
                matching_games.append(game)
        # First, figure out if we're in the same channel as any of these games
        if matching_games:
            matching_game = None
            for game in matching_games:
                if game.main_channel == message.channel:
                    matching_game = game
                    break
            else:
                # Next, figure out if we're a player in any of these games
                for game in matching_games:
                    if game.find_player(message.author):
                        matching_game = game
                        break
                else:
                    # Next, figure out if there's a game on the same server as this one
                    for game in matching_games:
                        if game.main_channel and (message.channel.type != discord.ChannelType.private) and (game.main_channel.guild == message.channel.guild):
                            matching_game = game
                            break
                    else:
                        # Finally, figure out if this user has a server in common with this game (if this is a DM)
                        if message.channel.type == discord.ChannelType.private:
                            for game in matching_games:
                                if game.main_channel and (message.author in game.main_channel.guild.members):
                                    matching_game = game
                                    break
                            else:
                                matching_game = matching_games[0]
                        else:
                            matching_game = matching_games[0]
            # Invoke the command if we can find it
            if matching_game:
                command = content.split(None, 2)[1]
                if command in matching_game.cmd_lookup:
                    await matching_game.cmd_lookup[command](message)
        # If we're muted, delete this message
        for user, game in self.muted:
            if (user == message.author) and (game.main_channel == message.channel):
                await message.delete()
                break
        # Dad joke replies
        if DAD_JOKES:
            await self.dad_joke_reply(message)



    async def dad_joke_reply(self, message):
        if message.content.lower().startswith('i\'m '):
            text = message.content[4:]
        elif message.content.lower().startswith('im '):
            text = message.content[3:]
        else:
            text = ''
        if text:
            text = re.split(r'[.,:;?!]', text)[0]
            await message.channel.send('Hi %s, I\'m %s.' % (text, self.user.mention))



    def run(self):
        # Run the GameBot
        discord.Client.run(self, os.getenv('GAMEBOT_TOKEN'))
