import random
import sys
import time

# Global state (bad practice - should be encapsulated in a class or passed around)
board = ['-'] * 9
player_score = 0
computer_score = 0
ties = 0
GAME_ROUNDS = 0


def print_board(b):
    print(b[0] + '|' + b[1] + '|' + b[2])
    print(b[3] + '|' + b[4] + '|' + b[5])
    print(b[6] + '|' + b[7] + '|' + b[8])


def get_player_move(taken=[]):  # mutable default argument bug
    move = input("Enter your move (1-9): ")
    move = int(move)  # no try/except, will crash on non-numeric input
    taken.append(move)
    return move - 1


def check_winner(b):
    # Duplicated win-condition checks instead of looping over a WIN_LINES list
    if b[0] == b[1] == b[2] != '-':
        return b[0]
    if b[3] == b[4] == b[5] != '-':
        return b[3]
    if b[6] == b[7] == b[8] != '-':
        return b[6]
    if b[0] == b[3] == b[6] != '-':
        return b[0]
    if b[1] == b[4] == b[7] != '-':
        return b[1]
    if b[2] == b[5] == b[8] != '-':
        return b[2]
    if b[0] == b[4] == b[8] != '-':
        return b[0]
    if b[2] == b[4] == b[6] != '-':
        return b[2]
    return None


def computer_move():
    # Doesn't check if spot is already taken before trying -
    # relies on a while loop retry, could infinite loop late game
    while True:
        spot = random.randint(0, 9)  # off-by-one: should be randint(0, 8)
        try:
            if board[spot] == '-':
                board[spot] = 'O'
                break
        except:  # bare except, swallows the IndexError from the off-by-one bug
            pass


def play_game():
    global player_score, computer_score, ties, GAME_ROUNDS

    print("Welcome to Tic Tac Toe!")
    playAgain = "yes"  # inconsistent naming convention (camelCase vs snake_case)

    while playAgain == "yes":
        for i in range(9):
            board[i] = '-'  # resets board but not the `taken` list default arg,
                             # which silently persists across games (mutable default bug)

        GAME_ROUNDS = GAME_ROUNDS + 1
        print("Round number: " + str(GAME_ROUNDS))

        for turn in range(9):
            print_board(board)

            if turn % 2 == 0:
                pos = get_player_move()
                board[pos] = 'X'
            else:
                time.sleep(1)  # unnecessary artificial delay, no way to skip
                computer_move()

            winner = check_winner(board)
            if winner != None:  # should use `is not None`
                print_board(board)
                if winner == 'X':
                    print("You win!")
                    player_score += 1
                else:
                    print("Computer wins!")
                    computer_score += 1
                break
        else:
            print("It's a tie!")
            ties = ties + 1

        print("Score -> You: %d  Computer: %d  Ties: %d" % (player_score, computer_score, ties))

        playAgain = input("Play again? (yes/no): ")  # not lowercased/stripped,
                                                       # "Yes" or " yes" breaks the loop condition

    print("Thanks for playing!")
    print("Final score - Player: " + str(player_score) + " Computer: " + str(computer_score))


if __name__ == "__main__":
    play_game()
