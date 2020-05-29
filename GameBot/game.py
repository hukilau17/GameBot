# Discord game base class
# Matthew Kroesche

import discord
import sys
import os
import io
import datetime
import traceback
import random
import asyncio

PING_DELAY = datetime.timedelta(hours=1) # One-hour delay for pinging #off-topic
VOTEKICK_MIN = 4 # Four votes required to force an inactive game to end
STARTING_DELAY = 60 * 20 # If the game is not started within 20 minutes of its creation time, delete it






class Game(object):

    # Define these in subclasses
    name = None
    prefix = None


    def __init__(self, bot):
        self.bot = bot
        self.owner = None # The player who started the game
        self.running = False # True if the game is currently ongoing
        self.main_channel = None
        self.cmd_lookup = {}
        self.players = []
        help_strings = []
        methods = dir(self)
        # Give global gb_* commands priority for snipping
        methods = [i for i in methods if i.startswith('gb_')] + [i for i in methods if not i.startswith('gb_')]
        for fname in methods:
            if not fname.startswith((self.prefix + '_', 'gb_')):
                continue
            func = getattr(self, fname)
            name = fname.split('_', 1)[1]
            self.cmd_lookup[name] = func
            if not ((func.__name__ == fname) and func.__doc__):
                continue
            snipsize = 1
            while name[:snipsize] in self.cmd_lookup:
                snipsize += 1
                if snipsize == len(name):
                    snipsize = 0
                    break
            if snipsize:
                self.cmd_lookup[name[:snipsize]] = func
                help_strings.append('%s __%s__%s: %s' % (self.prefix, name[:snipsize], name[snipsize:], func.__doc__))
            else:
                help_strings.append('%s %s: %s' % (self.prefix, name, func.__doc__))
        help_strings.sort()
        self.help = '**%s bot commands:**\n%s' % (self.name, '\n'.join(help_strings))
        self.starting_timer_task = None




    ##### Convenience functions that are called by bot commands #####


    async def askyesno(self, question, user, channel):
        # Ask a yes/no question.
        await channel.send(question + ' (Yes/No)')
        def check(m):
            return (m.channel == channel) and (m.author == user) and (m.content.lower().strip() in ('yes', 'no'))
        try:
            yesno = await self.bot.wait_for('message', check=check, timeout=10)
        except asyncio.TimeoutError:
            return False # Guess not, then
        return yesno.content.lower().strip() == 'yes'


    async def check_game(self, message):
        # Returns True if there is a game; else prints an error message and returns False
        if self.owner:
            return True
        await message.channel.send('There is no active game right now.')
        return False


    async def check_owner(self, message):
        # Returns True if there is a game and the person who sent this message created it; else prints an error message and returns False
        if (await self.check_game(message)):
            if self.owner.user == message.author:
                return True
            await message.channel.send('This game was created by %s. You do not have permission to modify it.' % self.owner.user.mention)
        return False
    

    async def check_running(self, message):
        # Returns True if there is a game and it has been started; else prints an error message and returns False
        if (await self.check_game(message)):
            if self.running:
                return True
            await message.channel.send('This game has not started yet.')
        return False
    

    async def check_not_running(self, message):
        # Returns True if there is a game and it has not yet started; else prints an error message and returns False
        if (await self.check_game(message)):
            if not self.running:
                return True
            await message.channel.send('Cannot modify this game, it has already started.')
        return False


    def create_player(self, user):
        # Return a new Player object corresponding to the given user
        # Abstract method, override this!
        pass


    def find_player(self, user):
        # Find the Player corresponding to the given user
        for player in self.players:
            if player.user == user:
                return player






    ##### GB commands (commands available in every GameBot game) #####


    async def setup(self):
        # Abstract method, override if you have async stuff you need to do at start-up
        pass


    async def create(self, message):
        # Initialize the data structures specific to this particular game
        # Abstract method, override this!
        pass


    async def gb_create(self, message):
        '''Create a new game'''
        # First, check if this is a private channel. You can't create a game in a DM.
        if message.channel.type == discord.ChannelType.private:
            await message.channel.send('Cannot create a game within a DM. Please try again using a public channel.')
            return
        # Check if there's another game of the same type as this one in the same channel
        for game in self.bot.games:
            if game.prefix == self.prefix:
                if game.main_channel == message.channel:
                    if game.owner.user != message.author:
                        await message.channel.send('A game of %s is currently being played in this channel. Please wait for it to finish, or ask %s to cancel it.' % (self.name, game.owner.user.mention))
                        return
                    if not (await self.askyesno('You have already created a game of %s in this channel. Do you want to cancel it and start a new one?' % self.name, message.author, message.channel)):
                        return
                    if game.owner:
                        await game.main_channel.send('%s has canceled the currently active game of %s.' % (message.author.mention, self.name))
                        game.close()
                    break
        # Check if this player is already playing another game of the same type as this one
        for game in self.bot.games:
            if game.prefix == self.prefix:
                if game.find_player(message.author):
                    await message.channel.send('You are already playing a game of %s, so you cannot create another one.' % self.name)
                    return
        # Make sure we're allowed to DM this user -- thanks to cwu
        # for breaking this :|
        try:
            await message.author.send('You have created a game of %s.' % self.name)
        except discord.Forbidden:
            await message.channel.send('You cannot create a game since the bot is unable to direct message you.')
            return
        if self.owner:
            # Create a new game
            game = self.__class__(self.bot)
            self.bot.games.append(game)
        else:
            # Reuse this one
            game = self
        # Set up the game
        game.owner = game.create_player(message.author)
        game.running = False
        game.players = [game.owner] # List of Player objects in the game, in order
        game.main_channel = message.channel
        game.votekicks = set() # List of people who have requested that the game be canceled due to an unresponsive owner
        await game.create(message)
        # Make a public announcement
        await game.main_channel.send('%s has just created an game of %s. To join, simply type "%s join".' % (message.author.mention, game.name, game.prefix))
        # Ping the #game-talk channel too if it's not too soon to do that
        now = datetime.datetime.utcnow()
        id = game.main_channel.guild.id
        if game.bot.ping_channels.get(id):
            if (self.bot.last_ping[id] is None) or (now - self.bot.last_ping[id] >= PING_DELAY):
                if message.guild:
                    role = discord.utils.get(message.guild.roles, name=str(os.getenv('GAMEBOT_ROLE_NAME')))
                    if role:
                        self.bot.last_ping = now
                        await self.bot.ping_channel.send('%s: a game of %s has been created in %s!' % (role.mention, game.name, game.main_channel.mention))
        # Start the timer
        game.starting_timer_task = asyncio.create_task(game.starting_timer())



    def close(self):
        # Reset the game state
        self.owner = None
        self.running = False
        self.players = []
        self.main_channel = None
        self.starting_timer_task = None
        self.unmute_all()
        # Remove this game from the list if there's another one like it
        for game in self.bot.games:
            if (game.prefix == self.prefix) and (game is not self):
                self.bot.games.remove(self)
                break



    async def starting_timer(self):
        # Start a very long timer to cancel the game after a certain amount (20 minutes) of delay between creation and start time
        await asyncio.sleep(STARTING_DELAY)
        if self.owner and not self.running:
            channel = self.main_channel
            self.close()
            await channel.send('*The current game of %s has timed out without starting. It has now been canceled.*' % self.name)


    def cancel_starting_timer(self):
        # Cancel the starting timer
        if self.running:
            # Stop the timer
            if self.starting_timer_task:
                if not self.starting_timer_task.done():
                    self.starting_timer_task.cancel()
                self.starting_timer_task = None
        
        
                    
                
    async def gb_cancel(self, message):
        '''Cancel a game you created'''
        if (await self.check_owner(message)):
            if (await self.askyesno('Are you sure you wish to cancel the currently active game of %s?' % self.name, message.author, message.channel)):
                if self.owner:
                    channel = self.main_channel
                    self.cancel_starting_timer()
                    self.close()
                    # Make a public announcement
                    await channel.send('%s has canceled the currently active game of %s.' % (message.author.mention, self.name))



    async def gb_join(self, message):
        '''Join a game that has not yet started'''
        if not self.owner:
            # Create a game if one doesn't already exist
            await self.gb_create(message)
            return
        if (await self.check_not_running(message)):
            # Make sure we're not already part of the game
            if self.find_player(message.author):
                await message.channel.send('You are already part of this game.')
                return
            # Check if this player is already playing another game of the same type as this one
            for game in self.bot.games:
                if game.prefix == self.prefix:
                    if game.find_player(message.author):
                        await message.channel.send('You are already playing a game of %s, so you cannot join another one.' % self.name)
                        return
            # Make sure we're allowed to DM this user -- thanks to cwu
            # for breaking this :|
            try:
                await message.author.send('You have joined the game of %s.' % self.name)
            except discord.Forbidden:
                await message.channel.send('You cannot join this game since the bot is unable to direct message you.')
                return
            # Add the player
            self.players.append(self.create_player(message.author))
            # Make a public announcement
            await self.main_channel.send('%s has joined the game of %s.' % (message.author.mention, self.name))



    async def gb_leave(self, message):
        '''Leave a game before it begins'''
        if (await self.check_not_running(message)):
            # Leave is the same thing as cancel if you're the game owner
            if self.owner and (message.author == self.owner.user):
                await self.gb_cancel(message)
                return
            # Make sure we're currently part of the game
            player = self.find_player(message.author)
            if not player:
                await message.channel.send('You are not part of this game.')
                return
            # Remove the player
            self.players.remove(player)
            # Make a public announcement
            await self.main_channel.send('%s has left the game of %s.' % (message.author.mention, self.name))

    

    async def gb_votekick(self, message):
        '''Vote to end the game if the owner has become unresponsive'''
        if (await self.check_game(message)):
            self.votekicks.add(message.author.id)
            if len(self.votekicks) == 1:
                await message.channel.send('1 person has voted to cancel the game of %s.' % self.name)
            else:
                await message.channel.send('%d people have voted to cancel the game of %s.' % (len(self.votekicks), self.name))
            if len(self.votekicks) >= 4:
                if self.owner:
                    channel = self.main_channel
                    self.close()
                    # Make a public announcement
                    await channel.send('The currently active game of %s has been canceled by popular vote.' % self.name)



    async def gb_move(self, message):
        '''Move this game to another channel.'''
        if (await self.check_owner(message)):
            if len(message.channel_mentions) != 1:
                await message.channel.send('Syntax: %s move [mention channel]' % self.prefix)
                return
            self.main_channel = message.channel_mentions[0]
            await self.main_channel.send('The game of %s has moved to %s.' % (self.name, self.main_channel.mention))
            


    async def start(self, message):
        # Start the game
        # Abstract method, override this!
        pass


    async def gb_start(self, message):
        '''Start the game that was previously created'''
        if (await self.check_owner(message)):
            if self.running:
                await message.channel.send('The game has already started.')
                return
            self.running = True
            await self.start(message)
            if self.running:
                self.cancel_starting_timer()
        

    async def gb_ping(self, message):
        '''Ping the GameBot'''
        await message.channel.send('pong')

    async def gb_coin(self, message):
        '''Simulate a random coin flip'''
        await message.channel.send(random.choice(['heads', 'tails']))

    async def gb_help(self, message):
        '''I'm guessing you've figured out by now what this one does'''
        await message.author.send(self.help)


    async def gb_roll(self, message):
        '''Roll some number of die'''
        words = message.content.split()
        if len(words) == 3:
            dice = words[2]
            if dice.startswith('d'):
                dice = '1' + dice
            try:
                number, sides = map(int, dice.split('d'))
            except ValueError:
                pass
            else:
                if number > 50:
                    await message.channel.send('Error: you are not allowed to roll that many dice at once.')
                else:
                    await message.channel.send('Your %d random %d-sided die roll%s: **%s**' % (number, sides, ('' if number == 1 else 's'),
                                                                                               ' '.join(map(str, [random.randint(1, sides) for i in range(number)]))))
                return
        # If we get here, there was an error and we need to print syntax
        await message.channel.send('Syntax: %s roll [number]d[sides]\n(For example: %s roll 1d6)' % (self.prefix, self.prefix))



    async def gb_debug(self, message):
        # For debugging ONLY!
        if not self.bot.DEBUG:
            return
        if message.author.id != int(os.getenv('GAMEBOT_MASTER_ID')):
            await message.channel.send('You do not have permission to run debugging commands!')
            return
        start = message.content.find('```')
        if start == -1:
            await message.channel.send('Syntax: %s debug ```[code]```' % self.prefix)
            return
        start += 3
        end = message.content.find('```', start)
        if end == -1:
            await message.channel.send('Syntax: %s debug ```[code]```' % self.prefix)
            return
        code = message.content[start:end]
        outp = io.StringIO()
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        sys.stdout = sys.stderr = outp
        try:
            exec(code)
        except:
            traceback.print_exc()
        sys.stdout = old_stdout
        sys.stderr = old_stderr
        s = outp.getvalue()
        if s:
            await message.channel.send('```%s```' % s)



    async def gb_heff(self, message):
        # Self-explanatory
        if message.channel_mentions:
            heff = message.channel_mentions[0]
        else:
            heff = discord.utils.get(self.bot.get_all_members(), id=int(os.getenv('GAMEBOT_HEFF_ID')))
        await heff.send('shup heff')


    # Muting

    def mute(self, player):
        if (player.user, self) not in self.bot.muted:
            self.bot.muted.append((player.user, self))

    def unmute(self, player):
        if (player.user, self) in self.bot.muted:
            self.bot.muted.remove((player.user, self))

    def unmute_all(self):
        for user, game in self.bot.muted[:]:
            if game == self:
                self.bot.muted.remove((user, game))



    # Synonyms (by popular demand)
    gb_new = gb_create
    gb_quit = gb_stop = gb_end = gb_cancel
    gb_in = gb_enter = gb_join
    gb_out = gb_exit = gb_leave
    gb_begin = gb_start
    gb_coinflip = gb_coin


