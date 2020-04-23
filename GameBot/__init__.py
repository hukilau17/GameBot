# Discord GameBot class
# Matthew Kroesche

try:
    import GameBot.server_settings
except ImportError:
    pass

from GameBot.bot import GameBot

from GameBot.avalon import Avalon
from GameBot.liars_dice import LiarsDice
from GameBot.secret_hitler import SecretHitler

games = [Avalon, LiarsDice, SecretHitler]

if __name__ == '__main__':
    client = GameBot(games, debug=True)
    client.run()
