import datetime
import time

from .cache import BingoCache
from .models import _GAEBingoSnapshotLog

def get_experiment_timeline_data(experiment, alternatives):
    query = _GAEBingoSnapshotLog.all().ancestor(experiment)
    query.order('-time_recorded')
    experiment_snapshots = query.fetch(1000)

    experiment_data_map = {}
    experiment_data = []

    def get_alt_str(n):
        for alt in alternatives:
            if alt.number == n:
                return alt.pretty_content
        return "Alternative #" + str(n)

    for snapshot in experiment_snapshots:
        n = snapshot.alternative_number

        if n not in experiment_data_map:
            data = {
                "name": get_alt_str(n),
                "data": []
            }
            experiment_data.append(data)
            experiment_data_map[n] = data

        utc_time = time.mktime(snapshot.time_recorded.timetuple()) * 1000

        experiment_data_map[n]["data"].append([
            utc_time,
            snapshot.participants,
            snapshot.conversions
        ])

    # add an extra data point to each series that represents the latest counts
    # this relies on the alternatives parameter being prefilled by the caller
    if experiment.live:
        utcnow = time.mktime(datetime.datetime.utcnow().timetuple()) * 1000
        for series in experiment_data:
            alt = next(a for a in alternatives
                       if get_alt_str(a.number) == series["name"])
            series["data"].append([utcnow, alt.participants, alt.conversions])

    return experiment_data
