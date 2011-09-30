import logging
import os
import time

from google.appengine.ext.webapp import template, RequestHandler

from .cache import BingoCache
from .models import _GAEBingoSnapshotLog

class TimeSeries:
    def __init__(self, name):
        self.name = name
        self.snapshots = []
    
class Timeline(RequestHandler):
    def get(self):

        experiment_name = self.request.get("experiment_name")

        if not experiment_name:
            return

        bingo_cache = BingoCache.get()
        experiment = bingo_cache.get_experiment(experiment_name)

        query = _GAEBingoSnapshotLog.all().ancestor(experiment)
        query.order('-time_recorded')
        experiment_snapshots = query.fetch(1000)
        
        experiment_data_map = {}
        experiment_data = []
        
        def get_alternative_content_str(alt_num):
            alts = bingo_cache.get_alternatives(experiment_name)
            for alt in alts:
                if alt.number == alt_num:
                    return alt.content
            return "Alternative #" + str(alt_num) 
        
        for snapshot in experiment_snapshots:

            if snapshot.alternative_number not in experiment_data_map:
                alternative_content_str = get_alternative_content_str(snapshot.alternative_number)
                experiment_data.append(TimeSeries(alternative_content_str))
                experiment_data_map[snapshot.alternative_number] = experiment_data[-1]

            conv_rate = 0.0
            if snapshot.participants > 0:
                conv_rate = float(snapshot.conversions) / float(snapshot.participants) * 100.0
            conv_rate = round(conv_rate, 1)

            utc_time = time.mktime(snapshot.time_recorded.timetuple()) * 1000

            experiment_data_map[snapshot.alternative_number].snapshots.append([utc_time, conv_rate])
        
        path = os.path.join(os.path.dirname(__file__), "templates/timeline.html")
        self.response.out.write(
            template.render(path, {
                "experiment": experiment,
                "experiment_data": experiment_data,
            })
        )
