import logging

# This file in particular is almost a direct port from Patrick McKenzie's A/Bingo's abingo/lib/abingo/statistics.rb

HANDY_Z_SCORE_CHEATSHEET = [[0.10, 1.29], [0.05, 1.65], [0.01, 2.33], [0.001, 3.08]]

PERCENTAGES = {0.10: '90%', 0.05: '95%', 0.01: '99%', 0.001: '99.9%'}

DESCRIPTION_IN_WORDS = {
        0.10: 'fairly confident', 0.05: 'confident',
        0.01: 'very confident', 0.001: 'extremely confident'
        }

def zscore(alternatives):

    if len(alternatives) != 2:
        raise Exception("Sorry, can't currently automatically calculate statistics for A/B tests with > 2 alternatives. Need to brush up on some statistics via http://www.khanacademy.org/#statistics before implementing.")

    if alternatives[0].participants == 0 or alternatives[1].participants == 0:
        raise Exception("Can't calculate the z score if either of the alternatives lacks participants.")

    cr1 = alternatives[0].conversion_rate
    cr2 = alternatives[1].conversion_rate

    n1 = alternatives[0].participants
    n2 = alternatives[1].participants

    numerator = cr1 - cr2
    frac1 = cr1 * (1 - cr1) / float(n1)
    frac2 = cr2 * (1 - cr2) / float(n2)

    if frac1 + frac2 == 0:
        return 0
    elif frac1 + frac2 < 0:
        raise Exception("At the moment we can't calculate the z score of experiments that allow multiple conversions per participant.")

    return numerator / float((frac1 + frac2) ** 0.5)

def p_value(alternatives):

    index = 0
    z = zscore(alternatives)
    z = abs(z)

    found_p = None
    while index < len(HANDY_Z_SCORE_CHEATSHEET):
        if z > HANDY_Z_SCORE_CHEATSHEET[index][1]:
            found_p = HANDY_Z_SCORE_CHEATSHEET[index][0]
        index += 1

    return found_p

def is_statistically_significant(p = 0.05):
    return p_value <= p

def describe_result_in_words(alternatives):

    try:
        z = zscore(alternatives)
    except Exception, e:
        return str(e)

    p = p_value(alternatives)

    words = ""

    if alternatives[0].participants < 10 or alternatives[1].participants < 10:
        words += "Take these results with a grain of salt since your samples are so small: "

    best_alternative = max(alternatives, key=lambda alternative: alternative.conversion_rate)
    worst_alternative = min(alternatives, key=lambda alternative: alternative.conversion_rate)

    words += """The best alternative you have is: [%(best_alternative_content)s], which had 
    %(best_alternative_conversions)s conversions from %(best_alternative_participants)s participants 
    (%(best_alternative_pretty_conversion_rate)s).  The other alternative was [%(worst_alternative_content)s], 
    which had %(worst_alternative_conversions)s conversions from %(worst_alternative_participants)s participants 
    (%(worst_alternative_pretty_conversion_rate)s).  """ % {
                "best_alternative_content": best_alternative.content,
                "best_alternative_conversions": best_alternative.conversions,
                "best_alternative_participants": best_alternative.participants,
                "best_alternative_pretty_conversion_rate": best_alternative.pretty_conversion_rate,
                "worst_alternative_content": worst_alternative.content,
                "worst_alternative_conversions": worst_alternative.conversions,
                "worst_alternative_participants": worst_alternative.participants,
                "worst_alternative_pretty_conversion_rate": worst_alternative.pretty_conversion_rate,
            }

    if p is None:
        words += "However, this difference is not statistically significant."
    else:
        words += """This difference is %(percentage_likelihood)s likely to be statistically significant, which means you can be 
        %(description)s that it is the result of your alternatives actually mattering, rather than 
        being due to random chance.  However, this statistical test can't measure how likely the currently 
        observed magnitude of the difference is to be accurate or not.  It only says "better," not "better 
        by so much.\"""" % {
                    "percentage_likelihood": PERCENTAGES[p],
                    "description": DESCRIPTION_IN_WORDS[p],
                }

    return words

