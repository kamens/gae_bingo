import os
import logging

from google.appengine.ext.webapp import template, RequestHandler

from .gae_bingo import bingo, ab_test
from .cache import bingo_and_identity_cache
from .stats import describe_result_in_words
from .config import can_control_experiments
from django.utils import simplejson as json


class Blotter(RequestHandler):
  """Blotter is a bingo callback for use from the client side 
  
  GETs allow you to check the user's experiment status from within js while 
  POSTs allow you to score conversions for a given test
  
  """

  def get(self):
    """request user condition/state for an experiment by passing 
    { canonical_name : "experiment_name" }
    
    successful requests return 200 and a json object { "experiment_name" : "state" }
    where state is a jsonified version of the user's state in the experiment
    
    if a user can_control_experiments, requests may create experiments on the server
    similar to calling ab_test directly. You should pass in:
    { "canonical_name": <string>, "alternative_params": <json_obj>, "conversion_name": <json_list>}
    This will return a 201 and the jsonified state of the user calling ab_test
    
    failed requests return 404 if the experiment is not found and
    return a 400 if the params are passed incorrectly
    """
    experiment_name = self.request.get("canonical_name", None)
    alternative_params = self.request.get("alternative_params", default_value = None)
    if (alternative_params):
      alternative_params = json.loads(alternative_params)

    conversion_name = self.request.get("conversion_name", default_value = None)
    if (conversion_name):
      conversion_name = json.loads(conversion_name)

    bingo_cache, bingo_identity_cache = bingo_and_identity_cache()

    self.response.headers['Content-Type'] = 'text/json'

    # return false if experiment not found (don't create a new one!)
    if(experiment_name):
      if experiment_name not in bingo_cache.experiments:
        if can_control_experiments():
          # create the given ab_test with passed params, etc
          condition = ab_test(experiment_name, alternative_params, conversion_name)
          logging.info("blotter created ab_test: %s", experiment_name)
          self.response.set_status(201)
          self.response.out.write(json.dumps(condition))
          return
        else:
          # experiment not found (and not being created)
          self.response.set_status(404)
          return
      
      # return status for experiment (200 implicit)
      else:
        condition = ab_test(experiment_name)
        self.response.out.write(json.dumps(condition))
        return
    
    else:
      # no params passed, sorry broheim
      self.response.set_status(400)
      self.response.out.write('"hc svnt dracones"')
      return
  


  def post(self):
    """post a conversion to blotter by passing { convert : "conversion_name" }
    
    you cannot currently pass a json list (as the response would be a bit ambiguous)
    so instead pass multiple calls to post (which is what the js tool does)
    
    successful conversions return HTTP 204
    
    failed conversions return a 404 (i.e. experiment not found in reverse-lookup)
    
    no params returns a 400 error
    """
    bingo_cache, bingo_identity_cache = bingo_and_identity_cache()
    
    conversion = self.request.get("convert", None)
    if(conversion):
      conversion = json.loads(conversion)

    self.response.headers['Content-Type'] = 'text/json'

    experiment_names = bingo_cache.get_experiment_names_by_conversion_name(conversion)
    if (conversion):
      if(len(experiment_names) > 0):
        # send null message
        self.response.set_status(204)
        # score the conversion
        bingo(conversion)
        return
    
      else:
        # send error
        self.response.set_status(404)
        return
    else:
      # no luck, compadre
      self.response.set_status(400)
      self.response.out.write('"hc svnt dracones"')
    