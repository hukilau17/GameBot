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
from GameBot.snarkback import Snarkback
from GameBot.codenames import Codenames

games = [Avalon, LiarsDice, SecretHitler, Snarkback, Codenames]

if __name__ == '__main__':
    client = GameBot(games, debug=True)
    client.run()
