import logging
import os

from google.appengine.ext.webapp import template, RequestHandler

from .gae_bingo import bingo, ab_test
from .cache import bingo_and_identity_cache
from .stats import describe_result_in_words
from .config import can_control_experiments


class Blotter(RequestHandler):
  """Blotter is a bingo callback for use from the client side 
  
  GETs allow you to check the user's experiment status from within js while 
  POSTs allow you to score conversions for a given test
  
  """

  def get(self):
    """request user condition/state for an experiment by passing { experiment : "experiment_name" }
    
    successful requests return 200 and a json object { "experiment_name" : "state" }
      where state is a stringified version of the user's state in the experiment
      this needs more work to jsonify correctly, but no big deal for now
    
    failed requests return 404 if the experiment is not found and 
      a return a 400 if the params are passed incorrectly
    """
    experiment_name = self.request.get("canonical_name", None)
    alternative_params = self.request.get("alternative_params[]", allow_multiple=True, default_value = None)
    conversion_name = self.request.get("conversion_name[]", allow_multiple=True, default_value = None)

    logging.info("alternative_params: %s", alternative_params)

    bingo_cache, bingo_identity_cache = bingo_and_identity_cache()

    self.response.headers['Content-Type'] = 'text/json'

    # return false if experiment not found (don't create a new one!)
    if(experiment_name):
      if experiment_name not in bingo_cache.experiments:
        if can_control_experiments():
          # create the given ab_test with passed params, etc
          logging.info("creating experiment %s", experiment_name)
          condition = str(ab_test(experiment_name, alternative_params, conversion_name))
          self.response.out.write('"%s"' % (condition))
          return
        else:
          # experiment not found (and not being created)
          self.response.set_status(404)
          return
      
      # return status for experiment (200 implicit)
      else:
        condition = str(ab_test(experiment_name))
        self.response.out.write('"%s"' % (condition))
        return
    
    else:
      # no params passed, sorry broheim
      self.response.set_status(400)
      self.response.out.write('"hc svnt dracones"')
      return
  


  def post(self):
    """post a conversion to blotter by passing { convert : "conversion_name" }
    
    successful conversions return HTTP 204
    
    failed conversions return a 404 (i.e. experiment not found in lookup)
    
    no params returns a 400 error ()
    """
    bingo_cache, bingo_identity_cache = bingo_and_identity_cache()
    
    conversion = self.request.get("convert", None)

    self.response.headers['Content-Type'] = 'text/json'

    experiment_names = bingo_cache.get_experiment_names_by_conversion_name(conversion)
    logging.info(experiment_names)
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
      