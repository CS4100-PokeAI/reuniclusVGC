# reuniclusVGC
A bot to play VGC. Here are my initial notes from reading

### Rules of Pokemon that make it hard:
1. You and opponent make turns simultaneously
    1. Your opponents moves affect the effects of your moves (e.g. if you’re KO’ed)
2. Large aspect of luck / randomness:
    1. Damage Rolls
    2. Move success (accuracy, multiple protects, OHKOs)
    3. Secondary Move effects
    4. Luck-based abilities (Super Luck, Effect Spore)
    5. Critical Hits
3. Moves made now can affect outlook through next couple of turns (e.g. tailwind, reflect, protect)
4. Imperfect knowledge
    1. Abilities
    2. Items
    3. Moves
    4. EV spreads
    5. IV spreads
    6. Pokemon brought

### ML basics:
- We need to learn a “policy”. Given the game state, and thus a set of possible actions, ML will choose the most optimal action
- Because of terms like “reverse sweeping” (e.g. going down 4 to 1 so that you can win with your last mon), it’s hard to have heuristics of whether a game was totally or just lost — the best way to approach this would be to reward the ML with +1 with a win and a -1 with a loss. We can add more heuristics to speed up training though
- Input:
    - State: Knowledge of pokemon/mechanics/team
    - Possible Actions [singles: 1-4, doubles: 1-4,1-4), switches (singles: 1-5, doubles: 1-2)]
- Output:
    - Best action
        - There is no such thing as a “best action” because a perfectly predictable strategy is exploitable. An understanding of how good each action is ideal

### Shortcuts to simplify modeling:
- We should create three types of opponents:
    - Random
    - One turn lookahead
        - Maximize damage
        - Maximize difference in HP
    - Maximize damage
    - Maximize difference in HP
- Assume you already know the other team (eliminates partial observation complexity)
    - This eliminates event space and computation.
    - In the future, we can create a model to predict spreads/moves/4 pokemon brought of the team. In essence, the P(environment = e | opponent’s actions & what we’ve observed), where e is our guess of their spreads/moves
        - Optimally, we would then incorporate this uncertainty into our choices, and further, we would account for how inoptimal we can get a player to act by withholding information
    - In doubles use-case, assume we already know the 4 being brought. Same assumptions apply as singles, with another layer of “who will be the 4 that the opponent brings”
- Progression:
    - Start with 1:1s with same Pokemon
    - Start with 2:2 doubles with same Pokemon
    - 4:4 doubles with same Pokemon
    - Randomize viable pokemon
    - Randomize viable pokemon + viable moves
- Start with doubles, as it is probably computationally less expensive
    - Turn-based event space: (ignoring dynamax, which adds 4 more actions per turn for singles, 8 for doubles)
        - Singles:  4 moves + 5 switches maximum = 9 possible
        - Doubles:
            - Pokemon 1: 4 moves for 3 targets + 2 switches: 14
            - Pokemon 2: 4 moves for 3 targets + 2 switches: 14
            - Estimated maximum total possible moves per turn: 196 possible
    - Estimated Turns per game
        - Singles: 50
        - Doubles: 15
    - Estimated Moves to evaluate:
        - Singles: 9^50 = 5.153775207e47
        - Doubles: 196^15 = 2.420143236e34
    - Ignore secondary effects/moves if they are <80% likely
    - Assume anything that is more than 30% likely to happen is going to happen
- We could possibly assume that players will make turns sequentially (and take top responses to sequential turns) to quickly find likely states?
- Let's ignore situations in which we are forced to make a decision mid-turn (e.g. volt switch, whirlwind)

### Ways Players Think
- Pokemon is a game of wincons
    - Goal is to eliminate all other pokemon that are threats to your wincon and outspeed/KO the rest
    - The ability to set yourself up and “look ahead” will be key
- Trainers think about HP not in the number, but in a way that matters: “survive two hits from kartana”
- Players dont bank on unlikely secondary effects unless absolutely necessary
- If we can eliminate pokemon each turn regardless of what the other player does, we win
- They work backwards:
    - In what situations will I win and how can I set up those situations?
        - Is it possible to identify 2+ x2 (where the opponent only has 2 mons left) situations in which we win and work backwards from there? As in, what HP/conditions will I need to beat the last two mons?
    - In what situations will I lose and how can I avoid those situations?
        - Is it possible to look at the situations in which I only have 2 mons left and I lose?
- In winning positions, they start making decisions according to probabilities: how can you minimize P(loss)?


### ML types:
- Reinforcement Learning because:
    - You dont know the probability of getting to the next state (due to opponent decision)
    - You don’t immediately know which states lead you to the reward (+1)
- Monte Carlo Tree Searching?
    - This would only really be applicable in Singles
    - This would be really expensive; you could create heuristics to think 2-3 turns ahead
        - e.g. not attacking your own pokemon unless healing or weakness policy
- “Backwards Induction” (implemented as Alpha-Beta pruning) can help prune gamestates
- Zero sum games can always be reformulated to Linear Problems (Dantzig, 1951)
- Training against itself? (AlphaZero/AlphaGo approach)
- “Portfolio Optimization” would be a team builder algorithm, and is unsolved
- The type of problem this is:
    - Stochastic Game (players make moves simultaneously in decision-making scenarios; the joint actions results in a transition to a different game state)
    - Multi-Agent (two player)
    - Zero Sum (aka constant sum)
    - Partially Observable (each player has imperfect information)
- Minimax Q?


### Useful Links:
1. Twitter Discussion: https://twitter.com/TBFUnreality/status/1059894045177200645
2. Simulator Github: https://github.com/smogon/pokemon-showdown
3. Paper on Poker ML using Imperfect Information: http://modelai.gettysburg.edu/2013/cfr/cfr.pdf
4. Someone creating DeepLearning for 1:1 battle: https://towardsdatascience.com/poke-agent-pokemon-battling-reinforcement-learning-27ef10885c5c
5. Create a showdown bot to operate easily: https://github.com/dramamine/leftovers-again
    1. ^ It will make a request and pass a gamestate, which we will return with a move
    2. Working Pokemon AI: https://github.com/vasumv/pokemon_ai/ (windows only)
6. Minimax AI: http://doublewise.net/pokemon/ (named Technical Machine)
    1. Code: https://bitbucket.org/davidstone/technical-machine/src/master/
7. Someone doing simple deep learning: https://web.stanford.edu/class/aa228/reports/2018/final151.pdf
8. Schoolwork: https://docplayer.net/63514819-Artificial-intelligence-for-pokemon-showdown.html
9. Schoolwork: https://nyuscholars.nyu.edu/en/publications/showdown-ai-competition
10. http://julian.togelius.com/Lee2017Showdown.pdf
    1. Includes primers on how to model AI using showdown API
    2. Also a bunch of fairly simple starter algorithms and their performance
11. https://papers.nips.cc/paper/2012/file/3df1d4b96d8976ff5986393e8767f5b2-Paper.pdf
    1. https://github.com/samhippie/shallow-red
12. Lit review on MARL: https://arxiv.org/pdf/2011.00583.pdf
13. Create DeepLearning stuff using poke-env: https://poke-env.readthedocs.io/en/stable/getting_started.html
    1. **This is what I go with**
14. Implemented Bot: https://github.com/pmariglia/showdown

### How I got this up and running
1. Install Git
2. create your directory/cd into your directory
2. Install Node
  1. curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.37.0/install.sh | bash # I had to create a .bash_profile first
  2. export NVM_DIR="$HOME/.nvm"
  3. [ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"
  4. [ -s "$NVM_DIR/bash_completion" ] && \. "$NVM_DIR/bash_completion"
  5. command -v nvm # to ensure it is running
  6. nvm install node -g
3. python3.8 -m pip install poke-env
4. git clone https://github.com/hsahovic/Pokemon-Showdown.git
5. python3.8 -m pip install pip keras-rl2

To run an eample where we simulate random battles, from home directory:
`node Pokemon-Showdown/pokemon-showdown`
then `python3.8 examples/random_player_random_battle.py`

Example bots: https://github.com/hsahovic/poke-env/tree/master/examples
