# Google App Engine Bingo

GAE/Bingo is a drop-in split testing framework for App Engine heavily inspired by [Patrick McKenzie](http://www.kalzumeus.com)'s [A/Bingo](http://www.bingocardcreator.com/abingo). If you're on App Engine, GAE/Bingo can get your A/B tests up and running in minutes.

GAE/Bingo is [MIT licensed](http://en.wikipedia.org/wiki/MIT_License).

* <a href="#features">Features</a>  
* <a href="#screens">Screenshots and Code Samples</a>  
* <a href="#principles">Design Principles</a>  
* <a href="#start">Getting Started</a>  
* <a href="#features">Features</a>  
* <a href="#bonus">Bonus</a>  
* <a href="#faq">FAQ</a>  

## <a name="features">Features</a>

Free features inherited [directly from A/Bingo's design](http://www.bingocardcreator.com/abingo):

* Test display or behavioral differences in one line of code.
* Measure any event as a conversion in one line of code.
* Eliminate guesswork: automatically test for statistical significance.
* Blazingly fast, with minimal impact on page load times or server load.
* Written by programmers, for programmers. Marketing is an engineering discipline!

Plus extra goodies:

* Drop-in split testing for App Engine with minimal configuration
* Framework agnostic -- works with webapp, Django, Flask, whatever.
* Persistent storage of test results -- if you're running experiments
  that take a long time like, say, [testing your software's effects on a student's education](http://www.khanacademy.org), that's no problem.
* Performance optimized for App Engine

## <a name="screens">Screenshots and Code Samples</a>

<img src="http://i.imgur.com/x4Hew.png"/><br/><em>Your dashboard shows all experiments along with statistical analysis of the results.</em><br/><br/>

## <a name="start">Getting Started</a>

1. Download this repository's source and copy the `gae_mini_profiler/` folder into your App Engine project's root directory.
2. Add the following two handler definitions to `app.yaml`:
<pre>
handlers:
&ndash; url: /gae_mini_profiler/static
&nbsp;&nbsp;static_dir: gae_mini_profiler/static<br/>
&ndash; url: /gae_mini_profiler/.*
&nbsp;&nbsp;script: gae_mini_profiler/main.py
</pre>
3. Modify the WSGI application you want to profile by wrapping it with the gae_mini_profiler WSGI application:
<pre>
&#35; Example of existing application
application = webapp.WSGIApplication(...existing application...)<br/>
&#35; Add the following
from gae_mini_profiler import profiler
application = profiler.ProfilerWSGIMiddleware(application)
</pre>
4. Insert the `profiler_includes` template tag below jQuery somewhere (preferably at the end of your template):
<pre>
        ...your html...
        {% profiler_includes %}
    &lt;/body&gt;
&lt;/html&gt;
</pre>
5. You're all set! Just choose the users for whom you'd like to enable profiling in `gae_mini_profiler/config.py`:
<pre>
&#35; If using the default should_profile implementation, the profiler
&#35; will only be enabled for requests made by the following GAE users.
enabled_profiler_emails = [
    "kamens@gmail.com",
]
</pre>

## <a name="features">Features</a>

* Production profiling without impacting normal users
* Easily profile all requests, including ajax calls
* Summaries of RPC call types and their performance so you can quickly figure out whether datastore, memcache, or urlfetch is your bottleneck
* Redirect chains are tracked -- quickly examine the profile of not just the currently rendered request, but any preceding request that issued a 302 redirect leading to the current page.
* Share individual profile results with others by sending link
* Duplicate RPC calls are flagged for easy spotting in case you're repeating memcache or datastore queries.
* Quickly sort and examine profiler stats and call stacks

## <a name="bonus">Bonus</a>

gae_bingo was developed for and is currently in production use at Khan Academy (http://khanacademy.org). If you make find good use of it elsewhere, be sure to let us know.

## <a name="faq">FAQ</a>

1. I had my appstats_RECORD_FRACTION variable set to 0.1, which means only 10% of my queries where getting profiles generated.  This meant that most of the time gae_mini_profiler was failing with a javascript error, because the appstats variable was null.

    If you are using appengine_config.py to customize Appstats behavior you should add this to the top of your "appstats_should_record" method.  
<pre>def appstats_should_record(env):
        from gae_mini_profiler.config import should_profile
        if should_profile(env):
            return True
</pre>
...coming soon, plz be patient...
