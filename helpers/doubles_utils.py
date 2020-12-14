from poke_env.player.player import Player
from poke_env.player.random_player import RandomPlayer
from poke_env.environment.move import Move
from poke_env.environment.pokemon import Pokemon
from typing import Optional
import random
import itertools

# This represents an action that a single Pokemon can take -- it can either be a switch or a move
class Action:
    _actor, _action, _target = None, None, None

    def __init__(self, actor=None, action=None, target=None):
        self._actor = actor
        self._action = action
        self._target = target if target != 0 else None

    def isEmpty(self) -> bool:
        """
        :return: Whether the Action has been set to anything, or is an empty action (default)
        :rtype: bool
        """
        return self._actor == None and self._action == None and self._target==None

    def isMove(self) -> bool:
        """
        :return: Whether this action represents a move. If empty, will return False
        :rtype: bool
        """
        return self._action is not None and isinstance(self._action, Move)

    def isSwitch(self) -> bool:
        """
        :return: Whether this action represents a switch. If empty, will return False
        :rtype: bool
        """
        return self._action is not None and isinstance(self._action, Pokemon)

    def showdownify(self) -> str:
        """
        :return: The Showdown message we should return for this Action. You still have to do some work to get this move to work w/ others (eg include "/choose" and ",")
        :rtype: str
        """
        if self.isEmpty(): return "default"
        elif self.isMove(): return "move " + str(self.move.id) + (" " + str(self.target) if self.target is not None else "")
        else: return "switch " + self.switch.species

    @property
    def target(self) -> Optional[int]:
        """
        :return: The target of the move, if there is one (self does not count), otherwise, return None
        :rtype: int
        """
        return self._target

    @target.setter
    def target(self, target: Optional[int]):
        self._target = target if target != 0 else None

    @property
    def move(self) -> Optional[Move]:
        """
        :return: Move if the action is a Move, otherwise None
        :rtype: Move
        """
        return self._action if self.isMove() and not self.isEmpty() else None

    @property
    def switch(self) -> Optional[Pokemon]:
        """
        :return: Pokemon that the user wants to Switch to, if the action is a Switch, otherwise None
        :rtype: Move
        """
        return self._action if not self.isMove() and not self.isEmpty() else None

    @property
    def actor(self) -> Pokemon:
        """
        :return: Pokemon that is doing the action (either the switching or using a move)
        :rtype: Pokemon
        """
        return self._actor

    def __str__(self):
        if self.isMove(): return "Actor: " + self._actor.species + ",Move: " + str(self._action.id) + (",Target:" + str(self._target) if self._target is not None else "")
        elif self.isSwitch(): return "Actor: " + self._actor.species + ",Switch: " + str(self._action.species)
        else: return "Empty Action"

    def __repr__(self):
        return self.__str__()

# Gets all possible moves for a Pokemon
def get_possible_moves(battle, mon):
    """
    :return: A list of all actions a pokemon can do in its position for the battle
    :rtype: List[Action]
    """

    actions = []

    # If we somehow don't have any active pokemon or the mon is None, return None
    if battle is None or not (battle.active_pokemon) or mon is None:
        return [Action()]

    # Find index of the mon, and if the mon passsed in isn't active, we raise a problem
    index = 0 if battle.active_pokemon[0] is not None and mon.species == battle.active_pokemon[0].species else 1
    if all(battle.active_pokemon) and mon.species != battle.active_pokemon[0].species and mon.species != battle.active_pokemon[1].species:
        raise("you passed in a mon that doesnt exist!")

    # Iterate through available moves
    for move in battle.available_moves[index]:

        # Add all available move to list against all targets
        for target in battle.get_possible_showdown_targets(move, mon):
            actions.append(Action(mon, move, target))

    # Add all available switches to this list, if either the pokemon isn't trapped or we're forced to switch
    if not battle.trapped[index] or battle.force_switch[index]:
        for pokemon in battle.available_switches[index]:
            actions.append(Action(mon, pokemon))

    # Always return an empty action if there are none available
    return actions if len(actions) > 0 else [Action()]

# Filter tuples of moves to ones that are possible
def filter_to_possible_moves(battle, actions):
    """
    :return: A list of tuples that contain possible actions
    :rtype: List[(Action, Action)]
    """

    filtered_moves = []

    # Iterate through every action
    for action1, action2 in actions:

        # Can't switch to the same mon
        if action1.isSwitch() and action2.isSwitch() and action1.switch.species == action2.switch.species: continue

        # Can't use a move w/ no PP
        if (action1.isMove() and action1.move.current_pp == 0) or (action2.isMove() and action2.move.current_pp == 0): continue

        filtered_moves.append((action1, action2))

    return filtered_moves

# Filters all actions to reasonable moves
def filter_to_reasonable_moves(battle, actions):
    reasonable_moves = []

    # TODO: change these to positives; e.g is_valid_self_hit, is_valid_self_boost, is_valid_side_condition
    for action1, action2 in actions:
        if (action1.isMove() and action1.move.current_pp == 0) or (action2.isMove() and action2.move.current_pp == 0): continue

        if _useless_self_boost(action1) or _useless_self_boost(action2): continue
        if _useless_battle_condition(battle, action1) or _useless_battle_condition(battle, action2): continue
        if _useless_self_hit(battle, action1) or _useless_self_hit(battle, action2): continue

        reasonable_moves.append((action1, action2))

    return reasonable_moves

# Return if the self-boost is inneffectual
def _useless_self_boost(action):
    if action.isMove():

        # Only consider self- or ally-boosting moves if you have boosts left, or if you dont, if the other pokemon has sucker punch
        if action.move.boosts and action.move.target == 'self':
            num_failed = 0
            for stat in action.move.boosts:
                if (action.actor.boosts[stat] == 6 and action.boosts[stat] > 0) or (action.actor.boosts[stat] == -6 and action.move.boosts[stat] < 0): num_failed += 1
            if num_failed < len(action.move.boosts):
                return True
    return False

# Return if side condition move is useless. This should eventually return False for everything when we learn better (e.g. Torkoal switch-ins)
def _useless_battle_condition(battle, action):
    if not action.isMove(): return False

    if action.move.side_condition and action.move.side_condition in battle.side_conditions: return True
    if action.move.weather and action.move.weather in battle.weather: return True
    if action.move.terrain and action.move.terrain in battle.terrain: return True
    return False

# Method to help reduce state space (will eventually default to 0). Here's the cases in which a self-hit is valid:
# Activate Weakness Policy
# Activate Justified
# Activate Berserk
# Activate Anger Point/Water Absorb/Volt Absorb/flash fire
# If actor has no more non-damaging moves and the opposing mon has suckerpunch
# Can default to False to eliminate self-hits, and True to not eliminate anything
def _useless_self_hit(battle, action):

    # Eliminate easy conditions in which this is not a useless self hit
    if not action.isMove(): return False
    if not _does_damage(action): return False
    if action.move.self_switch: return False

    # If it's a self-hit
    if action.target and action.target < 0:
        target_mon = battle.active_pokemon[action.target]
        if target_mon.item == 'weaknesspolicy' and action.move.type.damage_multiplier(*target_mon.types) >= 2: return True
        elif target_mon.ability == 'Berserk': return False
        elif target_mon.ability == 'Justified' and action.move.type == 'DARK': return False
        elif target_mon.ability == 'Water Absorb' and action.move.type == 'WATER': return False
        elif target_mon.ability == 'Volt Absorb' and action.move.type == 'ELECTRIC': return False
        elif target_mon.ability == 'Flash Fire' and action.move.type == 'FIRE': return False
        else: return True

    return False


# If not a move, returns false
def _does_damage(action):
    return action.isMove() and (action.move.base_power > 0 or action.move.damage)
