# TODO(chris): break dependency on KA website code. This file is specific to
# the KA website and is required by bingo.

import cPickle as pickle

load = pickle.loads
dump = pickle.dumps
