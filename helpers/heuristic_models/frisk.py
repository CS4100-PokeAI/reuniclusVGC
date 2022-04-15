import sys
from typing import Dict, List, Optional

from poke_env.environment.battle import Battle
from poke_env.player.battle_order import *
from reuniclusVGC.helpers.doubles_utils import *

# Predicts Items of a mon given a team-builder, then battle history
class FriskModel():

  def __init__(self):
    return

  # Predict items based on teampreview
  def predict_prior(self, mon, observed_team):
    return None

  # Predict items based on teampreview and battle history
  def predict_posterior(self, mon, observed_team, history):
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
