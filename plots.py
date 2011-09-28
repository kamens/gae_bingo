import logging
import os
import time

from google.appengine.ext.webapp import template, RequestHandler

from .cache import BingoCache
from .models import _GAEBingoSnapshotLog

class Timeline(RequestHandler):

    def post(self):

        experiment_name = self.request.get("experiment_name")

        if not experiment_name:
            return

        bingo_cache = BingoCache.get()
        experiment_model = bingo_cache.get_experiment( experiment_name )

        query = _GAEBingoSnapshotLog.all().ancestor(experiment_model)
        experiment_snapshots = query.fetch(1000)
        
        experiment_data = {}
        for snapshot in experiment_snapshots :

            if snapshot.alternative_name not in experiment_data:
                experiment_data[snapshot.alternative_name] = {'name': snapshot.alternative_name.replace("'", '"'), 'snapshots':[] }  # HACK TODO : proper escaping

            conv_rate = 0.0
            if snapshot.participants > 0 :
                conv_rate = float(snapshot.conversions) / float(snapshot.participants) * 100.0
            conv_rate = round( conv_rate, 1 )

            utc_time = time.mktime( snapshot.time_recorded.timetuple() ) * 1000

            experiment_data[snapshot.alternative_name]['snapshots'].append( [ utc_time, conv_rate ] )
        
        path = os.path.join(os.path.dirname(__file__), "templates/timeline.html")
        self.response.out.write(
            template.render(path, {
                "experiment_name": experiment_name,
                "experiment_data": experiment_data,
            })
        )
