import numpy as np
import tensorflow as tf
from datetime import datetime
import sys
import random
from typing import Dict, List, Optional, Tuple

from poke_env import utils
from poke_env.environment.double_battle import DoubleBattle
from poke_env.player.env_player import EnvPlayer

from poke_env.environment.field import Field
from poke_env.environment.side_condition import SideCondition
from poke_env.environment.status import Status
from poke_env.environment.weather import Weather
from poke_env.environment.pokemon_type import PokemonType
from poke_env.environment.move_category import MoveCategory
from poke_env.environment.target_type import TargetType
from poke_env.environment.volatile_status import VolatileStatus
from poke_env.environment.battle import Battle
from reuniclusVGC.bots.random_doubles_player import RandomDoublesPlayer

from poke_env.player.battle_order import DoubleBattleOrder, DefaultBattleOrder, BattleOrder, DefaultDoubleBattleOrder

from reuniclusVGC.helpers.doubles_utils import *

from rl.agents.dqn import DQNAgent
from rl.policy import LinearAnnealedPolicy, MaxBoltzmannQPolicy, Policy
from tensorflow.python.keras.engine import training
from rl.memory import SequentialMemory, Memory

from tensorflow.keras.layers import Dense, Flatten, Activation, BatchNormalization, Input
from tensorflow.keras.models import Sequential
from tensorflow.keras.optimizers import Adam


# We define our RL player
class SimpleDQNPlayer(EnvPlayer):

    _EMBEDDING_SPACE = None

    def __init__(self, num_battles=10000, **kwargs):
        super().__init__(**kwargs)

        # Redefine the buffer defined in env_player; this will be turn (int) => reward and will be reset every battle
        # So that we can compute te difference between this reward and the last state
        self.num_battles = num_battles
        self._reward_buffer = {}

        # Ensure stability and reproducibility
        tf.random.set_seed(21)
        np.random.seed(21)

        # (4 moves * (3 possible targets) * dynamax + 2 switches)
        # * (4 moves * (3 possible targets) * dynamax + 2 switches) = 676
        # This is not entirely true since you can't choose the same mon to switch to both times, or you cant dynamax
        # two mons at the same time but it's easier to do it this way
        action_space = list(range((4 * 3 * 2 + 2) * (4 * 3 * 2 + 2)))
        self._ACTION_SPACE = action_space

        self._EMBEDDING_SPACE = 7913

        # Preprocess all the sets that we'll use to embed battle states.
        # The tuples are key where we retrieve the classes, the class, and whether poke_env supports returning the
        # class (as opposed to string)
        self._knowledge = {}
        sets = [
            ('Field', Field, False),
            ('SideCondition', SideCondition, False),
            ('Status', Status, True),
            ('Weather', Weather, True),
            ('PokemonType', PokemonType, True),
            ('MoveCategory', MoveCategory, True),
            ('TargetType', TargetType, False),
            ('VolatileStatus', VolatileStatus, False),
        ]

        for key, klass, supported in sets:
            if supported:
                self._knowledge[key] = list(klass._member_map_.values())
            else:
                self._knowledge[key] = list(map(lambda x: x.name.lower().replace("_", ""),
                                                list(klass._member_map_.values())))

        # print(self._knowledge)

        self._model = None
        self._create_model()

    def _create_model(self):
        # Simple model where only one layer feeds into the next
        self._model = Sequential()

        # Get initializer for hidden layers
        init = tf.keras.initializers.RandomNormal(mean=.1, stddev=.02)

        # Input Layer; this shape is one that just works
        self._model.add(Dense(512, input_shape=(1, 7814), activation="relu",
                              use_bias=False, kernel_initializer=init, name='first_hidden'))

        # Hidden Layers
        self._model.add(Flatten(name='flatten'))  # Flattening resolve potential issues that would arise otherwise
        self._model.add(Dense(256, activation="relu", use_bias=False, kernel_initializer=init, name='second_hidden'))

        # Output Layer
        self._model.add(Dense(len(self._ACTION_SPACE), use_bias=False, kernel_initializer=init, name='final'))
        self._model.add(
            BatchNormalization())  # Increases speed: https://www.dlology.com/blog/one-simple-trick-to-train-keras-model-faster-with-batch-normalization/
        self._model.add(Activation(
            "linear"))  # Same as passing activation in Dense Layer, but allows us to access last layer: https://stackoverflow.com/questions/40866124/difference-between-dense-and-activation-layer-in-keras

        # This is how many battles we'll remember before we start forgetting old ones
        self._memory = SequentialMemory(limit=max(self.num_battles, 10000), window_length=1)

        # Simple epsilon greedy policy
        # This takes the output of our NeuralNet and converts it to a value
        # Softmax is another probabilistic option: https://github.com/keras-rl/keras-rl/blob/master/rl/policy.py#L120
        self._policy = LinearAnnealedPolicy(
            MaxBoltzmannQPolicy(),
            attr="eps",
            value_max=1.0,
            value_min=0.05,
            value_test=0,
            nb_steps=self.num_battles,
        )

        # Defining our DQN
        self._dqn = DQNAgent(
            model=self._model,
            nb_actions=len(self.action_space),
            policy=self._policy,
            memory=self._memory,
            nb_steps_warmup=max(1000, int(self.num_battles / 10)),
            # The number of battles we go through before we start training: https://hub.packtpub.com/build-reinforcement-learning-agent-in-keras-tutorial/
            gamma=0.8,  # This is the discount factor for the Value we learn - we care a lot about future rewards
            target_model_update=.01,
            # This controls how much/when our model updates: https://github.com/keras-rl/keras-rl/issues/55
            delta_clip=1,
            # Helps define Huber loss - cips values to be -1 < x < 1. https://srome.github.io/A-Tour-Of-Gotchas-When-Implementing-Deep-Q-Networks-With-Keras-And-OpenAi-Gym/
            enable_double_dqn=True,
        )

        self._dqn.compile(Adam(lr=0.01), metrics=["mae"])

    def _action_to_single_move(self, action: int, index: int, battle):

        if action < 24:
            # If either there is no mon or we're forced to switch, there's nothing to do
            if not battle.active_pokemon[index] or battle.force_switch[index]: return None
            dynamax, remaining = action % 2 == 1, int(action / 2)
            if battle.active_pokemon[index] and int(remaining / 3) < len(battle.active_pokemon[index].moves):
                move, initial_target = list(battle.active_pokemon[index].moves.values())[
                                           int(remaining / 3)], remaining % 3

                # If there's no target needed, we create the action as we normally would. It doesn't matter what our AI
                # returned as target since there's only one possible target
                if move.deduced_target not in ['adjacentAlly', 'adjacentAllyOrSelf', 'any', 'normal']:
                    return BattleOrder(order=move, actor=battle.active_pokemon[index], dynamax=dynamax)

                # If we are targeting a single mon, there are three cases: your other mon, the opponents mon or their
                # other mon. 2 corresponds to your mon and 0/1 correspond to the opponents mons (index in
                # opponent_active_mon) For the self-taret case, we ensure there's another mon on our side to hit
                # (otherwise we leave action1 as None)
                elif initial_target == 2:
                    if battle.active_pokemon[1] is not None:
                        return BattleOrder(order=move,
                                           move_target=utils.active_pokemon_to_showdown_target(1 - index, opp=False),
                                           actor=battle.active_pokemon[index], dynamax=dynamax)

                # In the last case (if initial_target is 0 or 1), we target the opponent, and we do it regardless of
                # what slot was chosen if there's only 1 mon left. In the following cases, we handle whether there are
                # two mons left or one mon left
                elif len(battle.opponent_active_pokemon) == 2 and all(battle.opponent_active_pokemon):
                    return BattleOrder(order=move,
                                       move_target=utils.active_pokemon_to_showdown_target(initial_target, opp=True),
                                       actor=battle.active_pokemon[index], dynamax=dynamax)
                elif len(battle.opponent_active_pokemon) < 2 and any(battle.opponent_active_pokemon):
                    initial_target = 1 if battle.opponent_active_pokemon[0] is not None else 0
                    return BattleOrder(order=move,
                                       move_target=utils.active_pokemon_to_showdown_target(initial_target, opp=True),
                                       actor=battle.active_pokemon[index], dynamax=dynamax)

        elif 25 - action < len(battle.available_switches[index]):
            return BattleOrder(order=battle.available_switches[index][25 - action], actor=battle.active_pokemon[index])

        return None

    # Takes the output of our policy (which chooses from a 676-dimensional array), and converts it into a battle order
    def _action_to_move(self, action: int, battle: DoubleBattle) -> BattleOrder:  # pyre-ignore
        """Converts actions to move orders. There are 676 actions - and they can be thought of as a 26 x 26 matrix
        (first mon's possibilities and second mon's possibilities). This is not quite true because you cant choose the
        same mon twice to switch to, but we handle that when determining the legality of the move choices later; If the
        proposed action is illegal, a random legal move is performed.
        The conversion is done as follows:

        :param action: The action to convert.
        :type action: int
        :param battle: The battle in which to act.
        :type battle: Battle
        :return: the order to send to the server.
        :rtype: BattleOrder
        """
        row, col = action % 26, int(action / 26)
        first_order = self._action_to_single_move(row, 0, battle) if battle.active_pokemon[0] else None
        second_order = self._action_to_single_move(col, 1, battle) if battle.active_pokemon[1] else None

        double_order = DoubleBattleOrder(first_order=first_order, second_order=second_order)
        if DoubleBattleOrder.is_valid(battle, double_order):
            return double_order
        else:
            return DefaultDoubleBattleOrder()

    @property
    def action_space(self) -> List:
        """
        There are 210 possible moves w/out dynamax:
        First mon's move possibilities:
            4 moves * 3 possible targets (for moves w/ multiple/self-targeting we default to any target) + 3 switches
        Second mon's move possibilities:
            4 moves * 3 possible targets (for moves w/ multiple/self-targeting we default to any target) + 2 switches
        First mon's move possibilities * Second mon's move possibilities = 210
        """
        return self._ACTION_SPACE

    @property
    def embedding_space(self) -> Tuple[int, int]:
        """
        Return the size of the embedding for a gen-8 VGC battle
        """

        return (1, self._EMBEDDING_SPACE)

    @property
    def model(self) -> training.Model:
        """
        Return our Keras-trained model
        """
        return self._model

    @property
    def memory(self) -> Memory:
        """
        Return the memory for our DQN
        """
        return self._memory

    @property
    def policy(self) -> Policy:
        """
        Return our policy for our DQN
        """
        return self._policy

    @property
    def dqn(self) -> DQNAgent:
        """
        Return our DQN object
        """
        return self._dqn

    # Embeds a move in a 178-dimensional array.
    # This includes a move's accuracy, base_power, whether it breaks protect, crit ratio, pp, damage, drain %,
    # expected of hits, whether it forces a switch, how much it heals,
    # whether it ignores abilities/defenses/evasion/immunity, min times it can hit, max times it can hit,
    # its priority bracket, how much recoil it causes, whether it self destructs,
    # whether it causes you to switch/steal boosts/thaw target/uses targets offense,
    # the moves offensive category (ohe: 3), defensive category (ohe: 3), type (ohe: ), fields (ohe: ),
    #           side conditions (ohe: ), weathers (ohe: ), targeting types (ohe: 14), volatility status (ohe: 57),
    #           status (ohe: ), boosts (ohe: 6), self-boosts (ohe: 6),
    # and the chance of a secondary effect
    def _embed_move(self, move):

        # If the move is None or empty, return a negative array (filled w/ -1's)
        if move is None or move.is_empty: return [-1] * 180

        embeddings = []

        embeddings.append([
            move.accuracy,
            move.base_power,
            int(move.breaks_protect),
            move.crit_ratio,
            move.current_pp,
            move.damage,
            move.drain,
            move.expected_hits,
            int(move.force_switch),
            move.heal,
            int(move.ignore_ability),
            int(move.ignore_defensive),
            int(move.ignore_evasion),
            1 if move.ignore_immunity else 0,
            move.n_hit[0] if move.n_hit else 1,  # minimum times the move hits
            move.n_hit[1] if move.n_hit else 1,  # maximum times the move hits
            move.priority,
            move.recoil,
            int(move.self_destruct is not None),
            int(move.self_switch is not None),
            int(move.steals_boosts),
            int(move.thaws_target),
            int(move.use_target_offensive),
        ])

        # Add Category
        embeddings.append([1 if move.category == category else 0 for category in self._knowledge['MoveCategory']])

        # Add Defensive Category
        embeddings.append([1 if move.defensive_category == category else 0
                           for category in self._knowledge['MoveCategory']])

        # Add Move Type
        embeddings.append([1 if move.type == pokemon_type else 0 for pokemon_type in self._knowledge['PokemonType']])

        # Add Fields (bad coding -- assumes field name will be move name, and uses string manipulation)
        embeddings.append([1 if move.id == field else 0 for field in self._knowledge['Field']])

        # Add Side Conditions (bad coding -- assumes side condition name will be move name, and uses string manipulation)
        embeddings.append([1 if move.side_condition == sc else 0 for sc in self._knowledge['SideCondition']])

        # Add Weathers (bad coding -- assumes field name will be move name, and uses string manipulation)
        embeddings.append([1 if move.weather == weather else 0 for weather in self._knowledge['Weather']])

        # Add Targeting Types; cardinality is 14
        embeddings.append([1 if move.deduced_target and move.deduced_target.lower() == tt else 0
                           for tt in self._knowledge['TargetType']])

        # Add Volatility Statuses; cardinality is 57
        volatility_status_embeddings = []
        for vs in self._knowledge['VolatileStatus']:
            if vs == move.volatile_status:
                volatility_status_embeddings.append(1)
            elif move.secondary and vs in list(map(lambda x: x.get('volatilityStatus', '').lower(), move.secondary)):
                volatility_status_embeddings.append(1)
            else:
                volatility_status_embeddings.append(0)
        embeddings.append(volatility_status_embeddings)

        # Add Statuses
        status_embeddings = []
        for status in self._knowledge['Status']:
            if status == move.status:
                status_embeddings.append(1)
            elif move.secondary and status in list(map(lambda x: x.get('status', ''), move.secondary)):
                status_embeddings.append(1)
            else:
                status_embeddings.append(0)
        embeddings.append(status_embeddings)

        # Add Boosts
        boost_embeddings = {'atk': 0, 'def': 0, 'spa': 0, 'spd': 0, 'spe': 0, 'evasion': 0, 'accuracy': 0}
        if move.boosts:
            for stat in move.boosts: boost_embeddings[stat] += move.boosts[stat]
        elif move.secondary:
            for x in move.secondary:
                for stat in x.get('boosts', {}): boost_embeddings[stat] += x['boosts'][stat]
        embeddings.append(boost_embeddings.values())

        # Add Self-Boosts
        self_boost_embeddings = {'atk': 0, 'def': 0, 'spa': 0, 'spd': 0, 'spe': 0, 'evasion': 0, 'accuracy': 0}
        if move.self_boost:
            for stat in move.self_boost: self_boost_embeddings[stat] += move.self_boost[stat]
        elif move.secondary:
            for x in move.secondary:
                for stat in x.get('self', {}).get('boosts', {}): self_boost_embeddings[stat] += x['self']['boosts'][
                    stat]
        embeddings.append(self_boost_embeddings.values())

        # Introduce the chance of a secondary effect happening
        chance = 0
        for x in move.secondary:
            chance = max(chance, x.get('chance', 0))
        embeddings.append([chance])

        return [item for sublist in embeddings for item in sublist]

    # We encode the opponent's mon in a 785-dimensional embedding
    # We encode all the mons moves, whether it is active, it's current hp, whether it's fainted, its level,
    # weight, whether it's recharging, preparing, dynamaxed, its stats, boosts, status,
    # types and whether it's trapped or forced to switch out.
    # We currently don't encode its item, abilities (271) or its species (1155) because of the large cardinalities
    def _embed_mon(self, battle, mon):
        embeddings = []

        # Append moves to embedding (and account for the fact that the mon might have <4 moves)
        for move in (list(mon.moves.values()) + [None, None, None, None])[:4]:
            embeddings.append(self._embed_move(move))

        # Add whether the mon is active, the current hp, whether its fainted, its level,
        # its weight and whether its recharging or preparing
        embeddings.append([
            int(mon.active),
            mon.current_hp,
            int(mon.fainted),
            mon.level,
            mon.weight,
            int(mon.must_recharge),
            1 if mon.preparing else 0,
            int(mon.is_dynamaxed),
        ])

        # Add stats and boosts
        embeddings.append(mon.stats.values())
        embeddings.append(mon.boosts.values())

        # Add status (one-hot encoded)
        embeddings.append([1 if mon.status == status else 0 for status in self._knowledge['Status']])

        # Add Types (one-hot encoded)
        embeddings.append([1 if mon.type_1 == pokemon_type else 0 for pokemon_type in self._knowledge['PokemonType']])
        embeddings.append([1 if mon.type_2 == pokemon_type else 0 for pokemon_type in self._knowledge['PokemonType']])

        # Add whether the mon is trapped or forced to switch. But first, find the index
        index = None
        if mon in battle.active_pokemon: index = 0 if battle.active_pokemon[0] == mon else 1
        embeddings.append([
            1 if index and battle.trapped[index] else 0,
            1 if index and battle.force_switch[index] else 0,
        ])

        # Flatten all the lists into a Nx1 list
        return_embedding = [item for sublist in embeddings for item in sublist]
        return return_embedding

    # We encode the opponent's mon in a 787-dimensional embedding
    # We encode all the mons moves, whether it's active, if we know it's sent, it's current hp, whether it's fainted,
    # its level, weight, whether it's recharging, preparing, dynamaxed, its base stats (because we don't know it's
    # IV/EV/Nature), boosts, status, types and whether it's trapped or forced to switch out. We currently don't encode
    # its item, possible abilities (271 * 3) or its species (1155) because of the large cardinalities
    # In the future, we should predict high/low ranges of stats based on damage and speeds/hail, and items based on cues
    def _embed_opp_mon(self, battle, mon):
        embeddings = []

        # Append moves to embedding (and account for the fact that the mon might have <4 moves)

        for move in (list(mon.moves.values()) + [None, None, None, None])[:4]:
            embeddings.append(self._embed_move(move))

        # Add whether the mon is active, the current hp, whether its fainted, its level,
        # its weight and whether its recharging or preparing
        embeddings.append([
            int(mon.active),  # This mon is on the field now
            int(mon in battle.opponent_team.values()),  # This mon was brought
            mon.current_hp,
            int(mon.fainted),
            mon.level,
            mon.weight,
            int(mon.must_recharge),
            1 if mon.preparing else 0,
            int(mon.is_dynamaxed),
        ])

        # Add stats and boosts
        embeddings.append(mon.base_stats.values())
        embeddings.append(mon.boosts.values())

        # Add status (one-hot encoded)
        embeddings.append([1 if mon.status == status else 0 for status in self._knowledge['Status']])

        # Add Types (one-hot encoded)
        embeddings.append([1 if mon.type_1 == pokemon_type else 0 for pokemon_type in self._knowledge['PokemonType']])
        embeddings.append([1 if mon.type_2 == pokemon_type else 0 for pokemon_type in self._knowledge['PokemonType']])

        # Add whether the mon is trapped or forced to switch. But first, find the index
        index = None
        if mon in battle.active_pokemon: index = 0 if battle.active_pokemon[0] == mon else 1
        embeddings.append([
            1 if index and battle.trapped[index] else 0,
            1 if index and battle.force_switch[index] else 0,
        ])

        # Flatten all the lists into a Nx1 list
        return_embedding = [item for sublist in embeddings for item in sublist]
        return return_embedding

    # Embeds the state of the battle in a 7814-dimensional embedding
    # Embed mons (and whether they're active)
    # Embed opponent mons (and whether they're active, they've been brought or we don't know)
    # Then embed all the Fields, Side Conditions, Weathers, Player Ratings, # of Turns and the bias
    def embed_battle(self, battle: DoubleBattle):
        embeddings = []

        # Add team to embeddings
        for mon in battle.sent_team.values():
            embeddings.append(self._embed_mon(battle, mon))

        # Embed opponent's mons. teampreview_opponent_team has empty move slots while opponent_team has moves we remember.
        # We first embed opponent_active_pokemon, then ones we remember from the team, then the rest
        embedded_opp_mons = set()
        for mon in battle.opponent_active_pokemon:
            if mon:
                embeddings.append(self._embed_opp_mon(battle, mon))
                embedded_opp_mons.add(mon.species)

        for mon in battle.opponent_team.values():
            if mon.species in embedded_opp_mons: continue
            embeddings.append(self._embed_opp_mon(battle, mon))
            embedded_opp_mons.add(mon.species)

        for mon in battle.teampreview_opponent_team:
            if mon in embedded_opp_mons: continue
            embeddings.append(self._embed_opp_mon(battle, battle.teampreview_opponent_team[mon]))
            embedded_opp_mons.add(mon)

        # Add Dynamax stuff
        embeddings.append(battle.can_dynamax + battle.opponent_can_dynamax + [battle.dynamax_turns_left,
                                                                              battle.opponent_dynamax_turns_left])

        # Add Fields;
        embeddings.append([1 if field in battle.fields else 0 for field in self._knowledge['Field']])

        # Add Side Conditions
        embeddings.append([1 if sc in battle.side_conditions else 0 for sc in self._knowledge['SideCondition']])

        # Add Weathers
        embeddings.append([1 if weather == battle.weather else 0 for weather in self._knowledge['Weather']])

        # Add Player Ratings, the battle's turn and a bias term
        embeddings.append(list(map(lambda x: x if x else -1, [battle.rating, battle.opponent_rating, battle.turn, 1])))

        # Flatten all the lists into a 7814-dim list
        return np.array([item for sublist in embeddings for item in sublist])

    # Define the incremental reward for the current battle state over the last one
    def compute_reward(self, battle) -> float:
        """A helper function to compute rewards.
        The reward is computed by computing the value of a game state, and by comparing it to the last state.
        State values are computed by weighting different factor. Fainted pokemons, their remaining HP, inflicted
        statuses and winning are taken into account. These are how we define the reward of the state

        Won 50000 (should really be the only thing we optimize for, since there are concepts like reverse-sweeping)

        These are other things that we could reward:
        - Fainted pokemon (100 each; 400 max)
        - Speed of mons (+25 for every mon faster, -25 for every mon slower; 100 max)
        - Current Type advantage (+25 for every type advantage, average of off/def; 100 max)
        - HP Difference (adding %'s; 100 max)
        - Condition (10 each; 40 max)
        - Information

        :param battle: The battle for which to compute rewards.
        :type battle: Battle
        :return: The reward.
        :rtype: float
        """

        current_value = 0
        victory_value, starting_value, fainted_value, hp_value = 70, 0, 3.25, 3.25

        # Initialize our reward buffer if this is the first turn in a battle.
        # Since we incorporate speed and type advantage, our turn 0 reward will be non-0
        if battle not in self._reward_buffer:
            self._reward_buffer[battle] = starting_value

        # # Incorporate rewards for our team
        # for mon in battle.team.values():
        #     current_value += mon.current_hp_fraction * hp_value # We value HP at 25 points for 100% of a mon's
        #     if mon.fainted: current_value -= fainted_value # We value fainted mons at 100 points

        # # Incorporate rewards for other team (to keep symmetry)
        # for mon in battle._teampreview_opponent_team:
        #     current_value -= mon.current_hp_fraction * hp_value
        #     if mon.fainted: current_value += fainted_value

        # Victory condition
        if battle.won:
            current_value += victory_value
        elif battle.lost:
            current_value -= victory_value

        # We return the difference between rewards now and save this battle turn's reward for the next turn
        to_return = current_value - self._reward_buffer[battle]
        self._reward_buffer[battle] = current_value

        return to_return

    # Because of env_player implementation, it requires an initial parameter passed, in this case,
    # it's the object itself (player == self)
    def _training_helper(self, player, num_steps=10000):
        self._dqn.fit(env=self, nb_steps=num_steps)
        self.complete_current_battle()

    def train(self, opponent: Player, num_steps: int) -> None:
        self.play_against(
            env_algorithm=self._training_helper,
            opponent=opponent,
            env_algorithm_kwargs={"num_steps": num_steps},
        )

    def save_model(self, filename=None) -> None:
        if filename is not None:
            self._dqn.save_weights("models/" + filename, overwrite=True)
        else:
            self._dqn.save_weights("models/model_" + datetime.now().strftime("%Y_%m_%d_%H_%M_%S"), overwrite=True)

    def load_model(self, filename: str) -> None:
        self._dqn.load_weights("models/" + filename)

    def evaluate_model(self, num_battles: int, v=True) -> float:
        self.reset_battles()
        self._dqn.test(env=self, nb_episodes=num_battles, visualize=False, verbose=False)
        if v: print("DQN Evaluation: %d wins out of %d battles" % (self.n_won_battles, num_battles))
        return self.n_won_battles * 1. / num_battles

    def choose_move(self, battle: DoubleBattle) -> BattleOrder:
        if battle not in self._observations or battle not in self._actions: self._init_battle(battle)
        self._observations[battle].put(self.embed_battle(battle))
        action = self._actions[battle].get()
        return self._action_to_move(action, battle)

    # Same as max damage for now - we return the mons who have the best average type advantages against the other team
    # TODO: implement using Q-values and minimax to send out position that maximizes our worst position
    def teampreview(self, battle):

        # We have a dict that has index in battle.team -> average type advantage
        mon_performance = {}

        # For each of our Pokemons
        for i, mon in enumerate(battle.team.values()):
            # We store their average performance against the opponent team
            mon_performance[i] = np.mean([compute_type_advantage(mon, opp) for opp in battle.opponent_team.values()])

        # We sort our mons by performance, and choose the top 4
        ordered_mons = sorted(mon_performance, key=lambda k: -mon_performance[k])[:4]

        # We start with the one we consider best overall
        # We use i + 1 as python indexes start from 0 but showdown's indexes start from 1,
        # and return the first 4 mons, in term of importance
        # return "/team " + "".join([str(i + 1) for i in ordered_mons])
        return "/team " + "".join(random.sample(list(map(lambda x: str(x + 1), range(0, len(battle.team)))), k=4))
