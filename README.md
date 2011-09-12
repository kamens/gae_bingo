# GAE/Bingo

GAE/Bingo is a drop-in split testing framework for App Engine, built for [Khan Academy](http://www.khanacademy.org) and *heavily* inspired by [Patrick McKenzie](http://www.kalzumeus.com)'s [A/Bingo](http://www.bingocardcreator.com/abingo). If you're on App Engine, GAE/Bingo can get your A/B tests up and running in minutes.

You can read [more about the initial inspiration and design of
GAE/Bingo](http://bjk5.com/coming-soon).

GAE/Bingo is [MIT licensed](http://en.wikipedia.org/wiki/MIT_License).

* <a href="#features">Features</a>  
* <a href="#screens">Screenshots and Code Samples</a>  
* <a href="#principles">Design Principles</a>  
* <a href="#start">Getting Started</a>  
* <a href="#non-features">Non-features so far</a>  
* <a href="#bonus">Bonus</a>  
* <a href="#faq">FAQ</a>  

## <a name="features">Features</a>

Free features [inherited quite directly from A/Bingo's design](http://www.bingocardcreator.com/abingo):

* Test display or behavioral differences in one line of code.
* Measure any event as a conversion in one line of code.
* Eliminate guesswork: automatically test for statistical significance.
* Blazingly fast, with minimal impact on page load times or server load.
* Written by programmers, for programmers. Marketing is an engineering discipline!

Plus extra goodies:

* Drop into App Engine with minimal configuration
* Framework agnostic -- works with webapp, Django, Flask, whatever.
* Persistent storage of test results -- if you're running experiments
  that take a long time like, say, [testing your software's effects on a student's education](http://www.khanacademy.org), that's no problem.
* Performance optimized for App Engine

## <a name="screens">Screenshots and Code Samples</a>

<img src="http://i.imgur.com/x4Hew.png"/><br/><em>Your dashboard lets you control all experiments along with statistical analysis of the results.</em><br/><br/>

### Starting an experiment
This line of code will automatically set up an A/B test named "new button
design" (if necessary) and return True or False by default. Use this anywhere
you can run Python code, it's highly optimized.

<pre>from gae_bingo.gae_bingo import ab_test

...

if ab_test("new button design"):
    return "new_button_class"
else:
    return "old_button_class"

...
</pre>

You can also specify an identifier for the conversion metric you're expecting
to analyze.

<pre>
if ab_test("crazy new type of animal", conversion_name="animals escaped"):
    return Gorillas()
else:
    return Monkeys()
</pre>

If you don't specify a conversion_name when starting a test, GAE/Bingo will
automatically listen for conversions with the same name as the experiment.

### Scoring a conversion
This line of code will score a conversion in the "new button design" experiment
for the current user.

<pre>from gae_bingo.gae_bingo import bingo

...
bingo("new button design")
</pre>

...or, in the case of the above "crazy new type of animal" experiment,
<pre>bingo("animals escaped")
</pre>

### Specifying alternatives
Even though the above two lines are all you need to start running some pretty
useful A/B tests, you've got more power than that. Choose from any of the
following lines of code to return various alternatives for your tests.
Remember: each individual user will get consistent results from these
functions.

<pre>from gae_bingo.gae_bingo import ab_test

...

# SIMPLE
#
# Returns True or False
#
use_new_button_design = ab_test("new button design")

...

# LIST OF ALTERNATIVES
#
# Returns "old" or "shiny"
#
button_class = ab_test("new button class", ["old", "shiny"])

...

# LIST OF >2 ALTERNATIVES (multivariate testing)
#
# Returns 10, 15, or 20
#
answers_required = ab_test("answers required", [10, 15, 20])

...

# WEIGHTED ALTERNATIVES
# (use a dictionary with alternatives as keys and weights as values)
#
# Returns "crazy" to 1/5 of your users and "normal" to 4/5 of your users
#
crazy_experiment = ab_test("crazy experiment", {"crazy": 1, "normal": 4})

</pre>

### Testing multiple results for a single experiment
You may want to statistically examine different dimensions of an experiment's
effects. You can do this by passing an array to the conversion_name parameter.

<pre>
breed_new_animal = ab_test("breed new animal", conversion_name=["animals escaped", "talking animals"])
</pre>

This syntactic sugar will automatically create multiple experiments for you.
Your conversions will be tracked independently with their own statistical
analysis, so you can independently call bingo() when appropriate:

<pre>
bingo("animals escaped")
</pre>

...and...

<pre>
bingo("talking animals")
</pre>

## <a name="principles">Design Principles</a>

Just go read through [Patrick McKenzie's slides on A/B testing design principles](http://www.bingocardcreator.com/abingo/design). This implementation only tweaks those to achieve:

* Persistence to datastore for very-long-lasting records and very-long-running
  experiments without sacrificing performance.
* Quick to drop-in for any App Engine (Python) developer, with
  strong-but-customizable ties to existing App Engine user identities.

## <a name="start">Getting Started</a>

## <a name="non-features">Non-features (well, some of them)</a>

In order to get v1 out the door, a number of features were cut. Please feel
free to help us accomplish the following:

* Multivariate statistical analysis -- currently we only automatically analyze
  experiments w/ exactly 2 alternatives.
* Multiple participation in experiments -- currently each user is only counted
  once per experiment.
* Nicer bot detection -- we took the cheap and quick route of checking user
  agents for bots even thought testing for javascript execution is much more
  effective. This shouldn't screw w/ your statistical analysis, conversions
  look rarer than they actually are due to bots getting through the filter.

## <a name="bonus">Bonus</a>

GAE/Bingo is currently in production use at Khan Academy (http://khanacademy.org). If you make good use of it elsewhere, be sure to let us know so we can brag about you to others (ben@khanacademy.org).

## <a name="faq">FAQ</a>

1. Would you have been able to build any of this without [A/Bingo](http://www.bingocardcreator.com/abingo)'s lead to
   follow?

    Nope.

2. Shouldn't I just be using Google Website Optimizer or some other
   javascript-powered A/B testing framework?

    [I'll let Patrick handle this one](http://www.bingocardcreator.com/abingo/compare).

3. How come you didn't just use one of the existing Python split testing
   frameworks like django-lean?

    django-lean is awesome, but we strongly believe in a couple of the core
    principles of A/Bingo, particularly making it as ridiculously easy as
    possible for developers (and anybody else) to create A/B tests.

    We also wanted this to quickly drop into any App Engine app, and we didn't want to
    exclude those on App Engine who aren't using Django.

4. Can I use this framework for my app/client/iguana website?

    It's all yours.
