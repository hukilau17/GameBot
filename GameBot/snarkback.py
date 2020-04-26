# Snarkback game bot
# Matthew Kroesche

import discord
import recordclass
import random
import os
import asyncio
import urllib.request

from .game import Game



Player = recordclass.recordclass('Player', 'user score round_score prompts snarks votes num_votes')
# user: the discord.User controlling this player
# score: the score of this player at the end of the last round
# round_score: the number of points accumulated by this player in the current round
# prompts: the list of string prompts given to this player
# snarks: the list of string responses by this player to the prompts
# votes: the list of integer indices representing votes cast by this player
# num_votes: the number of votes this player needs to cast



MAX_SNARK_SIZE = 50 # The maximum length of a reply to a prompt
PROMPT_TIMER = 60 # The timer for a prompt (if timers are turned on)
VOTING_TIMER = 15 # The timer for voting (if timers are turned on)







class Snarkback(Game):

    name = 'Snarkback'
    prefix = 'sb'

    def create_player(self, user):
        return Player(user, 0, 0, [], [], [], 0)

    async def create(self, message):
        self.round          = 0     # The current number of the round we are on
        self.prompts        = []    # The list of prompts being used in this round
        self.snarks         = []    # The list of players' replies to prompts. Each reply is of the form [prompt, (reply, player), (reply, player), ...]
        self.questions      = []    # The database of questions.
        self.audience_votes = []    # List of votes received from the audience. Each is the index of a snark.
        self.current_snark  = None  # The snark currently being voted on
        self.voting         = False # True if the voting for this prompt is currently open.
        self.timed          = False # True if this is a timed game
        self.timer_task     = None  # The current timer task, if any


    async def setup(self):
        try:
            url = os.getenv('GAMEBOT_SB_QUESTIONS')
            with urllib.request.urlopen(url) as o:
                data = o.read()
            if isinstance(data, bytes):
                data = data.decode()
            self.QUESTIONS = data.strip().splitlines()
            if self.owner:
                await self.bot.main_channel.send('*Snarkback prompts have been loaded!*')
        except:
            await self.bot.main_channel.send('*Error loading Snarkback prompts!!*')


    async def start(self, message):
        if len(self.players) < 3:
            await message.channel.send('Cannot start: the game should have at least 3 players')
            self.running = False
            return
        if not hasattr(self, 'QUESTIONS'):
            await message.channel.send('Cannot start: the questions have not been loaded yet. Please wait a moment.')
            self.running = False
            return
        # Set up the list of questions
        self.questions = self.QUESTIONS[:]
        # No upper limit on the number of players :P
        # Make a public announcement
        await self.bot.main_channel.send('The game has now been started!')
        await self.begin_round()



    async def sb_info(self, message):
        '''Print out the current game info'''
        if (await self.check_game(message)):
            players = sorted(self.players, key = lambda x: x.score, reverse=True)
            info = '**Current standings:**\n%s\n' % '\n'.join(['%s: %d' % (player.user.name, player.score) for player in players])
            info += 'Game owner: %s\n' % self.owner.user.mention
            if self.round:
                info += 'Current round: %d' % self.round
            else:
                info += '*The game has not started yet.*'
            await message.channel.send(info)
            if self.running:
                await self.sb_poke(message)



    async def sb_poke(self, message):
        '''Pokes people who need to make a decision'''
        if (await self.check_running(message)):
            waiting = []
            if self.snarks:
                waiting = [p for p in self.players if len(p.votes) < p.num_votes]
                if waiting:
                    await self.bot.main_channel.send('*Currently waiting for %d player%s to vote.*' % (len(waiting), '' if len(waiting) == 1 else 's'))
                    for p in waiting:
                        await p.user.send('*Waiting for you to vote!*')
                    return
            else:
                waiting = [p for p in self.players if len(p.snarks) < len(p.prompts)]
                if waiting:
                    await self.bot.main_channel.send('*Currently waiting for the following players to reply to prompts: %s*' % ', '.join([p.user.mention for p in waiting]))
                    return
            await self.bot.main_channel.send('*Not currently waiting for anyone to make a decision.*')



    async def sb_timer(self, message):
        '''Turn on timer mode'''
        if (await self.check_owner(message)):
            # For now, the host is allowed to change the timer settings mid-game; they'll
            # go into effect the next time something happens that would require a timer.
            self.timed = True
            await self.bot.main_channel.send('*Timer mode has been turned on.*')

            
    async def sb_notimer(self, message):
        '''Turn off timer mode'''
        if (await self.check_owner(message)):
            self.timed = False
            await self.bot.main_channel.send('*Timer mode has been turned off.*')



    async def begin_round(self):
        # Start the next round
        if self.round == 3:
            await self.bot.main_channel.send('**The game is over.** Thank you for playing!')
            self.owner = None
            self.running = False
            return # And we're done!
        self.round += 1
        self.snarks = []
        self.current_snark = None
        if self.round < 3:
            # Randomly pick one question for each player
            self.prompts = random.sample(self.questions, len(self.players))
            # Randomly assign each player two questions, so that each question is assigned
            # to exactly two players.
            # We do this by constructing a cycle. (Yay for graph theory!)
            players = list(self.players)
            prompts = list(self.prompts)
            current_player = self.players[0]
            current_prompt = random.choice(prompts)
            players.remove(current_player)
            prompts.remove(current_prompt)
            current_player.prompts = [current_prompt]
            while players:
                new_player = random.choice(players)
                new_prompt = random.choice(prompts)
                new_player.prompts = [current_prompt, new_prompt]
                players.remove(new_player)
                prompts.remove(new_prompt)
                current_player = new_player
                current_prompt = new_prompt
            self.players[0].prompts.append(current_prompt) # The first player only got one prompt at the beginning
        else:
            # Randomly pick a single question for everyone
            self.prompts = random.sample(self.questions, 1)
            for player in self.players:
                player.prompts = self.prompts[:]
        # Remove the prompts that were selected to avoid duplication in a later round
        for prompt in self.prompts:
            self.questions.remove(prompt)
        # Prompt all the players
        await self.bot.main_channel.send('**Round %d has begun!** All players, please check your DMs and reply to the prompts using "sb snark [reply]"' % self.round)
        if self.round == 3:
            await self.bot.main_channel.send('Everyone gets the same prompt!\n**Prompt:** %s' % self.prompts[0])
        if self.timed:
            # Start the timer if necessary
            self.timer_task = asyncio.create_task(self.timer('Time remaining to respond to prompts', PROMPT_TIMER, self.end_prompt), name='Prompt Timer')
        for player in self.players:
            player.snarks = []
            player.votes = []
            await self.next_prompt(player)



    async def timer(self, msg, delay, after):
        message = (await self.bot.main_channel.send('%s: **%d** seconds' % (msg, delay)))
        loop = asyncio.get_running_loop()
        start = loop.time()
        try:
            while True:
                # Update the clock every 1 second.
                await asyncio.sleep(1)
                remaining = max(0, delay - int(round(loop.time() - start)))
                await message.edit(content = '%s: **%d** seconds' % (msg, remaining))
                if remaining == 0:
                    # Time is up, use the after() coroutine to move things along
                    await message.delete()
                    await message.edit(content = 'Time\'s up!')
                    await after()
                    return
        except asyncio.CancelledError:
            # We're not waiting on anyone else
            await message.delete()
            raise
            



    async def next_prompt(self, player):
        await player.user.send('**Your latest prompt:** %s' % player.prompts[len(player.snarks)])

    async def end_prompt(self):
        if not self.snarks:
            self.shuffle_snarks()
            await self.bot.main_channel.send('Thanks for your awesome replies! Now let\'s start voting!')
            await self.next_vote()



    async def sb_snark(self, message):
        '''Submit a response to a prompt'''
        if (await self.check_running(message)):
            # Error checking
            if message.channel.type != discord.ChannelType.private:
                await message.delete()
                await message.channel.send('Replies should be made in a **private message** to %s. Please try again.' % self.bot.user.mention)
                return
            player = self.find_player(message.author)
            if player is None:
                await message.channel.send('Error: you are not currently part of this game.')
                return
            if len(player.snarks) == len(player.prompts):
                await message.channel.send('Error: it is not currently time to snark.')
                return
            try:
                snark = message.content.split(None, 2)[2]
            except IndexError:
                await message.channel.send('Syntax: sb snark [your zinger goes here].')
                return
            if len(snark) > MAX_SNARK_SIZE:
                await message.channel.send('Your reply is too long, it should be at most %d characters. Please try again.' % MAX_SNARK_SIZE)
                return
            await message.channel.send('Thank you for your reply!')
            snark = snark.upper()
            player.snarks.append(snark)
            if len(player.snarks) < len(player.prompts):
                await self.next_prompt(player)
            elif all([len(p.snarks) == len(p.prompts) for p in self.players]):
                if not self.snarks:
                    if self.timer_task:
                        # Stop the timer if it's running
                        if not self.timer_task.done():
                            self.timer_task.cancel()
                        self.timer_task = None
                    await self.end_prompt()



    async def sb_form(self, message):
        '''Get the Google form for submitting custom questions'''
        await message.channel.send(os.getenv('GAMEBOT_SB_FORM', 'Oops, couldn\'t find the form'))



    def shuffle_snarks(self):
        # Add `None` to unanswered prompts if necessary
        for player in self.players:
            while len(player.prompts) < len(player.snarks):
                player.prompts.append(None)
        # Shuffle everyone's replies and put them in the list
        for prompt in self.prompts:
            snarks = []
            for player in self.players:
                if prompt in player.prompts:
                    snarks.append((player.snarks[player.prompts.index(prompt)], player))
            random.shuffle(snarks) # Shuffle the order of the snarks
            self.snarks.append([prompt] + snarks)
        # Empty out other data structures
        self.prompts = []
        for player in self.players:
            player.prompts = []
            player.snarks = []



    async def next_vote(self):
        # Begin voting on the next snark
        if not self.snarks:
            await self.finish_round()
            return
        self.current_snark = self.snarks.pop(0)
        prompt = self.current_snark[0]
        replies = self.current_snark[1:]
        await self.bot.main_channel.send('**Next prompt:**')
        async with self.bot.main_channel.typing():
            await asyncio.sleep(5) # Pause for dramatic effect
        # Put together the snark embed
        embed = discord.Embed(title=self.name, description=prompt, type='rich', colour=discord.Colour.blue())
        nonvoting = []
        for i, (reply, player) in enumerate(replies, 1):
            embed.add_field(name='%d.' % i, value=reply, inline=False)
            if self.round != 3:
                nonvoting.append(player)
        await self.bot.main_channel.send(embed=embed)
        # Check for a jinx
        if (self.round != 3) and (replies[0][0] == replies[1][0]):
            await self.bot.main_channel.send('**Jinx!** Both snarks are exactly the same. Nobody gets any points.')
            await self.next_vote()
            return
        await self.bot.main_channel.send('Everyone: please vote on a reply to the prompt. Do this by DMing "sb vote [num]" to %s, \
where [num] is the integer number of the snark. People who are not part of the game can vote too! Also you can type "sb vote 0" to abstain.' \
                                         % self.bot.user.mention)
        # Set up everyone's voting data
        if self.round == 3:
            num_votes = min(len(self.players) // 2, 3)
        else:
            num_votes = 1
        for p in self.players:
            if p not in nonvoting:
                p.votes = []
                p.num_votes = num_votes
        self.audience_votes = []
        self.voting = True # Turn on voting
        if self.timed:
            # Start the timer if necessary
            self.timer_task = asyncio.create_task(self.timer('Time remaining to vote', VOTING_TIMER, self.end_voting), name='Voting Timer')



    async def sb_vote(self, message):
        '''Vote on a response to a prompt'''
        if (await self.check_running(message)):
            # Error checking
            if message.channel.type != discord.ChannelType.private:
                await message.delete()
                await message.channel.send('Votes should be cast in a **private message** to %s. Please try again.' % self.bot.user.mention)
                return
            player = self.find_player(message.author)
            if not self.voting:
                await message.channel.send('Error: it is not currently time to vote.')
                return
            spl = message.content.split()
            try:
                assert len(spl) == 3
                vote = int(spl[2])
            except (AssertionError, ValueError):
                await message.channel.send('Syntax: sb vote [integer_number]')
                return
            if not (0 <= vote <= len(self.current_snark[1:])):
                await message.channel.send('Error: invalid snark number')
                return
            if player:
                # Player voting
                if len(player.votes) == player.num_votes:
                    if player.num_votes == 0:
                        await message.channel.send('Error: you cannot vote for or against your own reply')
                    else:
                        await message.channel.send('Error: you have already finished voting')
                    return
                if (vote in player.votes) and (vote != 0):
                    await message.channel.send('Error: you have already voted for that option. Please pick a different one.')
                    return
                if (vote != 0) and (self.current_snark[vote][1] == player):
                    await message.channel.send('Error: you cannot vote for your own reply')
                    return
                player.votes.append(vote)
                need_more = (len(player.votes) < player.num_votes)
                if need_more and (vote == 0):
                    # Just abstain until we don't need to vote anymore
                    player.votes.extend( [0] * (player.num_votes - len(player.votes)) )
                    need_more = False
            else:
                # Audience voting
                if any([v[1] == message.author for v in self.audience_votes]):
                    await message.channel.send('Error: you have already voted')
                    return
                if vote != 0:
                    self.audience_votes.append((vote, message.author))
                need_more = False
            # Ping the user back
            await message.channel.send('Thank you for voting!')
            if need_more:
                await message.channel.send('Please cast another vote.')
            elif all([len(p.votes) == p.num_votes for p in self.players]):
                # Check if we're finally done
                if self.voting:
                    if self.timer_task:
                        # Stop the timer if it's running
                        if not self.timer_task.done():
                            self.timer_task.cancel()
                        self.timer_task = None
                    await self.end_voting()



    async def end_voting(self):
        if self.voting:
            self.voting = False
            await self.tabulate_votes()
            await self.next_vote()



    async def tabulate_votes(self):
        # Figure out who won and how many points to award
        total_votes = sum([p.num_votes for p in self.players]) + len(self.audience_votes)
        results = []
        for i, (reply, player) in enumerate(self.current_snark[1:], 1):
            # Find everyone who voted for this snark
            data = []
            for p in self.players:
                if i in p.votes:
                    data.append((p.votes.index(i) + 1, p.user))
            for v, u in self.audience_votes:
                if v == i:
                    data.append((2, u))
            # Find out the score
            total = False
            if self.round != 3:
                score = 1000.0 * self.round * len(data) / total_votes
                # Add a bonus if someone has *all* the votes!
                if all([p.votes[0] in (0, i) for p in self.players if p.votes]) and all([v == i for v in self.audience_votes]):
                    score += 100.0 * self.round
                    total = True
            else:
                score = 1500.0 * sum([4-i for i, u in data]) / total_votes
            score = int(round(score))
            player.round_score += score
            # Add a line to the results
            embed = discord.Embed(title=self.name, description=reply, type='rich', colour=discord.Colour.blue())
            embed.add_field(name='Player', value=player.user.mention, inline=False)
            if data:
                embed.add_field(name='Votes', value=', '.join([u.mention for i, u in data]))
            embed.add_field(name='Score', value='**%d**' % score, inline=False)
            if total:
                embed.add_field(name='', value='*Total Snarkery!*') # Yes it's dumb, I know
            results.append((embed, score))
        # Sort the lines and print them out one by one
        results.sort(key = lambda x: x[1])
        await self.bot.main_channel.send('And the results are...')
        for embed, score in results:
            async with self.bot.main_channel.typing():
                await asyncio.sleep(3) # Pause for dramatic effect
            await self.bot.main_channel.send(embed=embed)
        
        
                    
        
    async def finish_round(self):
        await self.bot.main_channel.send('**Round %d has ended!** The results are...' % self.round)
        async with self.bot.main_channel.typing():
            await asyncio.sleep(5) # Pause for dramatic effect
        for p in self.players:
            p.score += p.round_score
            p.round_score = 0
        players = sorted(self.players, key = lambda x: x.score, reverse=True)
        await self.bot.main_channel.send('\n'.join(['%s: %d' % (player.user.mention, player.score) for player in players]))
        await self.begin_round() # Start the next round
        


