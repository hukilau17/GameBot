# Secret Hitler game bot
# Matthew Kroesche

import discord
import recordclass
import random
import asyncio

from .game import Game



LIBERAL = 1
FASCIST = 2
HITLER = 3

JA = True
NEIN = False # :P


ROLE_NAMES = [
    # Descriptive names for the roles
    'None',
    'Liberal',
    'Fascist',
    'Hitler',
    ]

AMC_ROLE_NAMES = [
    # Special AMC-edition equivalents of role names (don't ask :P)
    'None',
    'Texan',
    'Missourian',
    'Anand',
    ]


POLICY_NAMES = ROLE_NAMES[:3]
AMC_POLICY_NAMES = ['None', 'Non-Geo', 'Geo']


NONE = 0
INVESTIGATE_LOYALTY = 1
SPECIAL_ELECTION = 2
POLICY_PEEK = 3
EXECUTION = 4


POWER_NAMES = [
    # Descriptive names for the presidential powers
    'None',
    'Investigate Loyalty',
    'Call Special Election',
    'Policy Peek',
    'Execution',
    ]

AMC_POWER_NAMES = [
    # Special AMC-edition equivalents of presidential powers
    'None',
    'Background Check',
    'Call Emergency Jury Meeting',
    'Shortlist Peek',
    'Disqualification',
    ]




Player = recordclass.recordclass('Player', 'user role party vote next')
# user: the discord.User controlling this player.
# role: one of LIBERAL, FASCIST, or HITLER
# party: one of LIBERAL or FASCIST
# vote: one of JA or NEIN
# next: the next Player after this one



# Game parameters

N_FASCISTS = {
    5 : 2,
    6 : 2,
    7 : 3,
    8 : 3,
    9 : 4,
    10: 4,
    }

GAME_BOARDS = {
    5 : (NONE               , NONE               , POLICY_PEEK     , EXECUTION, EXECUTION),
    6 : (NONE               , NONE               , POLICY_PEEK     , EXECUTION, EXECUTION),
    7 : (NONE               , INVESTIGATE_LOYALTY, SPECIAL_ELECTION, EXECUTION, EXECUTION),
    8 : (NONE               , INVESTIGATE_LOYALTY, SPECIAL_ELECTION, EXECUTION, EXECUTION),
    9 : (INVESTIGATE_LOYALTY, INVESTIGATE_LOYALTY, SPECIAL_ELECTION, EXECUTION, EXECUTION),
    10: (INVESTIGATE_LOYALTY, INVESTIGATE_LOYALTY, SPECIAL_ELECTION, EXECUTION, EXECUTION),
    }
    

VOTE_DELAY = 15 # Number of seconds before voting messages are deleted








class SecretHitler(Game):

    name = 'Secret Hitler'
    prefix = 'sh'


    def create_player(self, user):
        return Player(user, None, None, None, None)


    async def create(self, message):
        self.president = None # The current presidential candidate
        self.chancellor = None # The current chancellor candidate
        self.liberal_policies = 0 # Number of liberal policies passed
        self.fascist_policies = 0 # Number of fascist policies passed
        self.election_tracker = 0 # Number of consecutive governments that have been rejected
        self.investigated = [] # Keep track of who has been investigated before in this game
        self.waiting_for_nomination = False # True if the client is waiting for the president to nominate a candidate for chancellor
        self.waiting_for_votes = False # True if the client is waiting for people to cast their votes
        self.waiting_for_president = False # True if the client is waiting for the president to choose a policy
        self.waiting_for_chancellor = False # True if the client is waiting for the chancellor to choose a policy
        self.waiting_for_special = False # True if the client is waiting for the president to exercise a special power
        self.waiting_for_veto = False # True if the client is waiting for the president to respond to a chancellor's veto
        self.tabulating_votes = False # True if the bot is currently tabulating voting results
        self.tabulating_policies = False # True if the bot is currently tabulating success/fail cards
        self.policy_deck = [] # The policy deck for this game
        self.policies = [] # The policies from the deck being looked at by the President and Chancellor 
        self.last_president = None # The president who called a Special Election, if any
        self.term_limited = [] # List of people who are term limited and cannot be picked as Chancellor
        self.dead_players = [] # List of people who have been executed
        # Structures to keep track of which "dialect" we are using
        self.amc_mode = False
        self.ROLE_NAMES = ROLE_NAMES
        self.POWER_NAMES = POWER_NAMES
        self.POLICY_NAMES = POLICY_NAMES




    async def sh_info(self, message):
        '''Print out the current game info'''
        if (await self.check_game(message)):
            info = '**Current players:**\n%s\n' % ', '.join([player.user.name for player in self.players])
            info += 'Game owner: %s\n' % self.owner.user.mention
            if not self.running:
                info += 'Game has not yet started.'
                await message.channel.send(info)
                return
            info += '**Number of %s**: %d\n' % ('non-geo problems solved' if self.amc_mode else 'liberal policies passed', self.liberal_policies)
            info += '**Number of %s**: %d\n' % (    'geo problems solved' if self.amc_mode else 'fascist policies passed', self.fascist_policies)
            if self.president:
                info += '**Current %s**: %s\n' % ('head coach' if self.amc_mode else 'presidential candidate', self.president.user.mention)
            if self.chancellor:
                info += '**Current %s**: %s\n' % ('deputy coach' if self.amc_mode else 'chancellor candidate', self.chancellor.user.mention)
            await message.channel.send(info)
            await self.sh_poke(message)



    async def sh_poke(self, message):
        '''Pokes people who need to make a decision'''
        if (await self.check_running(message)):
            if self.waiting_for_nomination:
                await self.bot.main_channel.send('*Currently waiting for %s to nominate a %s*' % (self.president.user.mention,
                                                                                                  'deputy coach' if self.amc_mode else \
                                                                                                  'candidate for chancellor'))
            elif self.waiting_for_votes:
                await self.bot.main_channel.send('*Currently waiting for the following players to cast their votes: %s*' % \
                                                 ', '.join([p.user.mention for p in self.players if p.vote is None]))
            elif self.waiting_for_president:
                await self.bot.main_channel.send('*Currently waiting for %s to %s*' % (self.president.user.mention,
                                                                                      'trivialize a math problem' if self.amc_mode else \
                                                                                      'discard a policy'))
            elif self.waiting_for_chancellor:
                await self.bot.main_channel.send('*Currently waiting for %s to %s*' % (self.chancellor.user.mention,
                                                                                      'solve a math problem' if self.amc_mode else \
                                                                                      'enact a policy'))
            elif self.waiting_for_special:
                await self.bot.main_channel.send('*Currently waiting for %s to exercise a presidential power: %s*' % (self.president.user.mention,
                                                                                                                     self.POWER_NAMES[self.board[self.fascist_policies-1]]))                                                                                   
            else:
                await self.bot.main_channel.send('*Not currently waiting for anyone to make a decision.*')


    async def sh_powers(self, message):
        '''Print out the special powers to be used in this game'''
        if (await self.check_running(message)):
            info = '**Special Presidential Powers:**\n'
            info += '\n'.join(['%d. %s' % (i+1, self.POWER_NAMES[self.board[i]]) for i in range(5)])
            await message.channel.send(info)


    async def sh_rules(self, message):
        '''Gives link to the game rulebook'''
        await message.channel.send('https://secrethitler.com/assets/Secret_Hitler_Rules.pdf')


    async def sh_amc(self, message):
        self.amc_mode = True
        self.ROLE_NAMES = AMC_ROLE_NAMES
        self.POWER_NAMES = AMC_POWER_NAMES
        self.POLICY_NAMES = AMC_POLICY_NAMES

    async def sh_noamc(self, message):
        self.amc_mode = False
        self.ROLE_NAMES = ROLE_NAMES
        self.POWER_NAMES = POWER_NAMES
        self.POLICY_NAMES = POLICY_NAMES



    async def start(self, message):
        # Set up the board
        try:
            self.board = GAME_BOARDS[len(self.players)]
        except KeyError:
            self.running = False
            await message.channel.send('Cannot start: this game has too %s players' % ('few' if len(self.players) < 5 else 'many'))
            return
        # Make a public announcement
        await self.bot.main_channel.send('The game has now been started!')
        # Set up the game
        random.seed() # Seed the random number generator
        random.shuffle(self.players) # Randomize the play order
        for i in range(len(self.players)):
            self.players[i].next = self.players[(i+1) % len(self.players)] # Give each player a reference to the next one
        await self.shuffle_policies() # Randomize the policy deck
        await self.sh_info(message) # Print out the public info
        await self.secret_info()
        self.president = self.players[0] # Initialize the president's position
        await self.init_team()



    async def sh_nominate(self, message):
        '''Nominate a presidential candidate'''
        if len(message.mentions) != 1:
            # Print usage
            await message.channel.send('Syntax: sh nominate [mention user]')
            return
        if (await self.check_running(message)):
            if message.author != self.president.user:
                await message.channel.send('Error: You are not currently the %s.' % ('head coach' if self.amc_mode else 'president'))
                return
            if not self.waiting_for_nomination:
                await message.channel.send('Error: It is not currently time to choose a %s.' % ('deputy coach' if self.amc_mode else 'chancellor'))
                return
            chancellor = self.find_player(message.mentions[0])
            if not chancellor:
                await message.channel.send('Error: %s is not part of the game.' % message.mentions[0].name)
                return
            if chancellor == self.president:
                await message.channel.send('Error: you cannot nominate yourself.')
                return
            if chancellor in self.term_limited:
                await message.channel.send('Error: %s is currently term limited.' % chancellor.user.mention)
                return
            self.chancellor = chancellor
            self.waiting_for_nomination = False
            # Make a public announcement:
            await self.bot.main_channel.send('%s picked %s to be %s.' % (self.president.user.mention,
                                                                         self.chancellor.user.mention,
                                                                         ('deputy coach' if self.amc_mode else 'chancellor')))
            # Start voting!
            await self.init_voting()



    async def vote(self, message, vote):
        # Internal method to vote for or against a team
        if (await self.check_running(message)):
            if message.channel.type != discord.ChannelType.private:
                await message.delete()
                await message.channel.send('Votes should be cast in a **private message** to %s. Please try again.' % self.bot.user.mention)
                return
            player = self.find_player(message.author)
            if player is None:
                await message.channel.send('Cannot vote: you are not part of this game.')
                return
            if not self.waiting_for_votes:
                await message.channel.send('It is not currently time to vote.')
                return
            if player.vote is None:
                await message.channel.send('Thank you for voting!')
            else:
                await message.channel.send('Your vote has been updated.')
            player.vote = vote
            if not any([p.vote is None for p in self.players]):
                # Only do this *once*!
                if not self.tabulating_votes:
                    self.tabulating_votes = True
                else:
                    return
                approved = (await self.tabulate_votes())
                if self.running:
                    if approved:
                        await self.init_policies()
                    else:
                        await self.advance_team()
                # Reset the votes
                for player in self.players:
                    player.vote = None
                self.tabulating_votes = False



    async def sh_ja(self, message):
        '''Vote yes to a proposed team'''
        await self.vote(message, JA)

    async def sh_nein(self, message):
        '''Vote no to a proposed team'''
        await self.vote(message, NEIN)


    
        
    async def sh_discard(self, message):
        '''Discard a policy as president'''
        spl = message.content.lower().split()
        if (len(spl) != 3) or (spl[2] not in ('fascist', 'liberal', 'red', 'blue', 'geo', 'non-geo',
                                              'f', 'l', 'r', 'b', 'g', 'n')):
            # Print usage
            await message.channel.send('Syntax: sh discard [%s]' % ('geo or non-geo' if self.amc_mode else 'fascist or liberal'))
            return
        if (await self.check_running(message)):
            if message.channel.type != discord.ChannelType.private:
                await message.delete()
                await message.channel.send('Send a **private message** to %s, you doofus.' % self.bot.user.mention)
                return
            if message.author != self.president.user:
                await message.channel.send('Error: You are not currently the %s.' % ('head coach' if self.amc_mode else 'president'))
                return
            if not self.waiting_for_president:
                await message.channel.send('Error: It is not currently time to %s.' % \
                                           ('trivialize a math problem' if self.amc_mode else 'discard a policy'))
                return
            if spl[2] in ('fascist', 'red', 'geo', 'f', 'r', 'g'):
                to_discard = FASCIST
            else:
                to_discard = LIBERAL
            if to_discard not in self.policies:
                await message.channel.send('Error: no %s of that type exist. Please try again.' % ('problems' if self.amc_mode else 'policies'))
                return
            await message.channel.send('Thank you for making your selection!')
            self.policies.remove(to_discard)
            random.shuffle(self.policies) # No fancy communication!
            self.waiting_for_president = False
            # Inform the chancellor
            await self.chancellor.user.send('%s gave you the following two %s: %s, %s. Please choose one of them to %s using "sh %s"' % \
                                            (self.president.user.mention,
                                             'problems' if self.amc_mode else 'policies',
                                             self.POLICY_NAMES[self.policies[0]], self.POLICY_NAMES[self.policies[1]],
                                             'solve' if self.amc_mode else 'enact',
                                             'solve' if self.amc_mode else 'enact'))
            self.waiting_for_chancellor = True


    
        
    async def sh_enact(self, message):
        '''Enact a policy as chancellor'''
        spl = message.content.lower().split()
        if (len(spl) != 3) or (spl[2] not in ('fascist', 'liberal', 'red', 'blue', 'geo', 'non-geo',
                                              'f', 'l', 'r', 'b', 'g', 'n')):
            # Print usage
            await message.channel.send('Syntax: sh enact [%s]' % ('geo or non-geo' if self.amc_mode else 'fascist or liberal'))
            return
        if (await self.check_running(message)):
            if message.channel.type != discord.ChannelType.private:
                await message.delete()
                await message.channel.send('Send a **private message** to %s, you doofus.' % self.bot.user.mention)
                return
            if message.author != self.chancellor.user:
                await message.channel.send('Error: You are not currently the %s.' % ('deputy coach' if self.amc_mode else 'chancellor'))
                return
            if not self.waiting_for_chancellor:
                await message.channel.send('Error: It is not currently time to %s.' % \
                                           ('solve a math problem' if self.amc_mode else 'enact a policy'))
                return
            if spl[2] in ('fascist', 'red', 'geo', 'f', 'r', 'g'):
                to_enact = FASCIST
            else:
                to_enact = LIBERAL
            if to_enact not in self.policies:
                await message.channel.send('Error: no %s of that type exist. Please try again.' % ('problems' if self.amc_mode else 'policies'))
                return
            await message.channel.send('Thank you for making your selection!')
            self.policies = [to_enact]
            self.waiting_for_chancellor = False
            # Tabulate the result
            if not self.tabulating_policies:
                self.tabulating_policies = True
                await self.tabulate_policies()
                if self.running and not self.waiting_for_special:
                    await self.advance_team()
                self.tabulating_policies = False



    async def sh_veto(self, message):
        '''Veto a policy'''
        if (await self.check_running(message)):
            # Error checking
            if message.author not in (self.chancellor.user, self.president.user):
                await message.channel.send('Error: You are not in a position to veto.')
                return
            if self.fascist_policies < 5:
                await message.channel.send('Error: Veto power has not been unlocked yet.')
                return
            if not ((message.author == self.chancellor.user) and self.waiting_for_chancellor):
                if not ((message.author == self.president.user) and self.waiting_for_veto):
                    await message.channel.send('Error: It is not currently time to veto.')
                    return
            # Veto as chancellor
            if message.author == self.chancellor.user:
                await self.bot.main_channel.send('**%s wishes to veto.** %s, please respond using either "sh veto" or "sh noveto".' % \
                                                 (self.chancellor.user.mention, self.president.user.mention))
                self.waiting_for_chancellor = False
                self.waiting_for_veto = True
                return
            # Veto as president
            self.waiting_for_veto = False
            await self.bot.main_channel.send('**%s agrees to the veto.**' % self.president.user.mention)
            # Advance the team
            await self.advance_team()



    async def sh_noveto(self, message):
        '''Decline a veto as president'''
        if (await self.check_running(message)):
            # Error checking
            if not ((message.author == self.president.user) and (self.fascist_policies == 5) and self.waiting_for_veto):
                await message.channel.send('Error: You are not in a position to decline a veto.')
            # Decline a veto as president
            self.waiting_for_veto = False
            self.waiting_for_chancellor = True
            await self.bot.main_channel.send('**%s has refused to allow the veto.** %s, please choose a %s.' % \
                                             (self.president.user.mention, self.chancellor.user.mention,
                                              'problem to solve' if self.amc_mode else 'policy to enact'))



    async def sh_investigate(self, message):
        '''As President, use the Investigate Loyalty presidential power'''
        if len(message.mentions) != 1:
            # Print usage
            await message.channel.send('Syntax: sh investigate [mention target]')
            return
        if (await self.check_running(message)):
            if not (self.waiting_for_special and (self.board[self.fascist_policies-1] == INVESTIGATE_LOYALTY)):
                await message.channel.send('Error: It is not currently time to investigate someone.')
                return
            if message.author != self.president.user:
                await message.channel.send('Error: You are not currently the %s.' % ('head coach' if self.amc_mode else 'president'))
                return
            target = message.mentions[0]
            player = self.find_player(target)
            if not player:
                await message.channel.send('Error: %s is not part of the game.' % target.name)
                return
            if player.user == message.author:
                await message.channel.send('Error: you cannot investigate yourself.')
                return
            if player in self.investigated:
                await message.channel.send('Error: you cannot investigate someone who has already been investigated.')
                return
            self.waiting_for_special = False
            # Make a public announcement
            await self.bot.main_channel.send('**%s:** %s has chosen to investigate %s.' % \
                                             (self.POWER_NAMES[INVESTIGATE_LOYALTY], self.president.user.mention, player.user.mention))
            # Send a private message
            await self.president.user.send('Investigative result: %s is a **%s**' % (player.user.name, self.ROLE_NAMES[player.party]))
            # Advance the team
            await self.advance_team()



    async def sh_elect(self, message):
        '''As President, use the Call Special Election presidential power'''
        if len(message.mentions) != 1:
            # Print usage
            await message.channel.send('Syntax: sh elect [mention target]')
            return
        if (await self.check_running(message)):
            if not (self.waiting_for_special and (self.board[self.fascist_policies-1] == SPECIAL_ELECTION)):
                await message.channel.send('Error: It is not currently time to call %s.' % ('an emergency jury meeting' if self.amc_mode else 'a special election'))
                return
            if message.author != self.president.user:
                await message.channel.send('Error: You are not currently the %s.' % ('head coach' if self.amc_mode else 'president'))
                return
            target = message.mentions[0]
            player = self.find_player(target)
            if not player:
                await message.channel.send('Error: %s is not part of the game.' % target.name)
                return
            if player.user == message.author:
                await message.channel.send('Error: you cannot choose yourself.')
                return
            self.last_president = self.president
            self.president = player
            self.chancellor = None
            self.waiting_for_special = False
            # Make a public announcement
            await self.bot.main_channel.send('**%s:** %s has appointed %s as the next %s.' % \
                                             (self.POWER_NAMES[SPECIAL_ELECTION],
                                              self.last_president.user.mention, self.president.user.mention,
                                              'head coach' if self.amc_mode else 'president'))
            # Initialize the team
            await self.init_team()



    async def sh_execute(self, message):
        '''As President, use the Execution presidential power'''
        if len(message.mentions) != 1:
            # Print usage
            await message.channel.send('Syntax: sh execute [mention target]')
            return
        if (await self.check_running(message)):
            if not (self.waiting_for_special and (self.board[self.fascist_policies-1] == EXECUTION)):
                await message.channel.send('Error: It is not currently time to investigate someone.')
                return
            if message.author != self.president.user:
                await message.channel.send('Error: You are not currently the %s.' % ('head coach' if self.amc_mode else 'president'))
                return
            target = message.mentions[0]
            player = self.find_player(target)
            if not player:
                await message.channel.send('Error: %s is not part of the game.' % target.name)
                return
            self.waiting_for_special = False
            self.players.remove(player)
            self.dead_players.append(player)
            self.mute(player)
            # Make a public announcement
            await self.bot.main_channel.send('**%s:** %s has chosen to %s %s.' % \
                                             (self.POWER_NAMES[EXECUTION], self.president.user.mention,
                                              'disqualify' if self.amc_mode else 'execute',
                                              player.user.mention))
            # Check if they've killed Hitler
            if player.role == HITLER:
                await self.bot.main_channel.send('**The game is over. %s has been %s. %ss win!!**' % \
                                                 (self.ROLE_NAMES[HITLER],
                                                  'disqualified' if self.amc_mode else 'executed',
                                                  self.ROLE_NAMES[LIBERAL]))
                await self.finish_game()
                return
            # Advance the team
            await self.advance_team()





    # Synonyms (by popular demand)
    sh_prod = sh_poke
    sh_special = sh_powers
    sh_anand = sh_amc
    sh_noanand = sh_noamc
    sh_choose = sh_picc = sh_pick = sh_nominate
    sh_accept = sh_yes = sh_yee = sh_ok = sh_okay = sh_aight = sh_yep = sh_yeet = sh_approve = sh_ja
    sh_no = sh_nope = sh_noway = sh_rejecc = sh_reject = sh_nein
    sh_trivialize = sh_remove = sh_discard
    sh_solve = sh_implement = sh_enact
    sh_background = sh_check = sh_investigate
    sh_jury = sh_call = sh_elect
    sh_disqualify = sh_kill = sh_execute
        
        





    ##### Other game running methods #####


    async def secret_info(self):
        # Figure out how many of each role are being used
        N = len(self.players)
        n = N_FASCISTS[N]
        roles = []
        for i in range(N-n):
            roles.append((LIBERAL, LIBERAL))
        for i in range(n-1):
            roles.append((FASCIST, FASCIST))
        roles.append((HITLER, FASCIST))
        # Randomly assign them to players
        random.shuffle(roles)
        for player, (role, party) in zip(self.players, roles):
            player.role = role
            player.party = party
        # Disclose information to players as appropriate
        for player in self.players:
            info = 'Your role for this game: **%s**\nYour party: **%s**\n' % (self.ROLE_NAMES[player.role], self.ROLE_NAMES[player.party])
            # Non-Hitler Fascists know who the other fascists are, and which one is Hitler
            if player.role == FASCIST:
                other_fascists = [p.user.name for p in self.players if (p != player) and (p.role == FASCIST)]
                hitler = [p.user.name for p in self.players if (p != player) and (p.role == HITLER)][0]
                if other_fascists:
                    info += 'Other %ss: %s\n' % (self.ROLE_NAMES[FASCIST], ', '.join(other_fascists))
                info += '%s is %s\n' % (hitler, self.ROLE_NAMES[HITLER])
            # Hitler knows who the other fascist is if there are only 5-6 players
            elif (player.role == HITLER) and (N <= 6):
                other_fascist = [p.user.name for p in self.players if (p != player) and (p.role == FASCIST)][0]
                info += '%s is the other %s\n' % (other_fascist, self.ROLE_NAMES[FASCIST])
            # Send the info to the player
            await player.user.send(info)
                

        


    async def advance_team(self):
        # Advance the leadership and let the new leader pick a chancellor
        if self.last_president:
            # Resuming where we left off after a special election
            self.president = self.last_president
            self.last_president = None
        self.president = self.president.next
        while self.president in self.dead_players:
            self.president = self.president.next # Skip over anyone who is dead
        self.chancellor = None
        await self.init_team()



    async def init_team(self):
        # Initialize the new leadership
        await self.bot.main_channel.send('%s is now the %s. Nominate a candidate for %s using "sh nominate".' % \
                                     (self.president.user.mention,
                                      'head coach' if self.amc_mode else 'president',
                                      'deputy coach' if self.amc_mode else 'chancellor'))
        # Special messages if necessary
        if self.election_tracker == 2:
            await self.bot.main_channel.send('**Warning: A random %s will be %s if this vote fails.**' % \
                                             ('problem' if self.amc_mode else 'policy',
                                              'solved' if self.amc_mode else 'enacted'))
        self.waiting_for_nomination = True



    async def init_voting(self):
        # Reset everyone's votes and let them cast votes again
        if not self.waiting_for_votes:
            for player in self.players:
                player.vote = None
            await self.bot.main_channel.send('''Everyone: the candidates are %s for %s and %s for %s.
Please cast your votes **privately** by DMing either "sh ja" or "sh nein" to %s.''' % \
                                             (self.president.user.mention,
                                              'head coach' if self.amc_mode else 'president',
                                              self.chancellor.user.mention,
                                              'deputy coach' if self.amc_mode else 'chancellor',
                                              self.bot.user.mention))
            self.waiting_for_votes = True



    async def tabulate_votes(self):
        # Tabulate the votes that were cast
        if self.waiting_for_votes:
            self.waiting_for_votes = False
            voting_msg = (await self.bot.main_channel.send('Voting has concluded. Results are:\n%s' % \
                                                       '\n'.join(['%s: %s' % (p.user.name, 'Ja' if p.vote == JA else 'Nein') for p in self.players])))
            await voting_msg.delete(delay=VOTE_DELAY) # Delete after a certain time
            if sum([p.vote for p in self.players]) > len(self.players) // 2:
                await self.bot.main_channel.send('The team of %s and %s was approved!' % (self.president.user.mention, self.chancellor.user.mention))
                self.election_tracker = 0
                # Impose term limits
                if len(self.players) == 5:
                    self.term_limited = [self.chancellor]
                else:
                    self.term_limited = [self.president, self.chancellor]
                # Check right now if Hitler was elected chancellor
                if (self.chancellor.role == HITLER) and (self.fascist_policies >= 3):
                    await self.bot.main_channel.send('**The game is over. %s has been elected %s. %ss win!!**' % \
                                                     (self.ROLE_NAMES[HITLER],
                                                      'deputy coach' if self.amc_mode else 'chancellor',
                                                      self.ROLE_NAMES[FASCIST]))
                    await self.finish_game()
                    return False
                return True
            self.election_tracker += 1
            await self.bot.main_channel.send('The team of %s and %s was rejected. Election tracker is now at **%d** out of 3.' % \
                                             (self.president.user.mention, self.chancellor.user.mention, self.election_tracker))
            if self.election_tracker == 3:
                await self.chaos()
        return False



    async def chaos(self):
        # Enact a *random* policy!
        self.election_tracker = 0
        self.term_limited = []
        policy = self.policy_deck.pop()
        if policy == LIBERAL:
            self.liberal_policies += 1
        else:
            self.fascist_policies += 1
        await self.bot.main_channel.send('**Chaos:** The top %s from the deck, a **%s %s**, has been %s.' % \
                                         ('problem' if self.amc_mode else 'policy',
                                          self.POLICY_NAMES[policy],
                                          'problem' if self.amc_mode else 'policy',
                                          'solved' if self.amc_mode else 'enacted'))
        await self.check_for_winner()
        if self.running:
            await self.shuffle_policies()



    async def shuffle_policies(self):
        # Shuffle the policy deck if necessary
        if len(self.policy_deck) < 3:
            self.policy_deck = [LIBERAL] * (6 - self.liberal_policies) + [FASCIST] * (11 - self.fascist_policies)
            random.shuffle(self.policy_deck)
            await self.bot.main_channel.send('*Shuffling the %s deck...*' % ('problem' if self.amc_mode else 'policy'))



    async def init_policies(self):
        # Give three policies from the top of the deck to the president
        if not self.waiting_for_president:
            # Take the top three policies
            self.policies = self.policy_deck[-3:]
            del self.policy_deck[-3:]
            # Inform the president
            await self.president.user.send('The following three %s were taken from the deck: %s. Please choose one of them to discard by DMing \
"sh discard %s" or "sh discard %s" to %s.' % \
                                            ('problems' if self.amc_mode else 'policies',
                                             ', '.join([self.POLICY_NAMES[i] for i in self.policies]),
                                             self.POLICY_NAMES[LIBERAL].lower(), self.POLICY_NAMES[FASCIST].lower(),
                                             self.bot.user.mention))
            self.waiting_for_president = True
            for p in (self.president, self.chancellor):
                self.mute(p) # Don't let them talk while they are deciding



    async def tabulate_policies(self):
        # Determine what kind of policy was passed
        async with self.bot.main_channel.typing():
            await asyncio.sleep(5) # Pause for dramatic effect
        policy = self.policies[0]
        self.policies = []
        if policy == LIBERAL:
            self.liberal_policies += 1
        else:
            self.fascist_policies += 1
        await self.bot.main_channel.send('**A %s %s was %s.**' % (self.POLICY_NAMES[policy],
                                                                  'problem' if self.amc_mode else 'policy',
                                                                  'solved' if self.amc_mode else 'enacted'))
        for p in (self.president, self.chancellor):
            self.unmute(p) # Let the president and chancellor talk again
        await self.check_for_winner()
        await self.shuffle_policies()
        if self.running and (policy == FASCIST):
            # Make any special announcements necessary
            if self.fascist_policies == 3:
                await self.bot.main_channel.send('**Warning: %ss will win if %s is elected %s.**' % \
                                                 (self.ROLE_NAMES[FASCIST], self.ROLE_NAMES[HITLER],
                                                  'deputy coach' if self.amc_mode else 'chancellor'))
            elif self.fascist_policies == 5:
                await self.bot.main_channel.send('**Veto power has been unlocked!** In the future, the %s \
may move to veto an agenda proposed by the %s by typing "sh veto".' % \
                                                 ('deputy coach' if self.amc_mode else 'chancellor',
                                                  'head coach' if self.amc_mode else 'president'))
            # Figure out if the President gets to use a special power
            power = self.board[self.fascist_policies - 1]
            if power == INVESTIGATE_LOYALTY:
                await self.bot.main_channel.send('**%s:** %s, choose someone to investigate using "sh investigate".' % \
                                                 (self.POWER_NAMES[power], self.president.user.mention))
                self.waiting_for_special = True
            elif power == SPECIAL_ELECTION:
                await self.bot.main_channel.send('**%s:** %s, choose someone to be the next candidate for %s using "sh elect".' % \
                                                 (self.POWER_NAMES[power], self.president.user.mention,
                                                  'head coach' if self.amc_mode else 'president'))
                self.waiting_for_special = True
            elif power == POLICY_PEEK:
                # This one happens right away, since the president doesn't have to make a decision
                await self.bot.main_channel.send('**%s:** *%s has looked at the top three %s in the deck.*' % \
                                                 (self.POWER_NAMES[power], self.president.user.mention,
                                                  'problems' if self.amc_mode else 'policies'))
                await self.president.user.send('**%s:** The top three %s in the deck are: %s. (The first one is on top.)' % \
                                               (self.POWER_NAMES[power],
                                                'problems' if self.amc_mode else 'policies',
                                                ', '.join([self.POLICY_NAMES[i] for i in self.policy_deck[-1:-4:-1]])))
            elif power == EXECUTION:
                await self.bot.main_channel.send('**%s:** %s, choose someone to %s using "sh %s".' % \
                                                 (self.POWER_NAMES[power], self.president.user.mention,
                                                  'disqualify' if self.amc_mode else 'execute',
                                                  'disqualify' if self.amc_mode else 'execute'))
                self.waiting_for_special = True


    


    async def check_for_winner(self):
        # Check for a winner
        if self.fascist_policies == 6:
            await self.bot.main_channel.send('**The game is over. %ss win!!**' % self.ROLE_NAMES[FASCIST])
            await self.finish_game()
        elif self.liberal_policies == 5:
            await self.bot.main_channel.send('**The game is over. %ss win!!**' % self.ROLE_NAMES[LIBERAL])
            await self.finish_game()



    async def finish_game(self):
        # Announce the roles and clear the `running' flag
        self.owner = None
        self.running = False
        info = '**Game role reveals:**\n'
        for p in self.players + self.dead_players:
            info += '%s: %s\n' % (p.user.mention, self.ROLE_NAMES[p.role])
        await self.bot.main_channel.send(info)
        # Unmute everyone
        self.unmute_all()
            

