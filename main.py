import telegram
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, \
    InlineQueryHandler
from telegram.error import TelegramError

import logging
import datetime
from enum import Enum

with open("ignore/token.txt", "r") as f:
    API_TOKEN = f.read().rstrip()

with open("ignore/username.txt", "r") as f:
    USERNAME = f.read().rstrip()
    DM_URL = "http://t.me/{}".format(USERNAME)

def get_static_handler(command):
    """
    Given a string command, returns a CommandHandler for that string that
    responds to messages with the content of static_responses/[command].txt

    Throws IOError if file does not exist or something
    """

    f = open("static_responses/{}.txt".format(command), "r")
    response = f.read()

    return CommandHandler(command, \
        ( lambda bot, update : \
        bot.send_message(chat_id=update.message.chat.id, text=response) ) )

# Credit: https://github.com/CaKEandLies/Telegram_Cthulhu/blob/master/cthulhu_game_bot.py#L63
def feedback_handler(bot, update, args=None):
    """
    Store feedback from users in a text file.
    """
    if args and len(args) > 0:
        feedback = open("data/feedback.txt", "a")
        feedback.write("\n")
        feedback.write(update.message.from_user.first_name)
        feedback.write("\n")
        # Records User ID so that if feature is implemented, can message them
        # about it.
        feedback.write(str(update.message.from_user.id))
        feedback.write("\n")
        feedback.write(" ".join(args))
        feedback.write("\n")
        feedback.close()
        bot.send_message(chat_id=update.message.chat_id,
                         text="Thanks for the feedback!")
    else:
        bot.send_message(chat_id=update.message.chat_id,
                         text="Format: /feedback [feedback]")

def handle_error(bot, update, error):
    try:
        raise error
    except TelegramError:
        logging.getLogger(__name__).warning('TelegramError! %s caused by this update:\n%s', error, update)

class Player:
    def __init__(self, id, nickname):
        self.id = id
        self.name = name

    def set_nickname(self, name):
        self.name = name

    def get_markdown_tag(self):
        return "[{}](tg://user?id={})".format(self.name, self.id)

NUM_PER_SUIT = 4
class GameState:
    def __init__(self, num_players):
        # TODO will need to change if we want to support arbitrary joins in first round
        self.num_players = num_players
        self.player_minimums = [ [ 0 for _ in range(num_players) ] for _ in range(num_players) ]
        self.player_maximums = [ [ num_players for _ in range(num_players) ] for _ in range(num_players) ]
        self.hand_sizes = [ NUM_PER_SUIT for _ in range(num_players) ]

    # TODO track the message that lets us know each thing so we can send "proof" of why a move is invalid
    def has_at_least(self, player, suit, n):
        self.player_minimums[player][suit] = max(self.player_minimums[player][suit], n)

    def has_at_most(self, player, suit, n):
        self.player_maximums[player][suit] = min(self.player_maximums[player][suit], n)

    def has_exactly(self, player, suit, n):
        self.player_maximums[player][suit] = 0
        self.player_minimums[player][suit] = 0

    def has_hand_size(self, player, n):
        self.hand_sizes[player] = n

    def can_have(self, player, suit, n):
        return n >= self.player_minimums[player][suit] and \
            n <= self.player_maximums[player][suit]

    def deduce_extrema(self):
        # there are exactly NUM_PER_SUIT cards in every suit
        for suit in range(self.num_players):
            for player in range(self.num_players):
                in_other_hands = 0
                maybe_in_other_hands = 0
                for other_player in range(self.num_players):
                    if player == other_player:
                        continue
                    in_other_hands += self.player_minimums[other_player][suit]
                    maybe_in_other_hands += self.player_maximums[other_player][suit]
                self.has_at_most(player, suit, NUM_PER_SUIT - in_other_hands)
                self.has_at_least(player, suit, NUM_PER_SUIT - maybe_in_other_hands)

        # each player has the number of cards that they have
        for player in range(self.num_players):
            for suit in range(self.num_players):
                num_known_cards = 0
                num_possible_cards = 0
                for other_suit in range(self.num_players):
                    if suit == other_suit:
                        continue
                    num_known_cards += self.player_minimums[player][other_suit]
                    num_possible_cards += self.player_maximums[player][other_suit]
                self.has_at_most(player, suit, self.hand_sizes[player] - num_known_cards)
                self.has_at_least(player, suit, self.hand_sizes[player] - num_possible_cards)

    def is_converged(self):
        return self.player_maximums == self.player_minimums

    def asked_for(self, player, suit):
        if not self.can_have(player, suit, 1):
            return False

        self.has_at_least(player, suit, 1)

        return True

    def gave_away(self, player, suit, n):
        if not self.can_have(player, suit, n):
            return False

        self.has_hand_size(player, self.hand_sizes[player] - n)
        self.has_exactly(player, suit, 0)

        return True

    def received(self, player, suit, n):
        self.has_hand_size(player, self.hand_sizes[player] + n)
        self.player_minimums[player][suit] += n
        self.player_maximums[player][suit] += n
        self.has_at_most(player, suit, NUM_PER_SUIT)

        return True

    def test_action(self, source, target, suit, n):
        print( self.asked_for(source, suit) and \
            self.gave_away(target, suit, n) and \
            self.received(source, suit, n) )
        print()

    def __str__(self):
        return "Hand sizes[players]:  " + str(self.hand_sizes) + "\n" + \
               "Mins[players][suits]: " + str(state.player_minimums) + "\n" + \
               "Maxs[players][suits]: " + str(state.player_maximums)

class Game:
    def __init__(self):
        self.players = []
        self.suit_names = []
        self.started = False

    def player_join(self, player):
        if self.started:
            return "cannot join a game that has already started"
        else:
            self.players.append(player)

    def player_leave(self, player):
        if self.started:
            return "cannot join a game that has already started"
        elif player not in self.players:
            return "it's not like you were playing..."
        else:
            self.players.remove(player)

    def game_start(self):
        self.state = GameState(len(self.players))

def i_am_handler(bot, update, user_data=None, args=[]):
    pass

def list_player_handler(bot, update, chat_data=None):
    pass

def whois_handler(bot, update, chat_data=None):
    pass

def join_handler(bot, update, user_data=None, chat_data=None):
    pass

def leave_handler(bot, update, user_data=None, chat_data=None):
    pass

def start_game_handler(bot, update, user_data=None, chat_data=None):
    pass


def ask_handler(bot, update, user_data=None, chat_data=None, args=None):
    pass

def have_handler(bot, update, user_data=None, chat_data=None, args=None):
    pass

def go_fish_handler(bot, update, user_data=None, chat_data=None):
    have_handler(bot, update, user_data=user_data, chat_data=chat_data,
        args=["0"])

if __name__ == "__main__":
    updater = Updater(token=API_TOKEN)
    dispatcher = updater.dispatcher

    dispatcher.add_handler(get_static_handler("help"))
    dispatcher.add_handler(CommandHandler('feedback', feedback_handler, pass_args=True))

    # TODO these 2 commands shouldn't be necessary: you should be able to just start a game, then whoever asks first
    # is in it, as well as whoever they ask. but GameState currently does not support this
    dispatcher.add_handler(CommandHandler('joingame', join_handler, pass_user_data=True, pass_chat_data=True))
    dispatcher.add_handler(CommandHandler('leavegame', leave_handler, pass_user_data=True, pass_chat_data=True))

    dispatcher.add_handler(CommandHandler('startgame', start_game_handler, pass_user_data=True, pass_chat_data=True))

    dispatcher.add_handler(CommandHandler('listplayers', list_player_handler, pass_chat_data=True))
    dispatcher.add_handler(CommandHandler('whois', whois_handler, pass_chat_data=True))
    dispatcher.add_handler(CommandHandler('iam', i_am_handler, pass_user_data=True))

    dispatcher.add_handler(CommandHandler('ask', ask_handler, pass_args=True, pass_user_data=True, pass_chat_data=True))
    dispatcher.add_handler(CommandHandler('ihave', have_handler, pass_args=True, pass_user_data=True, pass_chat_data=True))
    dispatcher.add_handler(CommandHandler('gofish', go_fish_handler, pass_user_data=True, pass_chat_data=True))

    dispatcher.add_error_handler(handle_error)

    logging.basicConfig(
        filename="ignore/bot.log",
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.INFO)

    updater.start_polling()
    updater.idle()
