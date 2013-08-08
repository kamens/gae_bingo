var GAEDashboard = {

    archives: false,

    chartOptions: {
        credits: {
            enabled: false
        },
        title: {
            text: ""
        },
        xAxis: {
            type: "datetime"
        },
        plotOptions: {
            series: {
                marker: {
                    enabled: false,
                    states: {
                        hover: {
                            enabled: true
                        }
                    }
                }
            }
        },
        tooltip: {
            crosshairs: [true, true],
            shared: true
        },
        global: {
            useUTC: false
        }
    },

    /**
     * Initialize the dashboard by loading all experiments and rendering the
     * main experiment list. If we're viewing the archive page, only render
     * archived experiments.
     */
    init: function() {

        // Start/stop throbber when any ajax request starts/stops.
        $(document)
            .ajaxSend(GAEDashboard.showThrobber)
            .ajaxComplete(GAEDashboard.hideThrobber);

        // TODO(kamens): replace href detection w/ backbone & router
        this.archives = window.location.href.indexOf("/archives") > 0;
        if (this.archives) {
            $(".nav-archives").addClass("active");
        } else {
            $(".nav-experiments").addClass("active");
        }

        Highcharts.setOptions(this.chartOptions);

        this.loadExperiments();
    },

    /**
     * Load all experiments and render main list.
     */
    loadExperiments: function() {

        $.ajax({
            url: "/gae_bingo/api/v1/experiments",
            dataType: "json",
            type: "GET",
            data: {
                archives: this.archives ? 1 : 0
            },
            success: function(data) {

                $("#progress-bar").css("visibility", "hidden");

                $("#main").append($("#tmpl-experiments").handlebars(data));
                GAEDashboard.updateControls();

                // Attach click handlers for expanding individual experiments
                $("#main").on("click", ".experiment-container-minimized", function(e) {
                    // Start loading the summary for this experiment.
                    GAEDashboard.loadExperimentSummary($(this).data("canonical-name"));

                    // Connect all events for controlling this experiment (such
                    // as starting, stopping, archiving, and deleting).
                    $(this)
                        .removeClass("experiment-container-minimized")
                        .find("button.disabled")
                            .removeClass("disabled")
                            .end()
                        .find(".refresh-conversion")
                            .click(function(e) {
                                var expt = $(this)
                                    .closest("div.experiment-container")
                                        .find(".active .conversions-link")
                                        .data("experiment-name");
                                GAEDashboard
                                    .loadConversionsContent(expt, true);
                            })
                            .end()
                        .find(".control-experiment")
                            .click(function(e) {

                                e.preventDefault();

                                var stopping = $(this).is(".stop-experiment"),
                                    starting = $(this).is(".start-experiment"),
                                    archiving = $(this).is(".archive-experiment"),
                                    deleting = $(this).is(".delete-experiment"),
                                    alternativeNumber = $(this).data("alternative-number"),
                                    canonicalName = $(this).data("canonical-name"),
                                    confirmation = null;

                                if (stopping) {
                                    confirmation = "Are you sure you want to " + $.trim($(this).text()).toLowerCase() + "?" +
                                        "\n\nYou can always resume this experiment later.";
                                }

                                if (archiving) {
                                    if ($(this).is(".active")) {
                                        return false;
                                    }

                                    confirmation = "Are you sure you want to archive this experiment? " +
                                        "If your code tries to run this experiment again, it will create a new experiment." +
                                        "\n\n*** YOU CANNOT UNARCHIVE AN EXPERIMENT, you can only start a brand new one. ***";
                                }

                                if (deleting) {
                                    confirmation = "Are you sure you want to permanently delete this experiment? " +
                                        "\n\n*** This experiment and its data will be deleted forever. Have you considered archiving? ***";
                                }

                                if (confirmation) {
                                    if (!confirm(confirmation)) {
                                        return false;
                                    }
                                }

                                $(this)
                                    .closest("div.experiment-container")
                                        .toggleClass("not-live", !starting)
                                        .toggleClass("archived", archiving)
                                        .find("textarea")
                                            .focus()
                                            .end()
                                        .find(".seeing-alternative")
                                            .css("display", "none");

                                if (stopping) {
                                    $(this)
                                        .closest("ul")
                                            .prev("button")
                                                .button("toggle")
                                                .end()
                                            .end()
                                        .closest("div.experiment-container")
                                            .find(".seeing-alternative[data-alternative-number=\"" + alternativeNumber + "\"]")
                                                .css("display", "inline");
                                }

                                if (archiving) {
                                    $(this)
                                        .closest(".experiment-controls")
                                            .find(".btn")
                                                .not(".archive-experiment")
                                                    .remove();
                                }

                                if (deleting) {
                                    $(this)
                                        .closest("div.experiment-container")
                                            .slideUp();
                                }

                                $.ajax({
                                    url: "/gae_bingo/api/v1/experiments/control",
                                    data: {
                                        archives: GAEDashboard.archives ? 1 : 0,
                                        canonical_name: canonicalName,
                                        alternative_number: alternativeNumber,
                                        action: $(this).data("action")
                                    },
                                    dataType: "json",
                                    type: "POST",
                                    error: function(jqXHR, textStatus, errorThrown) {
                                        alert("Something went wrong. You should probably reload and try again.");
                                    }
                                });

                                _.defer(GAEDashboard.updateControls);
                            })
                            .end()
                        .find(".experiment-summary-content")
                            .empty()
                            .append($("#progress-bar").clone().css("visibility", "visible"))
                            .animate({height: 250}, 250);

                    e.preventDefault();
                }).on("click", ".experiment-container:not(.experiment-container-minimized) h2", function(e) {
                    // close the experiment
                    $(this).closest(".experiment-container")
                        .addClass("experiment-container-minimized")
                        .find(".control-experiment")
                            .addClass("disabled")
                            .end()
                        .find(".experiment-summary-content")
                            .css("min-height", "")
                            .css("overflow", "hidden")
                            .animate({ height: 0 }, 250);

                    e.preventDefault();
                });
            }
        });
    },

    /**
     * Load summary information for an individual experiment. Summaries contain
     * the names of all metrics/experiments included in the canonical
     * experiment.
     */
    loadExperimentSummary: function(canonicalName) {

        $.ajax({
            url: "/gae_bingo/api/v1/experiments/summary",
            data: {
                canonical_name: canonicalName,
                archives: this.archives ? 1 : 0
            },
            dataType: "json",
            type: "GET",
            success: function(dataSummary) {

                var jel = $("div.experiment-container[data-canonical-name=\"" + dataSummary.canonical_name + "\"] .experiment-summary-content");
                jel
                    .css("min-height", jel.height())
                    .stop()
                    .css("height", "")
                    .html($("#tmpl-experiment-summary").handlebars(dataSummary))
                    .find(".notes-content")
                        .val(dataSummary.notes)
                        .end()
                    .find(".emo")
                        .each(function() {
                            if ($.inArray($(this).val(), dataSummary.emotions) != -1) {
                                $(this).button("toggle");
                            }
                        })
                        .end()
                    .find(".save-notes")
                        .click(function(e) {
                            e.preventDefault();

                            if ($(this).is(".disabled")) {
                                return;
                            }

                            $(this).addClass("disabled").text("Saving...");
                            GAEDashboard.saveNotes($(this).data("canonical-name"));
                        })
                        .end()
                    .on("click", ".set-control", function(e) {
                        GAEDashboard.controlIndices[canonicalName] =
                            $(e.target).val();
                        var expt = jel.find(".active .conversions-link")
                                      .data("experiment-name");
                        GAEDashboard.renderConversions(expt);
                    })
                    .find("a.conversions-link")
                        .click(function(e) {

                            e.preventDefault();

                            $(this)
                                .parents("ul")
                                    .find(".active")
                                        .removeClass("active")
                                        .end()
                                    .end()
                                .closest("div.experiment-container")
                                    .css("min-height", function() { return $(this).height(); })
                                    .find("div.experiment-conversions-content")
                                        .empty()
                                        .append($("#progress-bar").clone().css("visibility", "visible"))
                                        .end()
                                    .end()
                                .parents("li")
                                    .addClass("active")
                                    .end();

                            GAEDashboard.loadConversionsContent($(this).data("experiment-name"));

                        })
                        .first()
                            .click();
            }
        });
    },

    setCookie: function(canonicalName, alternativeNumber, expiryDays) {
        var expiryDate = new Date();
        expiryDate.setDate(expiryDate.getDate() + expiryDays);
        var cookieValue = escape(alternativeNumber);
        if (expiryDays !== null) {
            cookieValue = cookieValue + "; expires=" + expiryDate.toUTCString();
        }
        cookieValue = cookieValue + "; path=/";
        document.cookie = "GAEBingo_" + canonicalName.replace(/\W/g, "+") + "=" + cookieValue;
    },

    readCookie: function(canonicalName) {
        var nameEQ = "GAEBingo_" + canonicalName.replace(/\W/g, "+") + "=";
        var ca = document.cookie.split(";");
        for (var i = 0; i < ca.length; i++) {
            var c = ca[i];
            while (c.charAt(0) == " ") {
                c = c.substring(1, c.length);
            }
            if (c.indexOf(nameEQ) === 0) {
                return c.substring(nameEQ.length, c.length);
            }
        }
        return null;
    },

    eraseCookie: function(canonicalName) {
        this.setCookie(canonicalName, "", -1);
    },

    /**
     * Update the on/off state of each "preview this" button for every
     * experiment alternative.
     */
    updatePreviewButtons: function(hashableName) {
        var currentAltNum = GAEDashboard.readCookie(hashableName);

        // Find all preview buttons corresponding to a hashable family name,
        // which could include preview buttons from multiple experiment
        // containers if the experiments share a family name. Then update the
        // preview buttons in all these relevant experiments.
        $(".preview-alternative[data-hashable-name=\"" + hashableName + "\"]")
            .closest("div.experiment-container")
                .find(".preview-alternative")
                    .each(function(el) {
                        var previewAltNum = $(this).data("alternative-number");
                        if (currentAltNum == previewAltNum) {
                            $(this)
                                .text("Previewing")
                                .addClass("active");
                        } else {
                            $(this)
                                .text("Preview this")
                                .removeClass("active");
                        }
                    });
    },

    /**
     * Update the on/off state of each Running/Stopped/Archived button for
     * every experiment.
     */
    updateControls: function() {
        $(".experiment-controls .btn")
            .each(function(el) {
                var jel = $(this);
                if (jel.is(".active")) {
                    jel.addClass(jel.data("active-cls"));
                } else {
                    jel.removeClass(jel.data("active-cls"));
                }
            });
    },

    /**
     * Save the user's input as notes for a specific archived experiment.
     */
    saveNotes: function(canonicalName) {

        var container = $("div.experiment-container[data-canonical-name=\"" + canonicalName + "\"]"),
            button = container.find(".save-notes"),
            notes = container.find(".notes-content"),
            emotions = container.find(".emo.active");

        $.ajax({
            url: "/gae_bingo/api/v1/experiments/notes",
            data: {
                canonical_name: canonicalName,
                notes: notes.val(),
                emotions: $.map(emotions, function(emotion) {
                    return $(emotion).val();
                }),
                archives: 1
            },
            dataType: "json",
            type: "POST",
            success: function(data) {

                button.text("Saved!");
                _.delay(function() {
                    button
                        .removeClass("disabled")
                        .text("Save notes and emotions");
                }, 2000);
            }
        });
    },

    /**
     * Map of experimentName to massaged conversion data.
     */
    conversionData: {},

    /**
     * Guess which alternative is the control, and return the index.
     *
     * Checks if any of the names sound control-like. If no reasonable guess can
     * be made, assumes the first on is the control and returns 0.
     *
     * @param  {Array} alternatives
     * @return {int} The index for the control
     */
    inferControl: function(alternatives) {
        var controlWords = ["old", "original", "false", "control"];

        for (var i = 0; i < alternatives.length; i++) {
            var isControl = _.any(controlWords, function(cw) {
                return String(alternatives[i].content).indexOf(cw) > -1;
            });
            if (isControl) {
                return i;
            }
        }
        return 0;
    },

    /**
     * Map of canonical name to control index.
     */
    controlIndices: {},

    handleConversionDataLoad: function(data) {
        var assignControl = function(data) {
            _.each(data.alternatives, function(alternative) {
                alternative["control"] = false;
            });
            var controlIndex = GAEDashboard.controlIndices[data.canonical_name];
            var control = data.alternatives[controlIndex];
            control["control"] = true;
            return control;
        };

        var control = assignControl(data);

        // Find conversation rate relative difference to control.
        var conversionRateControl = control["conversion_rate"];
        _.each(data.alternatives, function(alternative) {
            if (alternative["control"]) {
                alternative["relative_rate"] = "";
                return;
            }

            if (conversionRateControl > 0) {
                var relativeRate =
                    (alternative["conversion_rate"] - conversionRateControl) /
                    conversionRateControl;
                // Be explicit and put a leading "+" for positive values.
                alternative["relative_rate"] =
                    (relativeRate > 0 ? "▲" : "▼") +
                    Math.abs(relativeRate * 100).toFixed(2) +
                    " %";

                var clamp = function(val, min, max) {
                    return Math.min(max, Math.max(min, val));
                };
                var red = Math.round(
                        -clamp(relativeRate * 100, -25, 0) * 255 / 25);
                var green = Math.round(
                        clamp(relativeRate * 100, 0, 25) * 255 / 25);
                alternative["relative_rate_style"] = "color: rgb(" +
                        red + "," + green + ", 0);";
            } else {
                alternative["relative_rate"] = "N/A";
            }
        });

        // Find significance relative to control
        _.each(data.alternatives, function(alt) {
            if (alt["control"]) {
                alt["p_value"] = "";
                return;
            }

            var pValueStr = function(p) {
                return _.find([
                    ["< 0.1%", 0.001],
                    ["< 1%", 0.01],
                    ["< 5%", 0.05],
                    ["< 10%", 0.1],
                    ["> 10%", 1.0/0]
                ], function(row) {
                    return p < row[1];
                })[0];
            };

            var z = this.zscore(
                    control.conversion_rate, alt.conversion_rate,
                    control.participants, alt.participants);
            if (z != null) {
                var p = 1 - Stats.normalcdf(Math.abs(z));
                alt["p_value"] = pValueStr(p);
            }
        }, this);
    },

    renderTable: function(data) {
        var renderChart = _(this.renderChart).bind(this, data);

        $("div.experiment-container[data-canonical-name=\"" + data.canonical_name + "\"]")
            .css("min-height", "")
            .find("div.experiment-conversions-content")
                .html($("#tmpl-experiment-conversions-content").handlebars(data))
                .end()
            .find(".seeing-alternative[data-alternative-number=\"" + data.short_circuit_number + "\"]")
                .css("display", "inline")
                .end()
            .find(".preview-alternative")
                .click(function(e) {
                    var alternativeNum = GAEDashboard.readCookie($(this).data("hashable-name"));
                    if (alternativeNum == $(this).data("alternative-number")) {
                        GAEDashboard.eraseCookie($(this).data("hashable-name"));
                    } else {
                        GAEDashboard.setCookie($(this).data("hashable-name"), $(this).data("alternative-number"), 365);
                    }
                    GAEDashboard.updatePreviewButtons(data.hashable_name);
                })
                .end()
            .on("click", "a.conversions",
                _.partial(renderChart, this.conversionsChart))
            .on("click", "a.participants",
                _.partial(renderChart, this.participantsChart))
            .on("click", "a.pval",
                _.partial(renderChart, this.pValueChart));

        GAEDashboard.updatePreviewButtons(data.hashable_name);
    },

    /**
     * Renders the graphs of the conversions for the given experiment.
     */
    renderConversions: function(experimentName) {
        var data = this.conversionData[experimentName];
        GAEDashboard.handleConversionDataLoad(data);
        GAEDashboard.renderTable(data);
        GAEDashboard.renderChart(data, this.conversionsChart);
    },

    /**
     * Load historical participation/conversion data for a specific experiment
     * or metric.
     */
    loadConversionsContent: function(experimentName, force) {
        if (!force && this.conversionData[experimentName]) {
            this.renderConversions(experimentName);
            return;
        }

        $.ajax({
            type: "GET",
            url: "/gae_bingo/api/v1/experiments/conversions",
            data: {
                experiment_name: experimentName,
                archives: this.archives ? 1 : 0
            },
            dataType: "json",
        }).then(_.bind(this.receivedConversionsData, this, experimentName));
    },

    receivedConversionsData: function(experimentName, data) {
        // save the data
        this.conversionData[experimentName] = data;
        if (this.controlIndices[data.canonical_name] == null) {
            this.controlIndices[data.canonical_name] = this.inferControl(
                data.alternatives);
        }

        // To display tooltips correctly on a datetime axis, highcharts needs
        // the data sorted by ascending datetime.
        _.each(data.timeline_series, function(series) {
            series.data = _.sortBy(series.data, function(x) {
                return x[0];
            });
        });

        this.renderConversions(experimentName);
    },

    showThrobber: function() {
        $(".throbber").show();
    },

    hideThrobber: function() {
        $(".throbber").hide();
    },

    /**
     * Map of canonical name to HighCharts instance. Used to destroy charts.
     * @type {Object}
     */
    charts: {},

    renderChart: function(data, chartFn) {
        if (!(data && data.timeline_series.length)) {
            return;
        }

        var chart = this.charts[data.canonical_name];
        if (chart) {
            chart.destroy();
        }

        this.charts[data.canonical_name] = chartFn.call(this, data);
    },

    conversionsChart: function(data) {
        var conversionData = _.map(data.timeline_series, function(series) {
            return {
                name: series.name,
                data: _.map(series.data, function(x) {
                    var date = x[0];
                    var participants = x[1];
                    var conversions = x[2];
                    var rate = conversions / participants * 100 || 0;
                    return [date, rate];
                })
            };
        });

        return new Highcharts.Chart({
            chart: {
                renderTo: "highchart-" + data.canonical_name,
                type: "spline",
                zoomType: "xy"
            },
            yAxis: {
                title: {
                  text: "Conversions"
                },
                labels: {
                    format: "{value}%"
                }
            },
            series: conversionData,
            tooltip: {
                valueDecimals: 1,
                valueSuffix: "%"
            }
        });
    },

    participantsChart: function(data) {
        return new Highcharts.Chart({
            chart: {
                renderTo: "highchart-" + data.canonical_name,
                type: "spline",
                zoomType: "xy"
            },
            yAxis: {
                title: {
                  text: "Participants"
                }
            },
            series: data.timeline_series,
        });
    },

    pValueChart: function(data) {
        var controlIndex = this.controlIndices[data.canonical_name];
        var control = data.alternatives[controlIndex];
        var controlSeries = _.findWhere(
            data.timeline_series, {"name": control.pretty_content});

        var pdata = []
        _.each(data.timeline_series, function(series) {
            if (controlSeries.name === series.name) {
                return;
            }
            pdata.push({
                name: series.name,
                data: _.map(_.zip(controlSeries.data, series.data),
                    function(a) {
                        var c = a[0], t = a[1];

                        var ccr = c[2]/c[1];
                        var tcr = t[2]/t[1];
                        var z = this.zscore(ccr, tcr, c[1], t[1]);
                        var p = 1 - Stats.normalcdf(Math.abs(z));
                        return [t[0], p * 100];
                    }, this)
            });
        }, this);

        return new Highcharts.Chart({
            chart: {
                renderTo: "highchart-" + data.canonical_name,
                type: "spline",
                zoomType: "xy"
            },
            yAxis: {
                title: {
                  text: "p-value"
                },
                type: "logarithmic",
                labels: {
                    format: "{value}%"
                },
                // we have are log axis, so there are powers of 10, not raw:
                tickPositions: [
                    Math.log(0.05)/Math.log(10),
                    -1,
                    0,
                    Math.log(5)/Math.log(10),
                    1,
                    2
                ]
            },
            tooltip: {
                valueDecimals: 1,
                valueSuffix: "%"
            },
            series: pdata,
        });
    },

    zscore: function(crc, crt, nc, nt) {
        if (nc === 0 || nt === 0) {
            return null;
        }

        var varc = crc * (1 - crc) / nc;
        var vart = crt * (1 - crt) / nt;
        var variance = varc + vart;

        if (variance === 0) {
            return 0;
        } else if (variance < 0) {
            return null;
        }

        return (crc - crt) / Math.sqrt(variance);
    }
};

window.Stats = (function() {
    // from http://stackoverflow.com/a/14873282/3829
    var erf = function(x) {
        // save the sign of x
        var sign = (x >= 0) ? 1 : -1;
        x = Math.abs(x);

        // constants
        var a1 =  0.254829592;
        var a2 = -0.284496736;
        var a3 =  1.421413741;
        var a4 = -1.453152027;
        var a5 =  1.061405429;
        var p  =  0.3275911;

        // A&S formula 7.1.26
        var t = 1.0/(1.0 + p*x);
        var y = 1.0 - (((((a5 * t + a4) * t) + a3) * t + a2) * t + a1) * t * Math.exp(-x * x);
        return sign * y; // erf(-x) = -erf(x);
    };

    var cdf = function(x, mean, variance) {
        return 0.5 * (1 + erf((x - mean) / (Math.sqrt(2 * variance))));
    }

    var normalcdf =  function(z) {
        return cdf(z, 0, 1);
    }

    return {
        erf: erf,
        cdf: cdf,
        normalcdf: normalcdf
    }
})();

$(function(){ GAEDashboard.init(); });
