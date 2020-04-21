# Liar's Dice game bot
# Matthew Kroesche

import discord
import recordclass
import random
import asyncio

from .game import Game


Player = recordclass.recordclass('Player', 'user dice bid passed')
# user: the discord.User controlling this player.
# dice: the list of die rolls of this player
# bid: either None or a 2-tuple (number, value)
# passed: boolean indicating whether the player has passed this round

PASS_NONE   = 0 # Passing not allowed
PASS_TWO    = 1 # Passing allowed if there are exactly two dice showing different values
PASS_UNIQUE = 2 # Passing allowed if no two dice show the same value
PASS_SKIP   = 4 # Passing only allowed if the player before you didn't also pass

SPOT_NONE     = 0 # Spot not allowed
SPOT_NORMAL   = 1 # Spot allowed
SPOT_REWARD   = 2 # A correct spot call gives you a die back (or takes one away in backwards games)
SPOT_PENALIZE = 4 # A correct spot call causes everyone else to lose a die (or gain one in backward games)

# Default settings for pass and spot
PASS_DEFAULT = PASS_UNIQUE
SPOT_DEFAULT = SPOT_REWARD

RESULT_DELAY = 10 # Number of seconds before dice messages are deleted







class LiarsDice(Game):

    name = 'Liar\'s Dice'
    prefix = 'ld'

    def create_player(self, user):
        return Player(user, [], None, False)


    async def create(self, message):
        self.n_dice_start = 5         # Number of dice each player starts with
        self.n_dice_end = 0           # Number of dice that causes a player to be eliminated
        self.n_sides = 6              # Number of sides on each die
        self.pass_mode = PASS_DEFAULT # Pass settings
        self.spot_mode = SPOT_DEFAULT # Spot settings
        self.ones_wild = False        # True if 1s are wild
        self.current = None           # The Player whose turn it is currently, if any
        self.last_bidder = None       # The last Player to make an actual bid, if any
        self.passed_players = []      # The Players who have passed since the last actual bid was made
        


    async def gb_leave(self, message):
        '''Leave a game'''
        # Override to allow leaving the game after it has started
        if (await self.check_game(message)):
            # Leave is the same thing as cancel if the game is running and you're the game owner
            if self.running:
                if self.owner and (message.author == self.owner.user):
                    await self.gb_cancel(message)
                    return
            # Make sure we're currently part of the game
            player = self.find_player(message.author)
            if not player:
                await message.channel.send('You are not part of this game.')
                return
            if self.running:
                if not (await self.askyesno('Are you sure you want to leave the game? You will not be able to rejoin later.', message.author, message.channel)):
                    return
            if player in self.players:
                index = self.players.index(player)
                # Remove the player
                self.players.remove(player)
                # Make a public announcement
                await self.bot.main_channel.send('%s has left the game of %s.' % (message.author.mention, self.name))
                if self.running:
                    if len(self.players) <= 1:
                        await self.bot.main_channel.send('The game has been canceled because there are too few players.')
                        self.running = False
                        self.owner = None
                    elif player.user == self.current:
                        self.current = self.players[index % len(self.players)]
                        await self.ld_poke(message)
                    



    def dice_settings(self):
        style = ('decreasing' if self.n_dice_end < self.n_dice_start else 'increasing')
        return '**Current dice settings:** %d %d-sided dice, %s to %d' % \
               (self.n_dice_start, self.n_sides, style, self.n_dice_end)


    async def ld_dice(self, message):
        '''Configure the dice settings for the game'''
        if len(message.content.split()) == 2:
            if (await self.check_game(message)):
                # Print out the settings
                await message.channel.send(self.dice_settings())
            return
        try:
            n_dice_start, n_dice_end, n_sides = map(int, message.content.lower().split()[2:])
        except ValueError:
            # Print usage
            await message.channel.send('Syntax: ld dice [starting number] [final number] [number of sides]')
            return
        if (await self.check_not_running(message)) and (await self.check_owner(message)):
            if (n_dice_start < 1) or (n_dice_end < 0) or (n_sides < 2) or (n_dice_end == n_dice_start):
                await message.channel.send('Error: invalid dice configuration')
                return
            self.n_dice_start = n_dice_start
            self.n_dice_end = n_dice_end
            self.n_sides = n_sides
            await self.bot.main_channel.send(self.dice_settings())


    def pass_settings(self):
        if self.pass_mode == PASS_NONE:
            return '**Current passing rules:** Passing is not allowed.'
        if self.pass_mode & PASS_UNIQUE:
            message = 'You can pass if no two of your dice are showing the same number.'
        else:
            message = 'You can pass if you have two dice and they are not showing the same number.'
        if self.pass_mode & PASS_SKIP:
            message += ' Two people passing in a row is prohibited.'
        return '**Current passing rules:** %s' % message


    async def ld_passmode(self, message):
        '''Configure the passing rules for the game'''
        if len(message.content.split()) == 2:
            if (await self.check_game(message)):
                # Print out the settings
                await message.channel.send(self.pass_settings())
            return
        if (await self.check_not_running(message)) and (await self.check_owner(message)):
            settings = list(sorted(message.content.lower().split()[2:]))
            mode = PASS_NONE
            for setting in settings:
                if setting == 'none':
                    mode = PASS_NONE
                elif setting == 'two':
                    mode |= PASS_TWO
                    mode &= ~PASS_UNIQUE
                elif setting == 'unique':
                    mode |= PASS_UNIQUE
                    mode &= ~PASS_TWO
                elif setting == 'skip':
                    mode |= PASS_SKIP
                else:
                    await message.channel.send('Invalid pass mode: should be one of none, two, unique, skip')
                    return
            if mode == PASS_SKIP:
                mode |= PASS_DEFAULT
            self.pass_mode = mode
            await self.bot.main_channel.send(self.pass_settings())


    def spot_settings(self):
        if self.spot_mode == SPOT_NONE:
            return '**Current spotting rules:** Calling spot is not allowed.'
        if self.spot_mode == SPOT_NORMAL:
            return '**Current spotting rules:** Calling spot is allowed, but there is no reward for doing so.'
        message = []
        if self.spot_mode & SPOT_NORMAL:
            message.append('Calling spot is allowed.')
        if self.spot_mode & SPOT_REWARD:
            if self.n_dice_start > self.n_dice_end:
                message.append('A successful spot call allows you to gain back a lost die.')
            else:
                message.append('A successful spot call allows you to lose a previously gained die.')
        if self.spot_mode & SPOT_PENALIZE:
            if self.n_dice_start > self.n_dice_end:
                message.append('A successful spot call causes every other player to lose a die.')
            else:
                message.append('A successful spot call causes every other player to gain a die.')
        return '**Current spotting rules:** %s' % ' '.join(message)


    async def ld_spotmode(self, message):
        '''Configure the spotting rules for the game'''
        if len(message.content.split()) == 2:
            if (await self.check_game(message)):
                # Print out the settings
                await message.channel.send(self.spot_settings())
            return
        if (await self.check_not_running(message)) and (await self.check_owner(message)):
            settings = list(sorted(message.content.lower().split()[2:]))
            mode = SPOT_NONE
            for setting in settings:
                if setting == 'none':
                    mode = SPOT_NONE
                elif setting == 'normal':
                    mode |= SPOT_NORMAL
                elif setting == 'reward':
                    mode |= SPOT_REWARD
                elif setting == 'penalize':
                    mode |= SPOT_PENALIZE
                else:
                    await message.channel.send('Invalid spot mode: should be one of none, normal, reward, penalize')
                    return
            if mode != SPOT_NONE:
                mode |= SPOT_NORMAL
            self.spot_mode = mode
            await self.bot.main_channel.send(self.spot_settings())


    async def ld_wild(self, message):
        '''Configure whether ones are wild in this game'''
        content = message.content.lower().split()
        if len(content) == 2:
            if (await self.check_game(message)):
                # Print out the settings
                await message.channel.send('Ones are %swild in this game.' % ('' if self.ones_wild else 'not '))
            return
        if (await self.check_not_running(message)) and (await self.check_owner(message)):
            if len(content) == 3:
                if content[2] == 'on':
                    self.ones_wild = True
                    await self.bot.main_channel.send('**Ones are wild in this game.**')
                    return
                if content[2] == 'off':
                    self.ones_wild = False
                    await self.bot.main_channel.send('**Ones are not wild in this game.**')
                    return
            await message.channel.send('Syntax: ld wild [on or off]')



    async def ld_info(self, message):
        '''Print out the current game info'''
        if (await self.check_game(message)):
            info = '**Current players:**\n%s\n' % ', '.join([player.user.name for player in self.players])
            info += 'Game owner: %s\n' % self.owner.user.mention
            info += self.dice_settings() + '\n'
            info += self.pass_settings() + '\n'
            info += self.spot_settings() + '\n'
            if self.ones_wild:
                info += '**Ones are wild in this game.**\n'
            if self.last_bidder:
                info += '**Current bid:** %s by %s\n' % (self.format_bid(self.last_bidder.bid), self.last_bidder.user.mention)
            await message.channel.send(info)
            await self.ld_poke(message)


    async def ld_poke(self, message):
        '''Pokes people who need to make a decision'''
        if (await self.check_running(message)):
            if self.current:
                await self.bot.main_channel.send('*Currently waiting for %s to make a bid.*' % self.current.user.mention)
            else:
                await self.bot.main_channel.send('*Not currently waiting for anyone to make a decision.*')


    async def start(self, message):
        # Set up the game
        if len(self.players) < 2:
            self.running = False
            await message.channel.send('Cannot start the game unless there are at least two players.')
            return
        # Make a public announcement
        await self.bot.main_channel.send('The game has now been started!')
        # Set up the game
        random.seed() # Seed the random number generator
        random.shuffle(self.players) # Randomize the play order
        self.current = self.players[0]
        for p in self.players:
            p.dice = [1] * self.n_dice_start
        await self.roll(message) # and let's get started!


    async def roll(self, message):
        self.last_bidder = None
        self.passed_players = []
        for p in self.players:
            p.dice = [random.randint(1, self.n_sides) for i in range(len(p.dice))]
            p.dice.sort()
            p.bid = None
            p.passed = False
            await p.user.send('Your dice rolls for this round:\n**%s**' % ' '.join(map(str, p.dice)))
        await self.ld_poke(message)


    async def penalize(self, player):
        if self.n_dice_start > self.n_dice_end:
            player.dice.pop()
        else:
            player.dice.append(1)
        if len(player.dice) == self.n_dice_end:
            await self.bot.main_channel.send('*%s has been eliminated from the game.*' % player.user.mention)
            self.players.remove(player)
            if len(self.players) == 1:
                await self.bot.main_channel.send('**The game is over. %s is the winner!**' % self.players[0].user.mention)
                self.owner = False
                self.running = False

                
    async def reward(self, player):
        if self.n_dice_start > self.n_dice_end:
            if len(player.dice) < self.n_dice_start:
                player.dice.append(1)
        else:
            if len(player.dice) > self.n_dice_start:
                player.dice.pop()
        if len(player.dice) == self.n_dice_end:
            await self.bot.main_channel.send('*%s has been eliminated from the game.*' % player.user.mention)
            self.players.remove(player)
            if len(self.players) == 1:
                await self.bot.main_channel.send('**The game is over. %s is the winner!**' % self.players[0].user.mention)
                self.owner = False
                self.running = False
                
                


    async def check_current(self, message):
        # Returns True if the game is running, and the player sending this message is the current player.
        if (await self.check_running(message)):
            if self.current and (message.author == self.current.user):
                return True
            if self.find_player(message.author) is None:
                await message.channel.send('You are not currently part of this game.')
            else:
                await message.channel.send('It is not currently your turn.')
        return False


    def format_bid(self, bid):
        num, value = bid
        return '%d %d%s' % (num, value, '' if num == 1 else 's')


    def compare_bid(self, bid):
        num, value = bid
        if (value == 1) and self.ones_wild:
            return 2*num, value
        return num, value



    async def ld_bid(self, message):
        '''Make a bid on the number of dice'''
        if (await self.check_current(message)):
            try:
                num, value = map(int, message.content.lower().split()[2:])
            except ValueError:
                # Print usage
                await message.channel.send('Syntax: ld bid [number of dice] [value on dice]')
                return
            # Error checking
            if (num < 1) or not (1 <= value <= self.n_sides):
                await message.channel.send('Illegal bid, please try again')
                return
            if self.last_bidder:
                if self.compare_bid(self.last_bidder.bid) >= self.compare_bid((num, value)):
                    errormsg = 'Please try again, you must raise the current bid of %s' % self.format_bid(self.last_bidder.bid)
                    if self.ones_wild and (1 in (self.last_bidder.bid[1], value)):
                        errormsg += '\n*Note that since ones are wild, bids involving ones are worth twice as much.*'
                    await message.channel.send(errormsg)
                    return
            # Update the bid
            self.current.bid = (num, value)
            self.last_bidder = self.current
            self.passed_players = []
            # Advance the current player
            index = self.players.index(self.current)
            index = (index + 1) % len(self.players)
            self.current = self.players[index]
            # Make a public announcement
            await self.bot.main_channel.send('%s bid **%s**.\nIt is now %s\'s turn.' % (self.last_bidder.user.mention, self.format_bid((num, value)), self.current.user.mention))



    async def ld_liar(self, message, is_pass=False):
        '''Challenge another player's bid or pass'''
        if (await self.check_current(message)):
            # Error checking
            if message.mentions:
                # `ld liar @someone` will challenge their bid or pass if possible,
                # and print an error message if not. If it is possible to challenge
                # them on both bidding and passing (which only happens if they bid, and then
                # every single person in the round used their pass at once) then it will challenge
                # the bid and not the pass.
                # On the other hand, `ld liarpass @someone` will challenge that person's PASS, if possible,
                # and print an error message otherwise.
                player = self.find_player(message.mentions[0])
                if player is None:
                    await message.channel.send('Error: %s is not currently part of the game.' % message.mentions[0].mention)
                    return
                if (player != self.last_bidder) and (player not in self.passed_players):
                    await message.channel.send('Error: it is not currently possible to challenge %s.' % player.user.mention)
                    return
                if is_pass and (player not in self.passed_players):
                    await message.channel.send('Error: %s has not passed since the last bid.' % player.user.mention)
                    return
                if player != self.last_bidder:
                    is_pass = True
            elif is_pass:
                # `ld liarpass` will challenge the most recent pass, if any,
                # and print an error message otherwise.
                if not self.passed_players:
                    await message.channel.send('Error: there is not currently a pass to challenge.')
                    return
                player = self.passed_players[-1]
            else:
                # `ld liar` will challenge the most recent bid, if any,
                # and print an error message otherwise.
                player = self.last_bidder
                if player is None:
                    await message.channel.send('Error: there is not currently a bid to challenge.')
                    return
            if player.user == message.author:
                await message.channel.send('Error: you cannot challenge your own bid!')
                return
            # Make a public announcement
            current = self.current
            self.current = None # Don't allow repeat invocations!
            if not is_pass:
                await self.bot.main_channel.send('%s challenged %s\'s bid of %s.' % (message.author.mention, player.user.mention, self.format_bid(player.bid)))
            else:
                await self.bot.main_channel.send('%s challenged %s\'s pass.' % (message.author.mention, player.user.mention))
            async with self.bot.main_channel.typing():
                await asyncio.sleep(5) # Pause for dramatic effect
            rolls = ['%s: %s' % (p.user.mention, ' '.join(map(str, p.dice))) for p in self.players]
            result_msg = (await self.bot.main_channel.send('Die rolls:\n%s' % '\n'.join(rolls)))
            await result_msg.delete(delay=RESULT_DELAY) # Delete after a certain time
            penalty = ('loses' if self.n_dice_start > self.n_dice_end else 'gains')
            if not is_pass:
                # The accusation was against the last player to make a bid
                num, value = player.bid
                count = sum([p.dice.count(value) for p in self.players])
                if self.ones_wild and (value != 1):
                    count += sum([p.dice.count(1) for p in self.players])
                msg = 'Total number of %ds%s: **%d**\n' % (value, ' (including wilds)' if self.ones_wild and (value != 1) else '', count)
                if count >= num:
                    msg += '%s\'s bid was **correct**, so %s %s a die.' % (player.user.mention, current.user.mention, penalty)
                    losing = current
                else:
                    msg += '%s\'s bid was **incorrect**, so %s %s a die.' % (player.user.mention, player.user.mention, penalty)
                    losing = player
            else:
                # The accusation was against somebody who passed
                dice = list(player.dice)
                has_ones = (self.ones_wild and (1 in dice) and (len(dice) > 1)) # You can't pass if you have a wild, unless it's the only dice you have
                if self.pass_mode & PASS_UNIQUE:
                    if (len(dice) == len(set(dice))) and not has_ones:
                        msg = '%s\'s dice were all unique, so they were allowed to pass. %s %s a die.' % (player.user.mention, current.user.mention, penalty)
                        losing = current
                    else:
                        msg = '%s\'s dice were not all unique, so they should not have passed. %s %s a die.' % (player.user.mention, player.user.mention, penalty)
                        losing = player
                else:
                    if (len(dice) == len(set(dice)) == 2) and not has_ones:
                        msg = '%s has exactly two dice showing different values, so they were allowed to pass. %s %s a die.' % \
                              (player.user.mention, current.user.mention, penalty)
                        losing = current
                    else:
                        msg = '%s does not have exactly two dice showing different values, so they should not have passed. %s %s a die.' % \
                              (player.user.mention, player.user.mention, penalty)
                        losing = player
            # Send the message and penalize the appropriate player
            await self.bot.main_channel.send(msg)
            index = self.players.index(losing)
            await self.penalize(losing)
            if losing in self.players:
                self.current = losing
            else:
                self.current = self.players[index % len(self.players)]
            await asyncio.sleep(2) # Pause for a bit
            if self.running:
                await self.roll(message) # and roll again



    async def ld_liarpass(self, message):
        '''Challenge another player's pass'''
        await self.ld_liar(message, is_pass=True)
        



    async def ld_pass(self, message):
        '''Skip your turn without making a bid'''
        if (await self.check_current(message)):
            # Error checking
            if self.pass_mode == PASS_NONE:
                await message.channel.send('Error: passing is not allowed in this game.')
                return
            if self.current.passed:
                await message.channel.send('Error: you can only pass once per round.')
                return
            if self.pass_mode & PASS_SKIP:
                index = self.players.index(self.current)
                prev = self.players[(index - 1) % len(self.players)]
                if prev in self.passed_players:
                    await message.channel.send('Error: you cannot pass because the person before you passed.')
                    return
            # Update the bid
            self.current.passed = True
            self.passed_players.append(self.current)
            # Advance the current player
            index = self.players.index(self.current)
            index = (index + 1) % len(self.players)
            self.current = self.players[index]
            # Make a public announcement
            await self.bot.main_channel.send('%s passed.\nIt is now %s\'s turn.' % (self.passed_players[-1].user.mention, self.current.user.mention))



    async def ld_spot(self, message):
        '''Make a spot-on call'''
        if (await self.check_current(message)):
            # Error checking
            if self.spot_mode == SPOT_NONE:
                await message.channel.send('Error: spotting is not allowed in this game.')
                return
            if self.last_bidder is None:
                await message.channel.send('Error: there is not currently a bid to spot.')
                return
            player = self.last_bidder
            # Make a public announcement
            current = self.current
            self.current = None # Don't allow repeat invocations!
            await self.bot.main_channel.send('%s called spot on %s\'s bid of %s.' % (message.author.mention, player.user.mention, self.format_bid(player.bid)))
            async with self.bot.main_channel.typing():
                await asyncio.sleep(5) # Pause for dramatic effect
            rolls = ['%s: %s' % (p.user.mention, ' '.join(map(str, p.dice))) for p in self.players]
            result_msg = (await self.bot.main_channel.send('Die rolls:\n%s' % '\n'.join(rolls)))
            await result_msg.delete(delay=RESULT_DELAY) # Delete after a certain time
            num, value = player.bid
            count = sum([p.dice.count(value) for p in self.players])
            if self.ones_wild and (value != 1):
                count += sum([p.dice.count(1) for p in self.players])
            msg = 'Total number of %ds%s: **%d**\n' % (value, ' (including wilds)' if self.ones_wild and (value != 1) else '', count)
            losing = []
            winning = []
            if count == num:
                msg += '%s\'s bid was **spot on**' % player.user.mention
                if self.spot_mode == SPOT_NORMAL:
                    msg += ', so nobody is penalized.'
                else:
                    reward = ((self.spot_mode & SPOT_REWARD) and (len(current.dice) != self.n_dice_start))
                    if reward:
                        msg += ', so %s %s a die' % (current.user.mention, 'gains' if self.n_dice_start > self.n_dice_end else 'loses')
                        winning = [current]
                    if self.spot_mode & SPOT_PENALIZE:
                        if reward:
                            msg += ' and '
                        else:
                            msg += ', so '
                        msg += 'everyone else %s a die' % ('loses' if self.n_dice_start > self.n_dice_end else 'gains')
                        losing = [p for p in self.players if p != current]
                    else:
                        msg += '.'
            else:
                msg += '%s\'s bid was **not** spot on, so %s %s a die' % (player.user.mention, current.user.mention,
                                                                          'loses' if self.n_dice_start > self.n_dice_end else 'gains')
                losing = [current]
            # Send the message and penalize/reward the appropriate player(s)
            await self.bot.main_channel.send(msg)
            index = self.players.index(current)
            rotated_players = self.players[index:] + self.players[:index]
            for p in losing:
                await self.penalize(p)
            for p in rotated_players:
                if p in self.players:
                    self.current = p
                    break
            for p in winning:
                await self.reward(p)
            await asyncio.sleep(2) # Pause for a bit
            if self.running:
                await self.roll(message) # and roll again



    # Synonyms
    
    ld_bet = ld_bid
    ld_call = ld_bs = ld_liar
    ld_callpass = ld_bspass = ld_liarpass
    ld_prod = ld_poke

