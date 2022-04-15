import sys
from typing import Dict, List, Optional

from poke_env.environment.battle import Battle
from poke_env.player.battle_order import *
from reuniclusVGC.helpers.doubles_utils import *

# Predicts Ability of a mon given a team-builder, then battle history
class TraceModel():

  def __init__(self, gen=8, priorty=0):
    pass

  # Predict abilities based on teampreview
  def predict_prior(self, mon, observed_team):
    return None

  # Predict abilities based on teampreview and battle history
  def predict_posterier(self, mon, observed_team, history):
    return None

  # Trains model
  def train(self, data):
    return None

  # Saves model
  def save(self, filename):
    return None

  # Read file of pre-trained parameters
  def load(self, filename):
    return None
