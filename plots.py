import logging
import os
import time

from google.appengine.ext.webapp import RequestHandler

from .cache import BingoCache
from .models import _GAEBingoSnapshotLog, ConversionTypes

def get_experiment_timeline_data(experiment):

    bingo_cache = BingoCache.get()
        
    query = _GAEBingoSnapshotLog.all().ancestor(experiment)
    query.order('-time_recorded')
    experiment_snapshots = query.fetch(1000)
    
    experiment_data_map = {}
    experiment_data = []
    y_scale_multiplier = 1.0 if experiment.conversion_type == ConversionTypes.Counting else 100.0
    
    def get_alternative_content_str(alt_num):
        alts = bingo_cache.get_alternatives(experiment.name)
        for alt in alts:
            if alt.number == alt_num:
                return str(alt.content)
        return "Alternative #" + str(alt_num) 
    
    for snapshot in experiment_snapshots:

        if snapshot.alternative_number not in experiment_data_map:
            alternative_content_str = get_alternative_content_str(snapshot.alternative_number)
            experiment_data.append({ "name": alternative_content_str, "data": [] })
            experiment_data_map[snapshot.alternative_number] = experiment_data[-1]

        conv_rate = 0.0
        if snapshot.participants > 0:
            conv_rate = float(snapshot.conversions) / float(snapshot.participants) * y_scale_multiplier
        conv_rate = round(conv_rate, 3)

        utc_time = time.mktime(snapshot.time_recorded.timetuple()) * 1000

        experiment_data_map[snapshot.alternative_number]["data"].append([utc_time, conv_rate])

    return experiment_data
