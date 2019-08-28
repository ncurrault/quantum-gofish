NUM_PER_SUIT = 4
class GameState:
    """
    Class for tracking the state of a game. That is, given n players
    (referred to by indices 0 to n-1) and n suits (also 0 to n-1), learn data
    about what players may or may not have.
    """

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
        """
        Check if 'player' can have 'n' cards of suit 'suit'
        """
        return n >= self.player_minimums[player][suit] and \
            n <= self.player_maximums[player][suit]

    def deduce_extrema(self):
        """
        From all current extrema, deduce stricter extrema from the principles
        of the game: there are NUM_PER_SUIT cards of each suit and each players
        hand consists of cards from the suits.
        """
        previous = None
        current = self.player_minimums + self.player_maximums
        while previous != current:
            previous = current
            self._deduce_extrema_step()
            current = self.player_minimums + self.player_maximums

    def _deduce_extrema_step(self):
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
        """
        Note that some player 'player' has asked another for the suit 'suit'.
        If this is impossible (it is known that 'player' has no 'suit's), returns
        False and does nothing.

        If it is possible, returns True and internally notes that the player
        has at least 1 card of suit 'suit'.
        """
        print(self)
        print("asked for", player, suit)
        print()

        if not self.can_have(player, suit, 1):
            return False

        self.has_at_least(player, suit, 1)

        return True

    def gave_away(self, player, suit, n):
        """
        Note that some player 'player' has given away exacly 'n' cards with suit
        'suit'.

        If this is impossible (it is known that 'player' has more or less than n
        'suit's), returns False and does nothing.

        If it is possible, returns True and internally notes that the player
        has given away 'n' 'suit's
        """
        print(self)
        print("gave away", player, suit, n)
        print()

        if not self.can_have(player, suit, n):
            return False

        self.has_hand_size(player, self.hand_sizes[player] - n)
        self.has_exactly(player, suit, 0)

        return True

    def received(self, player, suit, n):
        """
        Notes that 'player' has received 'n' cards of suit 'suit'. This action
        cannot fail. Returns True.
        """
        print(self)
        print("received", player, suit, n)
        print()

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
               "Mins[players][suits]: " + str(self.player_minimums) + "\n" + \
               "Maxs[players][suits]: " + str(self.player_maximums)

if __name__ == "__main__":
    state = GameState(3)
    # state.test_action(0, 1, 0, 1)
    # state.deduce_extrema()
    # state.test_action(1, 2, 1, 3)
    # state.deduce_extrema()
    #
    # print(state.asked_for(2, 1))

    print(state.asked_for(0, 0))
    print(state.gave_away(1, 0, 0))
    print(state)
