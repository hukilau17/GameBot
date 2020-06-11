# Snarkback game bot
# Matthew Kroesche

import discord
import recordclass
import random
import os
import datetime
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

# Timer settings
PROMPT_TIMER = 90 # The timer for a prompt
FINAL_PROMPT_TIMER = 45 # The timer for a prompt in round three
VOTING_TIMER = 20 # The timer for voting
FINAL_VOTING_TIMER = 40 # The timer for voting in round three
WARNING_TIME = 10 # The time at which a warning message is DMed to everyone we're waiting on

RESET_DELAY = datetime.timedelta(hours=6) # After six hours of inactivity, reset all the questions







##### Deck helper class #####


class Deck(object):

    def __init__(self):
        self.questions = []
        self.normal_questions = []
        self.custom_questions = []
        self.used_questions = []
        self.loaded = False
        self.length = 0
        self.custom_ratio = 1


    deck_cache = {}


    def cache_for_server(self, guild):
        if self.loaded:
            self.deck_cache[guild.id] = self


    @classmethod
    def load_for_server(cls, guild):
        for id, deck in cls.deck_cache.items():
            if id == guild.id:
                return deck
        new = cls.global_deck.copy()
        new.cache_for_server(guild)
        return new


    def load(self):
        # Load all the questions from the file
        if not self.loaded:
            url = os.getenv('GAMEBOT_SB_QUESTIONS')
            with urllib.request.urlopen(url) as o:
                data = o.read()
            if isinstance(data, bytes):
                data = data.decode()
            questions = data.strip().splitlines()
            separator = questions.index('')
            self.normal_questions = questions[:separator]
            self.custom_questions = questions[separator+1:]
            self.loaded = True
        self.questions = []
        self.used_questions = []
        self.length = 0


    def copy(self):
        # Create and return a copy of this deck
        new = Deck()
        new.questions = self.questions[:]
        new.normal_questions = self.normal_questions[:]
        new.custom_questions = self.custom_questions[:]
        new.used_questions = self.used_questions[:]
        new.loaded = self.loaded
        new.length = self.length
        new.custom_ratio = self.custom_ratio
        return new


    def shuffle(self):
        # Shuffle all the questions back into the pool, duplicating custom questions
        # the appropriate number of times
        self.questions = self.normal_questions + self.custom_questions * self.custom_ratio
        if self.custom_ratio:
            self.length = len(self.normal_questions) + len(self.custom_questions)
        else:
            self.length = len(self.normal_questions)
        self.used_questions = []
        random.shuffle(self.questions)


    def draw(self, n):
        # Draw and return `n` questions from the pool, and mark them used so they
        # will not appear again until the deck is reshuffled
        if self.length < n:
            self.shuffle()
        questions = []
        while len(questions) < n:
            question = self.questions.pop()
            if question in self.used_questions:
                continue
            questions.append(question)
            self.used_questions.append(question)
            self.length -= 1
        return questions
            
            
        
Deck.global_deck = Deck()
    
        















##### Main class #####



class Snarkback(Game):

    name = 'Snarkback'
    prefix = 'sb'
    

    def __init__(self, bot):
        Game.__init__(self, bot)
        self.last_start = None

    def create_player(self, user):
        return Player(user, 0, 0, [], [], [], 0)

    async def create(self, message):
        self.round          = 0     # The current number of the round we are on
        self.prompts        = []    # The list of prompts being used in this round
        self.snarks         = []    # The list of players' replies to prompts. Each reply is of the form [prompt, (reply, player), (reply, player), ...]
        self.audience_votes = []    # List of votes received from the audience. Each is the index of a snark.
        self.current_snark  = None  # The snark currently being voted on
        self.voting         = False # True if the voting for this prompt is currently open.
        self.timed          = True  # True if this is a timed game
        self.timer_task     = None  # The current timer task, if any
        self.delay_time     = None  # The current delay set on the timer
        self.starting_time  = None  # The time when the timer started, if any
        # Create the deck
        self.deck = Deck.load_for_server(self.main_channel.guild)


    async def setup(self):
        Deck.global_deck.load()
        if self.owner:
            await self.main_channel.send('*Snarkback prompts have been loaded!*')


    async def start(self, message):
        if len(self.players) < 3:
            await message.channel.send('Cannot start: the game should have at least 3 players')
            self.running = False
            return
        if not self.deck.loaded:
            if self.deck.global_deck.loaded:
                self.deck = self.deck.global_deck.copy()
                self.deck.cache_for_server(self.main_channel.guild)
            else:
                await message.channel.send('Cannot start: the questions have not been loaded yet. Please wait a moment.')
                self.running = False
                return
        # Set up the list of questions
        now = datetime.datetime.now()
        if (self.last_start is None) or (now - self.last_start > RESET_DELAY):
            self.deck.shuffle()
        self.last_start = now
        # No upper limit on the number of players :P
        # Make a public announcement
        await self.main_channel.send('The game has now been started!')
        await self.begin_round()
        



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
                # Remove the player
                self.players.remove(player)
                # Make a public announcement
                await self.main_channel.send('%s has left the game of %s.' % (message.author.mention, self.name))
                if self.running:
                    if len(self.players) < 3:
                        channel = self.main_channel()
                        self.close()
                        await channel.send('The game has been canceled because there are too few players.')
                    else:
                        # Check for things
                        await self.check_for_snarks()
                        await self.check_for_votes()




    async def sb_info(self, message):
        '''Print out the current game info'''
        if (await self.check_game(message)):
            players = sorted(self.players, key = lambda x: x.score, reverse=True)
            info = '**Current standings:**\n%s\n' % '\n'.join(['%s: %d' % (player.user.name, player.score) for player in players])
            info += 'Game owner: %s\n' % self.owner.user.mention
            if self.round:
                info += 'Current round: %d\n' % self.round
            else:
                info += '*The game has not started yet.*\n'
            if self.timed:
                info += '*This is a timed game.*'
            else:
                info += '*This is not a timed game.*'
            await message.channel.send(info)
            if self.running:
                await self.sb_poke(message)


    def waiting(self):
        # Get the list of people we're waiting for
        if self.snarks:
            return [p for p in self.players if len(p.votes) < p.num_votes]
        else:
            return [p for p in self.players if len(p.snarks) < len(p.prompts)]



    async def sb_poke(self, message):
        '''Pokes people who need to make a decision'''
        if (await self.check_running(message)):
            if not self.timed:
                # `poke` is a no-op in timed mode
                # (since it is annoying and unnecessary)
                waiting = self.waiting()
                if waiting:
                    if self.snarks:
                        await self.main_channel.send('*Currently waiting for %d player%s to vote.*' % (len(waiting), '' if len(waiting) == 1 else 's'))
                        for p in waiting:
                            await p.user.send('*Waiting for you to vote!*')
                    else:
                        await self.main_channel.send('*Currently waiting for the following players to reply to prompts: %s*' % ', '.join([p.user.mention for p in waiting]))
                else:
                    await self.main_channel.send('*Not currently waiting for anyone to make a decision.*')




    async def sb_form(self, message):
        '''Get the Google form for submitting custom questions'''
        await message.channel.send(os.getenv('GAMEBOT_SB_FORM', 'Oops, couldn\'t find the form'))



    async def sb_timer(self, message):
        '''Turn on timer mode'''
        if (await self.check_owner(message)):
            # For now, the host is allowed to change the timer settings mid-game; they'll
            # go into effect the next time something happens that would require a timer.
            self.timed = True
            await self.main_channel.send('*Timer mode has been turned on.*')

            
    async def sb_notimer(self, message):
        '''Turn off timer mode'''
        if (await self.check_owner(message)):
            self.timed = False
            await self.main_channel.send('*Timer mode has been turned off.*')



    async def sb_time(self, message):
        '''Ask how much time is left'''
        if (await self.check_running(message)):
            if not self.timed:
                await message.channel.send('There is no timer in this game.')
            elif self.starting_time is None:
                await message.channel.send('The clock is not currently running.')
            else:
                loop = asyncio.get_running_loop()
                now = loop.time()
                diff = max(self.delay_time - int(round(now - self.starting_time)), 0)
                if diff == 0:
                    await message.channel.send('Time is up!')
                else:
                    await message.channel.send('**%d** seconds remaining!' % diff)




    async def sb_ratio(self, message):
        '''Set or query the custom question ratio'''
        if (await self.check_game(message)):
            spl = message.content.split()
            if len(spl) == 2:
                await message.channel.send('*The custom question ratio is %d to 1*' % self.deck.custom_ratio)
                return
            if len(spl) != 3:
                n = None
            else:
                try:
                    n = int(spl[2])
                except ValueError:
                    n = None
            if n is None:
                await message.channel.send('Syntax: sb ratio [number]')
                return
            if n < 0:
                await message.channel.send('Cannot set negative ratio')
                return
            if n > 10:
                await message.channel.send('Ratio is too large')
                return
            if self.running:
                await message.channel.send('Cannot change ratio in the middle of a game')
                return
            self.deck.custom_ratio = n
            if self.deck.loaded:
                self.deck.shuffle()
            await self.main_channel.send('*The custom question ratio has been set to %d to 1*' % n)
        



    async def begin_round(self):
        # Start the next round
        if self.round == 3:
            channel = self.main_channel
            self.close()
            await channel.send('**The game is over.** Thank you for playing!')
            return # And we're done!
        self.round += 1
        self.snarks = []
        self.current_snark = None
        if self.round < 3:
            # Randomly pick one question for each player
            self.prompts = self.deck.draw(len(self.players))
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
            self.prompts = self.deck.draw(1)
            for player in self.players:
                player.prompts = self.prompts[:]
        # Prompt all the players
        await self.main_channel.send('**Round %d has begun!** All players, please check your DMs and reply to the prompts using "sb snark [reply]"' % self.round)
        if self.round == 3:
            await self.main_channel.send('Everyone gets the same prompt!\n**Prompt:** %s' % self.prompts[0])
        if self.timed:
            # Start the timer if necessary
            delay = (PROMPT_TIMER if self.round < 3 else FINAL_PROMPT_TIMER)
            self.timer_task = asyncio.create_task(self.timer('Time remaining to respond to prompts', delay, self.end_prompt))
        for player in self.players:
            player.snarks = []
            player.votes = []
            await self.next_prompt(player)



    async def timer(self, msg, delay, after):
        message = (await self.main_channel.send('%s: less than **%d** seconds' % (msg, delay)))
        loop = asyncio.get_running_loop()
        self.starting_time = loop.time()
        remaining = self.delay_time = delay
        warned = False
        try:
            while remaining:
                # Update the clock every 5 seconds.
                await asyncio.sleep(5)
                remaining = max(0, delay - 5 * int(round((loop.time() - self.starting_time) / 5.0)))
                await message.edit(content = '%s: less than **%d** seconds' % (msg, remaining))
                if (0 < remaining <= WARNING_TIME) and not warned:
                    warned = True
                    for p in self.waiting():
                        await p.user.send('Hurry -- only **%d** seconds remaining!' % remaining)
            # Time is up, use the after() coroutine to move things along
            await message.delete()
            self.starting_time = self.delay_time = None
            for p in self.waiting():
                await p.user.send('Time is up!')
            if after:
                await after()
            return
        except asyncio.CancelledError:
            # We're not waiting on anyone else
            await message.delete()
            self.starting_time = self.delay_time = None
            raise
            



    async def next_prompt(self, player):
        await player.user.send('**Your latest prompt:** %s' % player.prompts[len(player.snarks)])

    async def end_prompt(self):
        if not self.snarks:
            self.shuffle_snarks()
            await self.main_channel.send('Thanks for your awesome replies! Now let\'s start voting!')
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
                await message.channel.send('Your reply is too long (%d characters), it should be at most %d characters. Please try again.' % \
                                           (len(snark), MAX_SNARK_SIZE))
                return
            await message.channel.send('Thank you for your reply!')
            snark = snark.upper()
            player.snarks.append(snark)
            if len(player.snarks) < len(player.prompts):
                await self.next_prompt(player)
            else:
                await self.check_for_snarks()



    async def check_for_snarks(self):
        if all([p.snarks and (len(p.snarks) == len(p.prompts)) for p in self.players]):
            if not self.snarks:
                if self.timer_task:
                    # Stop the timer if it's running
                    if not self.timer_task.done():
                        self.timer_task.cancel()
                    self.timer_task = None
                await self.end_prompt()



    def shuffle_snarks(self):
        # Add `None` to unanswered prompts if necessary
        for player in self.players:
            while len(player.snarks) < len(player.prompts):
                player.snarks.append(None)
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


    def colour(self):
        # Change the color between rounds
        if self.round == 1:
            return discord.Colour.blue()
        if self.round == 2:
            return discord.Colour.green()
        return discord.Colour.red()



    async def next_vote(self):
        # Begin voting on the next snark
        if not self.snarks:
            await self.finish_round()
            return
        self.current_snark = self.snarks.pop(0)
        prompt = self.current_snark[0]
        replies = self.current_snark[1:]
        await self.main_channel.send('**Next prompt:**')
        async with self.main_channel.typing():
            await asyncio.sleep(5) # Pause for dramatic effect
        # Put together the snark embed
        embed = discord.Embed(title=self.name, description=prompt, type='rich', colour=self.colour())
        nonvoting = []
        blank = []
        for i, (reply, player) in enumerate(replies, 1):
            if reply is None:
                reply = '<NO RESPONSE>'
                blank.append(i)
            embed.add_field(name='**%d.**' % i, value=reply, inline=False)
            if self.round != 3:
                nonvoting.append(player)
        await self.main_channel.send(embed=embed)
        # Check for a no-contest
        if (self.round != 3) and blank:
            if len(blank) == 2:
                await self.main_channel.send('Neither %s nor %s replied to the prompt, so nobody gets any points.' % \
                                                 (replies[0][1].user.mention, replies[1][1].user.mention))
            else:
                b = replies[blank[0] - 1][1]
                a = replies[2 - blank[0]][1]
                points = 1000 * self.round
                await self.main_channel.send('%s replied, but %s did not, so %s gets the full %d points.' % \
                                                 (a.user.mention, b.user.mention, a.user.mention, points))
                a.round_score += points
            await self.next_vote()
            return
        # Check for a jinx
        if (self.round != 3) and (replies[0][0] == replies[1][0]):
            await self.main_channel.send('**Jinx!** Both snarks (%s and %s) are exactly the same. Nobody gets any points.' % \
                                             (replies[0][1].user.mention, replies[1][1].user.mention))
            await self.next_vote()
            return
        await self.main_channel.send('Everyone: please vote on a reply to the prompt. Do this by DMing "sb vote [num]" to %s, \
where [num] is the integer number of the snark. People who are not part of the game can vote too! Also you can type "sb vote 0" to abstain.' \
                                         % self.bot.user.mention)
        # Set up everyone's voting data
        if self.round == 3:
            num_votes = 3
        else:
            num_votes = 1
        for p in self.players:
            p.votes = []
            if p in nonvoting:
                p.num_votes = 0
            else:
                p.num_votes = num_votes
        self.audience_votes = []
        self.voting = True # Turn on voting
        if self.timed:
            # Start the timer if necessary
            delay = (VOTING_TIMER if self.round < 3 else FINAL_VOTING_TIMER)
            self.timer_task = asyncio.create_task(self.timer('Time remaining to vote', delay, self.end_voting))



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
            if (vote != 0) and (self.current_snark[vote][0] is None):
                await message.channel.send('Error: you cannot vote for someone who did not reply')
                return
            if player:
                # Player voting
                if len(player.votes) == player.num_votes:
                    if player.num_votes == 0:
                        await message.channel.send('Error: you cannot vote for or against your own reply')
                    else:
                        await message.channel.send('Error: you have already finished voting')
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
            else:
                await self.check_for_votes()



    async def check_for_votes(self):
        if all([len(p.votes) == p.num_votes for p in self.players]):
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
        total_votes = sum([len(p.votes) - p.votes.count(0) for p in self.players]) + len(self.audience_votes)
        if not total_votes:
            await self.main_channel.send('Nobody voted, so *nobody gets any points!*')
            return
        results = []
        for i, (reply, player) in enumerate(self.current_snark[1:], 1):
            if reply is None:
                continue # Skip over replies that timed out
            # Find everyone who voted for this snark
            voters = []
            for p in self.players:
                for j in range(p.votes.count(i)):
                    voters.append(p.user) # May contain duplicates if this is round 3
            for v, u in self.audience_votes:
                if v == i:
                    voters.append(u)
            # Find out the score
            bonus = None
            score = 1000.0 * self.round * len(voters) / total_votes
            if self.round != 3:
                # Add a bonus if someone has *all* the votes!
                if len(voters) == total_votes:
                    score += 250.0 * self.round
                    bonus = '*Total Snarkery!*' # Yes it's dumb, I know
                elif len(voters) > total_votes * 0.5:
                    score += 100.0 * self.round
                    bonus = 'Winner!'
            score = int(round(score, -1))
            player.round_score += score
            # Add a line to the results
            embed = discord.Embed(title=self.name, description=reply, type='rich', colour=self.colour())
            embed.add_field(name='**Player**', value=player.user.mention)
            embed.add_field(name='**Score**', value='**%d**' % score)
            if bonus:
                embed.add_field(name='**Bonus**', value=bonus)
            if voters:
                embed.add_field(name='**Votes**', value=', '.join([u.mention for u in voters]), inline=False)
            results.append((embed, score))
        # Sort the lines and print them out one by one
        results.sort(key = lambda x: x[1])
        await self.main_channel.send('And the results are...')
        for embed, score in results:
            async with self.main_channel.typing():
                await asyncio.sleep(3) # Pause for dramatic effect
            await self.main_channel.send(embed=embed)
        
        
                    
        
    async def finish_round(self):
        await self.main_channel.send('**Round %d has ended!** The results are...' % self.round)
        async with self.main_channel.typing():
            await asyncio.sleep(5) # Pause for dramatic effect
        for p in self.players:
            p.score += p.round_score
            p.round_score = 0
        players = sorted(self.players, key = lambda x: x.score, reverse=True)
        await self.main_channel.send('\n'.join(['%s: %d' % (player.user.mention, player.score) for player in players]))
        await self.begin_round() # Start the next round
        


