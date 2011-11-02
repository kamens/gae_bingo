"""Blotter is a bingo callback for use from the client side 

GETs allow you to check the user's experiment status from within js while 
POSTs allow you to score conversions for a given test

"""
import os
import logging

from google.appengine.ext.webapp import RequestHandler

from .gae_bingo import bingo, ab_test
from .cache import BingoCache
from .config import can_control_experiments
import simplejson as json

class AB_Test(RequestHandler):
    """request user alternative/state for an experiment by passing 
    { canonical_name : "experiment_name" }
    
    successful requests return 200 and a json object { "experiment_name" : "state" }
    where state is a jsonified version of the user's state in the experiment
    
    if a user can_control_experiments, requests may create experiments on the server
    similar to calling ab_test directly. You should pass in:
        { 
            "canonical_name": <string>,
            "alternative_params": <json_obj | json_list>,
            "conversion_name": <json_list>
        }
    *q.v. gae_bingo.ab_test*
    
    Creating a new experiment will return a 201 and the 
    jsonified state of the user calling ab_test
    
    Simply querying an experiment successfully will return a 200
    
    failed requests return 404 if the experiment is not found and
    return a 400 if the params are passed incorrectly
    """
    
    def post(self):
        
        experiment_name = self.request.get("canonical_name", None)
        alternative_params = self.request.get("alternative_params", None)
        
        if alternative_params:
            alternative_params = json.loads(alternative_params)
        
        bingo_cache = BingoCache.get()
        conversion_name = self.request.get("conversion_name", None)
        
        if conversion_name:
            conversion_name = json.loads(conversion_name)
        
        self.response.headers['Content-Type'] = 'text/json'
        
        status = 200
        response = None
        
        if experiment_name:
            
            if experiment_name not in bingo_cache.experiments:
                
                if can_control_experiments():
                    # create the given ab_test with passed params, etc
                    response = ab_test(experiment_name, alternative_params, conversion_name)
                    status = 201
                
                else:
                    # experiment not found (and not being created)
                    status = 404
            
            # return status for experiment (200 implicit)
            else:
                response = ab_test(experiment_name)
        
        else:
            # no params passed, sorry broheim
            status = 400
            response = "hc svnt dracones"
        
        
        self.response.set_status(status)
        response = json.dumps(response)
        if response is not 'null':
            self.response.out.write(response)
        return



class Bingo(RequestHandler):
    """post a conversion to gae_bingo by passing { convert : "conversion_name" }
    
    you cannot currently pass a json list (as the response would be a bit ambiguous)
    so instead pass multiple calls to post (which is what the js tool does)
    
    successful conversions return HTTP 204
    
    failed conversions return a 404 (i.e. experiment not found in reverse-lookup)
    
    no params returns a 400 error
    """

    def post(self):
        
        bingo_cache = BingoCache.get()
        
        conversion = self.request.get("convert", None)
        if conversion:
            try:
                conversion = json.loads(conversion)
            except json.JSONDecodeError, e:
                logging.error("json.loads FAILED on input: %s", conversion)
                raise e

        self.response.headers['Content-Type'] = 'text/json'

        experiment_names = bingo_cache.get_experiment_names_by_conversion_name(conversion)
        
        status = 200
        response = None
        
        if conversion:
            
            if len(experiment_names) > 0:
                # send null message and score the conversion
                status = 204
                bingo(conversion)
            
            else:
                # send error
                status = 404
        
        else:
            # no luck, compadre
            status = 400
            response = "hc svnt dracones"
        
        self.response.set_status(status)
        if response:
            self.response.out.write(json.dumps(response))
        return
        
