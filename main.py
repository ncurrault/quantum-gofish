import telegram
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, \
    InlineQueryHandler
from telegram.error import TelegramError

import random
import logging
import datetime
from enum import Enum

from game_state import GameState

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
def feedback_handler(bot, update, args):
    """
    Store feedback from users in a text file.
    """
    if args and len(args) > 0:
        feedback = open("ignore/feedback.txt", "a")
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
    """
    Helper class for representing a Telegram user,
    allowing them to set a nickname, and tag them in a Markdown-encoded message.
    """
    def __init__(self, id, nickname):
        self.id = id
        self.name = nickname

    def set_nickname(self, name):
        self.name = name

    def get_markdown_tag(self):
        return "[{}](tg://user?id={})".format(self.name, self.id)

class GameStatus(Enum):
    GAME_NOT_STARTED = 0
    AWAITING_ASK = 1
    AWAITING_RESPONSE = 2
    GAME_OVER = 3

class Game:
    """
    Represents a game of Quantum Go Fish. Maintains a GameState representing the
    current state of the game, and a list of players and suit names with indices
    corresponding to the GameState.
    """
    def __init__(self):
        self.players = []
        self.suit_names = []
        self.started = False
        self.status = GameStatus.GAME_NOT_STARTED

        self.asking_player_idx = None
        self.requested_suit_idx = None
        self.target_player = None
        self.target_player_idx = None

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
        self.num_players = len(self.players)
        self.state = GameState(self.num_players)
        self.started = True

        random.shuffle(self.players)
        self.status = GameStatus.AWAITING_ASK
        self.asking_player_idx = 0
        self.asking_player = self.players[0]

    def get_player(self, nickname_or_idx):
        """
        Get a Player object of a player in this game given 'nickname_or_idx', a
        string that another user might use to refer to them
        (their index in the turn order or their nickname).

        Returns None if no player with that index/nickname exists.
        """
        if nickname_or_idx.isdigit() and int(nickname_or_idx) < len(self.players):
            return self.players[int(nickname_or_idx)]
        for player in self.players:
            if player.name == nickname_or_idx:
                return player

    def get_player_md_tag(self, nickname_or_idx):
        """
        Wrapper for get_player that returns either the Markdown tag of the
        player referred to by 'nickname_or_idx' or None if the player could not
        be identified.
        """

        res = self.get_player(nickname_or_idx)
        if res:
            return res.get_markdown_tag()
        else:
            return None

    def ask_for(self, player, target_str, suit):
        if self.status != GameStatus.AWAITING_ASK:
            return "/ask unexpected"

        player_idx = self.players.index(player)
        target = self.get_player(target_str)
        if target:
            target_idx = self.players.index(target)
        else:
            return "cannot parse target user: " + target_str

        if suit in self.suit_names:
            suit_idx = self.suit_names.index(suit)
        else:
            print(suit)
            if len(self.suit_names) == self.num_players:
                return "could not parse suit name: " + suit
            suit_idx = len(self.suit_names)
            self.suit_names.append(suit)

        if not self.state.asked_for(player_idx, suit_idx):
            return "error: game state indicates that {} has at least one \"{}\" with probability zero".format(player.name, suit)

        self.state.deduce_extrema()
        if self.state.is_converged():
            self.winner = player
            self.status = GameStatus.GAME_OVER
        else:
            self.status = GameStatus.AWAITING_RESPONSE
            self.requested_suit = suit
            self.requested_suit_idx = suit_idx
            self.target_player = target
            self.target_player_idx = target_idx

    def respond_to_request(self, player, n_str):
        if self.status != GameStatus.AWAITING_RESPONSE:
            return "/ihave unexpected"

        if n_str.isdigit():
            n = int(n_str)
        else:
            return "cannot parse number of cards: " + n_str

        if player == self.target_player:
            player_idx = self.players.index(player)
        else:
            return "expected \"/ihave [n]\" from {}, not {}".format(self.target_player.name, player.name)

        if self.state.gave_away(player_idx, self.requested_suit_idx, n):
            self.state.received(self.asking_player_idx, self.requested_suit_idx, n)
        else:
            return "error: game state indicates that {} has {} \"{}\" with probability zero".format(player.name, n, self.requested_suit)

        self.state.deduce_extrema()
        if self.state.is_converged():
            self.winner = player
            self.status = GameStatus.GAME_OVER
        else:
            self.status = GameStatus.AWAITING_ASK
            while True:
                self.asking_player_idx = (self.asking_player_idx + 1) % self.num_players
                self.asking_player = self.players[self.asking_player_idx]

                if self.state.hand_sizes[self.asking_player_idx] > 0:
                    break # find the next player with a nonempty hand

    def player_list(self):
        res = "List of players:\n"
        for i, player in enumerate(self.players):
            res += str(i) + ". "
            res += player.name + " "

            if self.status != GameStatus.GAME_NOT_STARTED:
                res += "({} cards)".format(self.state.hand_sizes[i])

            if i == self.asking_player_idx:
                res += " (Q)"
            elif i == self.target_player_idx and self.status == GameStatus.AWAITING_RESPONSE:
                res += " (A)"

            res += "\n"

        return res

    def send_blame(self, bot, chat_id):
        if self.status == GameStatus.AWAITING_ASK:
            msg = "It's {}'s turn!".format(self.asking_player.get_markdown_tag())
        elif self.status == GameStatus.AWAITING_RESPONSE:
            msg = '{}: "{}, do you have any {}?"'.format(
                self.asking_player.name,
                self.target_player.get_markdown_tag(),
                self.requested_suit)
        elif self.status == GameStatus.GAME_NOT_STARTED:
            msg = "Waiting on anyone to start the game"
        else:
            msg = "Game is over. Congratulations, {}!".format(self.winner.name)
            # TODO show what the converged state was

        bot.send_message(chat_id=chat_id, text=msg, parse_mode=telegram.ParseMode.MARKDOWN)

def newgame_handler(bot, update, chat_data):
    chat_data["game_obj"] = Game()
    update.message.reply_text("Started new Quantum Go Fish game! /joingame to join")

# Telegram handlers for inquiries about players/nicknames

def i_am_handler(bot, update, user_data, args):
    if args:
        nickname = args[0]
        if "player_obj" in user_data:
            user_data["player_obj"].set_nickname(nickname)
        else:
            user_data["player_obj"] = Player(update.message.from_user.id, nickname)

        update.message.reply_text("Successfully changed nickname to: " + nickname)
    else:
        update.message.reply_text("Nickname required")

def list_player_handler(bot, update, chat_data):
    if "game_obj" in chat_data:
        update.message.reply_text(chat_data["game_obj"].player_list())
    else:
        update.message.reply_text("No game exists in this chat")

def whois_handler(bot, update, args, chat_data):
    if "game_obj" not in chat_data:
        update.message.reply_text("No game exists in this chat")
    elif not args:
        update.message.reply_text("usage: /whois [nickname or index]")
    else:
        nickname = " ".join(args)
        res = chat_data["game_obj"].get_player_md_tag(nickname)
        if res:
            update.message.reply_text(res, parse_mode=telegram.ParseMode.MARKDOWN)
        else:
            update.message.reply_text("No player with nickname '{}'".format(nickname))

# Telegram handlers for game management actions (joining/leaving the lobby, starting)
# TODO shouldn't need... (see comment below)
def join_handler(bot, update, user_data, chat_data):
    if "game_obj" in chat_data:
        if "player_obj" not in user_data:
            user_data["player_obj"] = Player(update.message.from_user.id, update.message.from_user.first_name)

        player = user_data["player_obj"]
        game = chat_data["game_obj"]
        msg = game.player_join(player)
        if msg:
            update.message.reply_text(msg)
        else:
            update.message.reply_text("Welcome, {}! Current player count is {}.".format(player.name, len(game.players)))
    else:
        update.message.reply_text("No game exists in this chat")

def leave_handler(bot, update, user_data, chat_data):
    if "game_obj" in chat_data:
        if "player_obj" not in user_data:
            user_data["player_obj"] = Player(update.message.from_user.id, update.message.from_user.first_name)

        player = user_data["player_obj"]
        game = chat_data["game_obj"]
        msg = game.player_leave(player)
        if msg:
            update.message.reply_text(msg)
        else:
            update.message.reply_text("{} has left. Current player count is {}.".format(player.name, len(game.players)))
    else:
        update.message.reply_text("No game exists in this chat")

def start_game_handler(bot, update, chat_data):
    if "game_obj" in chat_data:
        chat_data["game_obj"].game_start()
        chat_data["game_obj"].send_blame(bot, update.message.chat_id)
    else:
        update.message.reply_text("No game exists in this chat")

# Telegram handlers for in-game actions: asking another user for something,
# responding with how many you have, or /go fish (equivalent to "/ihave 0")

def ask_handler(bot, update, user_data, chat_data, args):
    if len(args) < 2:
        update.message.reply_text("syntax: /ask [user] [suit name]")
    elif "game_obj" not in chat_data:
        update.message.reply_text("No game exists in this chat")
    elif "player_obj" not in user_data or user_data["player_obj"] not in chat_data["game_obj"].players:
        update.message.reply_text("It doesn't look like you're in this game")
    else:
        response = chat_data["game_obj"].ask_for(user_data["player_obj"], args[0], " ".join(args[1:]))

        if response:
            update.message.reply_text(response)
        else:
            chat_data["game_obj"].send_blame(bot, update.message.chat_id)


def have_handler(bot, update, user_data, chat_data, args):
    if len(args) != 1:
        update.message.reply_text("syntax: /ihave [number]")
    elif "game_obj" not in chat_data:
        update.message.reply_text("No game exists in this chat")
    elif "player_obj" not in user_data or user_data["player_obj"] not in chat_data["game_obj"].players:
        update.message.reply_text("It doesn't look like you're in this game")
    else:
        response = chat_data["game_obj"].respond_to_request(user_data["player_obj"], args[0])
        if response:
            update.message.reply_text(response)
        else:
            chat_data["game_obj"].send_blame(bot, update.message.chat_id)

def go_fish_handler(bot, update, user_data, chat_data):
    have_handler(bot, update, user_data=user_data, chat_data=chat_data,
        args=["0"])

def blame_handler(bot, update, chat_data):
    if "game_obj" in chat_data:
        chat_data["game_obj"].send_blame(bot, update.message.chat_id)
    else:
        update.message.reply_text("No game exists in this chat")

if __name__ == "__main__":
    updater = Updater(token=API_TOKEN)
    dispatcher = updater.dispatcher

    dispatcher.add_handler(get_static_handler("help"))
    dispatcher.add_handler(CommandHandler('feedback', feedback_handler, pass_args=True))

    dispatcher.add_handler(CommandHandler('newgame', newgame_handler, pass_chat_data=True))
    dispatcher.add_handler(CommandHandler('listplayers', list_player_handler, pass_chat_data=True))
    dispatcher.add_handler(CommandHandler('whois', whois_handler, pass_args=True, pass_chat_data=True))
    dispatcher.add_handler(CommandHandler('iam', i_am_handler, pass_args=True, pass_user_data=True))

    # TODO these 2 commands shouldn't be necessary: you should be able to just start a game, then whoever asks first
    # is in it, as well as whoever they ask. but GameState currently does not support this
    dispatcher.add_handler(CommandHandler('joingame', join_handler, pass_user_data=True, pass_chat_data=True))
    dispatcher.add_handler(CommandHandler('leavegame', leave_handler, pass_user_data=True, pass_chat_data=True))
    dispatcher.add_handler(CommandHandler('startgame', start_game_handler, pass_chat_data=True))

    dispatcher.add_handler(CommandHandler('ask', ask_handler, pass_args=True, pass_user_data=True, pass_chat_data=True))
    dispatcher.add_handler(CommandHandler('ihave', have_handler, pass_args=True, pass_user_data=True, pass_chat_data=True))
    dispatcher.add_handler(CommandHandler('gofish', go_fish_handler, pass_user_data=True, pass_chat_data=True))

    dispatcher.add_handler(CommandHandler('blame', blame_handler, pass_chat_data=True))

    dispatcher.add_error_handler(handle_error)

    logging.basicConfig(
        filename="ignore/bot.log",
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.INFO)

    updater.start_polling()
    updater.idle()
