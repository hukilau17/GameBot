# Codenames game bot
# Matthew Kroesche

import discord
import recordclass
import random
import asyncio


from .game import Game


Player = recordclass.recordclass('Player', 'user')
# The Player class here has no data

# Team color constants
NONE = 0
RED = 1
BLUE = 2
CIVILIAN = 3
ASSASSIN = 4

COLORS = ['None', 'Red', 'Blue', 'Civilian', 'Assassin']




class Codenames(Game):

    name = 'Codenames'
    prefix = 'cn'

    def create_player(self, user):
        return Player(user)


    async def setup(self):
        with open('codewords') as o:
            # Load the word bank
            self.codewords = o.read().strip().splitlines()
        

    async def create(self, message):
        # Initialize the game attributes
        self.red_team = []
        self.blue_team = []
        self.key = []
        self.key_string = ''
        self.board = []
        self.board_size = (5, 5)
        self.num_clues = 8
        self.current_team = NONE
        self.waiting_for_clue = False
        self.guesses_remaining = 0
        self.reentrant = False



    async def cn_settings(self, message):
        '''Query or modify the game board settings'''
        if len(message.content.split()) == 2:
            if (await self.check_game(message)):
                # Print out the settings
                await message.channel.send('**Current board settings:** %d x %d board with %d guesses for the second team to win' % \
                                           (self.board_size + (self.num_clues,)))
            return
        try:
            board_width, board_height, num_clues = map(int, message.content.lower().split()[2:])
        except ValueError:
            # Print usage
            await message.channel.send('Syntax: cn settings [board width] [board height] [number of clues]')
            return
        if (await self.check_not_running(message)) and (await self.check_owner(message)):
            if (board_width < 1) or (board_height < 1) or (num_clues < 1):
                await message.channel.send('Error: invalid board configuration')
                return
            if (board_width > 12) or (board_height > 12):
                await message.channel.send('Error: maximum board width/height is 12')
                return
            if (num_clues > board_width * board_height // 2 - 1):
                await message.channel.send('Error: too many clues for given board size')
            self.board_size = (board_width, board_height)
            self.num_clues = num_clues
            await self.main_channel.send('**Current board settings:** %d x %d board with %d guesses for the second team to win' % \
                                         (self.board_size + (self.num_clues,)))
        

        


    async def cn_info(self, message):
        '''Print out the current game info'''
        if (await self.check_game(message)):
            # Print out the team info
            red_names = [p.user.name for p in self.red_team]
            if red_names: red_names[0] += ' (Cluemaster)'
            info = '**Red team**\n%s\n' % ', '.join(red_names)
            blue_names = [p.user.name for p in self.blue_team]
            if blue_names: blue_names[0] += ' (Cluemaster)'
            info += '**Blue team**\n%s\n' % ', '.join(blue_names)
            not_joined = [p for p in self.players if p not in self.red_team + self.blue_team]
            if not_joined:
                info += '*The following players still need to join a team:* %s\n' % ', '.join([p.user.mention for p in not_joined])
            if not self.running:
                info += 'Game has not yet started.'
                await message.channel.send(info)
                return
            # Print out the game board if the game has started
            if self.board:
                board = [i if isinstance(i, str) else '[%s]' % COLORS[i] for i in board]
                rows = [board[i:i+self.board_size[0]] for i in range(0, len(board), self.board_size[0])]
                colwidths = [max(map(len, [rows[j][i] for j in range(len(rows))])) + 2 for i in range(len(rows[0]))]
                rows = [[s.center(colwidths[i]) for i, s in enumerate(row)] for row in rows]
                info += 'Game board:\n```'
                divider = '+%s+\n' % '+'.join(['-' * i for i in colwidths])
                info += divider
                for row in rows:
                    info += '|%s|\n' % '|'.join(row)
                    info += divider
                info += '```'
            await message.channel.send(info)
            await self.cn_poke(message)



    async def cn_poke(self, message):
        '''Pokes people who need to make a decision'''
        if (await self.check_running(message)):
            if self.current_team:
                if self.waiting_for_clue:
                    team = (self.red_team if self.current_team == RED else self.blue_team)
                    cluemaster = team[0]
                    await self.main_channel.send('*Currently waiting for %s to give a clue.' % cluemaster.user.mention)
                    return
                if self.guesses_remaining:
                    await self.main_channel.send('*Currently waiting for the %s Team to click on something.' % COLORS[self.current_team])
                    return
            await self.main_channel.send('*Not currently waiting for anyone to make a decision.*')



    # Overrides of join and leave

    async def cn_join(self, message):
        '''Join a game that has not yet started'''
        spl = message.content.split()
        if not (self.find_player(message.author) and (len(spl) == 3)):
            await self.gb_join(message) # Allow things like "cn join red" after we've already joined, to switch teams
        player = self.find_player(message.author)
        if player:
            # Override to support syntax like "cn join red" or "cn join blue"
            if len(spl) == 3:
                team = spl[-1].lower()
                if team == 'red':
                    self.red_team.append(player)
                    if player in self.blue_team:
                        self.blue_team.remove(player)
                elif team == 'blue':
                    self.blue_team.append(player)
                    if player in self.red_team:
                        self.red_team.remove(player)
                else:
                    await message.channel.send('Unrecognized team name "%s"' % team)


    async def cn_leave(self, message):
        '''Leave a game before it begins'''
        player = self.find_player(message.author)
        await self.gb_leave(message)
        # Override to make sure that when someone leaves, it drops them from whatever team they're on too
        if player and self.running and not self.find_player(message.author):
            if player in self.red_team:
                self.red_team.remove(player)
            elif player in self.blue_team:
                self.blue_team.remove(player)



    async def cn_shuffle(self, message):
        '''Randomly assign teams'''
        if (await self.check_not_running(message)) and (await self.check_owner(message)):
            players = self.players[:]
            random.shuffle(players)
            n = len(players) // 2
            teams = [players[:n], players[n:]]
            random.shuffle(teams)
            self.red_team, self.blue_team = teams
            await self.main_channel.send('The teams have been shuffled!')
            await self.cn_info(message)



    async def cn_cluemaster(self, message):
        '''Assign someone to be the cluemaster of their team'''
        if len(message.mentions) != 1:
            await message.channel.send('Syntax: cn cluemaster [mention person]')
            return
        if (await self.check_not_running(message)) and (await self.check_owner(message)):
            player = self.find_player(message.mentions[0])
            if player is None:
                await message.channel.send('Error: %s is not currently part of the game.' % message.mentions[0].mention)
            elif player in self.red_team:
                self.red_team.remove(player)
                self.red_team.insert(0, player)
                await self.main_channel.send('%s is now the cluemaster of the Red Team.' % player.user.mention)
            elif player in self.blue_team:
                self.blue_team.remove(player)
                self.blue_team.insert(0, player)
                await self.main_channel.send('%s is now the cluemaster of the Blue Team.' % player.user.mention)
            else:
                await message.channel.send('Error: %s has not currently joined a team.' % message.mentions[0].mention)
        



    async def start(self, message):
        # Error checking
        not_joined = [p for p in self.players if p not in self.red_team + self.blue_team]
        if not_joined:
            await message.channel.send('Cannot start because the following players still need to join a team:* %s.' % \
                                       ', '.join([p.user.mention for p in not_joined]))
            self.running = False
            return
        if len(self.red_team) <= 1 or len(self.blue_team) <= 1:
            await message.channel.send('Cannot start: there must be at least two players on each team.')
            self.running = False
            return
        # Make a public announcement
        await self.main_channel.send('The game has now been started!')
        # Set up the game
        self.board = random.sample(self.codewords, self.board_size[0] * self.board_size[1]) # Decide which codewords to use
        order = [RED, BLUE]
        random.shuffle(order)
        self.key = []
        self.key.extend( [order[0]] * (self.num_clues + 1) ) # The team that goes first has to give an extra clue
        self.key.extend( [order[1]] * self.num_clues )
        self.key.extend( [CIVILIAN] * (self.board_size[0]*self.board_size[1] - 2*self.num_clues - 2) ) # Leftover spaces for civilians
        self.key.append(ASSASSIN) # Make sure there is exactly one assassin
        random.shuffle(self.key) # And shuffle it
        # Create the key string
        self.key_string = '\n'.join(['RBCX'[s-1] for s in self.key[i:i+self.board_size[0]] for i in range(0, len(self.key), self.board_size[0])])
        self.key_string += '\n(Legend: R=Red, B=Blue, C=Civilian, X=Assassin)'
        # Update whose turn it is
        self.current_team = order[0]
        self.waiting_for_clue = True
        await self.cn_info(message) # Print out the public info
        # Tell the key to both cluemasters
        for cluemaster in (self.red_team[0], self.blue_team[0]):
            await cluemaster.user.send(self.key_string)
            self.mute(cluemaster) # The cluemasters cannot talk (other than giving clues at the appropriate time)
            

        
                
    async def cn_clue(self, message):
        '''As the cluemaster, give a clue to your team'''
        if (await self.check_running(message)):
            player = self.find_player(message.author)
            # Error checking
            if player is None:
                await message.channel.send('You are not currently part of this game.')
            elif player not in (self.red_team[0], self.blue_team[0]):
                await message.channel.send('You are not currently the cluemaster.')
            elif not self.waiting_for_clue:
                await message.channel.send('It is not currently time to give a clue.')
            elif player != [None, self.red_team, self.blue_team][self.current_team][0]:
                await message.channel.send('It is currently the other team\'s turn to give a clue.')
            else:
                # Parse the message
                spl = message.content.split()
                num = None
                if len(spl) == 4:
                    clue = spl[2].upper()
                    if spl[3] == 'u':
                        num = -1
                    else:
                        try:
                            num = int(spl[3])
                        except ValueError:
                            pass
                        if num < 0:
                            num = None
                # Print out syntax message if it wasn't parsed
                if num is None:
                    await message.channel.send('Syntax: cn clue [clue] [number]')
                else:
                    # Update internal data
                    self.waiting_for_clue = False
                    if num <= 0:
                        self.guesses_remaining = -1
                        if num == -1:
                            num = 'UNLIMITED'
                    else:
                        self.guesses_remaining = num + 1
                    # Give the clue
                    await self.main_channel.send('%s has given the following clue to the %s Team: %s %s' % \
                                                 (player.user.mention, COLORS[self.current_team], clue, num))



    async def cn_click(self, message):
        '''Choose a cell to click on when it is your team's turn'''
        if (await self.check_running(message)):
            player = self.find_player(message.author)
            # Error checking
            if player is None:
                await message.channel.send('You are not currently part of this game.')
            elif player in (self.red_team[0], self.blue_team[0]):
                await message.channel.send('Stop trolling, you dork.')
            elif self.waiting_for_clue:
                await message.channel.send('It is not currently time to click on cells.')
            elif player not in [None, self.red_team, self.blue_team][self.current_team]:
                await message.channel.send('It is currently the other team\'s turn to contact their agents.')
            elif self.reentrant:
                await message.channel.send('Too early to guess again. Please wait a few seconds.')
            elif not self.guesses_remaining:
                await message.channel.send('Your team is out of guesses.')
            else:
                # Parse the message
                spl = message.content.split()
                index = None
                if len(spl) == 3:
                    cell = spl[2].upper()
                    try:
                        index = self.board.index(cell)
                    except ValueError:
                        await message.channel.send('There is no active cell named "%s"' % cell)
                        return
                # Print out syntax message if it wasn't parsed
                if index is None:
                    await message.channel.send('Syntax: cn click [cell name]')
                else:
                    self.reentrant = True
                    async with self.main_channel.typing():
                        await asyncio.sleep(5) # Pause for dramatic effect
                    # Update internal data
                    value = self.board[index] = self.key[index]
                    if self.guesses_remaining > 0:
                        self.guesses_remaining -= 1
                    await self.main_channel.send('The %s Team contacted the following agent: **%s**' % (COLORS[self.current_team], COLORS[value]))
                    if value == ASSASSIN:
                        # End the game immediately if the assassin is contacted
                        winner = ('Red' if self.current_team == BLUE else 'Blue')
                        channel = self.main_channel
                        self.close()
                        await channel.send('**The game is over because the Assassin was contacted. The %s Team wins!**' % winner)
                        return
                    for team in (RED, BLUE):
                        if self.board.count(team) == self.key.count(team):
                            # End the game if all the agents for a team have been contacted
                            channel = self.main_channel
                            self.close()
                            await channel.send('**The %s Team wins because they have contacted all their agents!**' % COLORS[team])
                            return
                    if value != self.current_team:
                        # Don't end the game, but take away all the team's remaining guesses
                        self.guesses_remaining = 0
                    if self.guesses_remaining:
                        await self.main_channel.send('Please either contact another agent using "cn click", or finish your turn using "cn finish". You have %s guess%s remaining.' % \
                                                     ('unlimited' if self.guesses_remaining < 0 else ('up to %d' % self.guesses_remaining),
                                                      '' if self.guesses_remaining == 1 else 'es'))
                    else:
                        # Switch to the other team
                        self.current_team = (RED if self.current_team == BLUE else BLUE)
                        self.waiting_for_clue = True
                        team = (self.red_team if self.current_team == RED else self.blue_team)
                        cluemaster = team[0]
                        await self.main_channel.send('It is now %s\'s turn to give a clue to the %s Team.' % (cluemaster.user.mention, COLORS[self.current_team]))
                    self.reentrant = False



    async def cn_finish(self, message):
        '''End your team's turn without making any more guesses'''
        if (await self.check_running(message)):
            player = self.find_player(message.author)
            # Error checking
            if player is None:
                await message.channel.send('You are not currently part of this game.')
            elif player in (self.red_team[0], self.blue_team[0]):
                await message.channel.send('Stop trolling, you dork.')
            elif self.waiting_for_clue:
                await message.channel.send('It is not currently time to click on cells.')
            elif player not in [None, self.red_team, self.blue_team][self.current_team]:
                await message.channel.send('It is currently the other team\'s turn to contact their agents.')
            elif self.reentrant:
                await message.channel.send('Too early to finish. Please wait a few seconds.')
            else:
                # Switch to the other team
                old_team = self.current_team
                self.current_team = (RED if self.current_team == BLUE else BLUE)
                self.waiting_for_clue = True
                team = (self.red_team if self.current_team == RED else self.blue_team)
                cluemaster = team[0]
                await self.main_channel.send('The %s Team has ended their turn. It is now %s\'s turn to give a clue to the %s Team.' % \
                                             (COLORS[old_team], cluemaster.user.mention, COLORS[self.current_team]))
                    
            
                
    # Synonyms

    cn_prod = cn_poke
    cn_contact = cn_clue
