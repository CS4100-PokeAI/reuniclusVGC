# -*- coding: utf-8 -*-
import asyncio
import sys
import random

sys.path.append(".") # will make "bots" callable from root
sys.path.append("..") # will make "bots" callable from simulators

from poke_env.player.random_player import RandomPlayer
from poke_env.player.utils import cross_evaluate
from tabulate import tabulate
from bots.random_doubles_player import RandomDoublesPlayer
from bots.smarter_random_player import SmarterRandomPlayer
from helpers.team_repo import TeamRepository

# TODO: examine why we get this error:
# 2020-11-29 01:59:42,142 - SmarterRandomPlayer 1 - WARNING - Error message received: |error|[Invalid choice] Can't move: Your Zapdos doesn't have a move matching nastyplot
# Go to SmarterRandomPlayer
# Print out what's happening with specifically Zapdos
async def main():
    print("\033[92m Starting script... \033[0m")


    # We create players:
    players = [
      # RandomDoublesPlayer(max_concurrent_battles=10, battle_format='gen8vgc2021', team=TeamRepository.teams[0]),
      # SmarterRandomPlayer(max_concurrent_battles=1, battle_format='gen8vgc2021', team=TeamRepository.teams['nochoice']),
      # SmarterRandomPlayer(max_concurrent_battles=1, battle_format='gen8vgc2021', team=TeamRepository.teams['doubleturn']),
      SmarterRandomPlayer(max_concurrent_battles=10, battle_format='gen8vgc2021', team=TeamRepository.teams['regirock']),
      RandomDoublesPlayer(max_concurrent_battles=10, battle_format='gen8vgc2021', team=TeamRepository.teams['switch']),
      SmarterRandomPlayer(max_concurrent_battles=10, battle_format='gen8vgc2021', team=TeamRepository.teams['garchomp']),
      SmarterRandomPlayer(max_concurrent_battles=10, battle_format='gen8vgc2021', team=TeamRepository.teams['swampert']),
    ]

    # Now, we can cross evaluate them: every player will player 30 games against every
    # other player.
    cross_evaluation = await cross_evaluate(players, n_challenges=100)

    # Defines a header for displaying results
    table = [["-"] + [p.username for p in players]]

    # Adds one line per player with corresponding results
    for p_1, results in cross_evaluation.items():
        table.append([p_1] + [cross_evaluation[p_1][p_2] for p_2 in results])

    # Displays results in a nicely formatted table.
    print(tabulate(table))


if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(main())
