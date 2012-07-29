var GAEDashboard = {

    archives: false,

    /**
     * Initialize the dashboard by loading all experiments and rendering the
     * main experiment list. If we're viewing the archive page, only render
     * archived experiments.
     */
    init: function() {
        // TODO(kamens): replace href detection w/ backbone & router
        this.archives = window.location.href.indexOf("/archives") > 0;
        if (this.archives) {
            $(".nav-archives").addClass("active");
        } else {
            $(".nav-experiments").addClass("active");
        }

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
                $("#main .experiment-container-minimized").click(function(e) {

                    if (!$(this).is(".experiment-container-minimized")) {
                        // Already expanded
                        return;
                    }

                    // Start loading the summary for this experiment.
                    GAEDashboard.loadExperimentSummary($(this).data("canonical-name"));

                    // Connect all events for controlling this experiment (such
                    // as starting, stopping, archiving, and deleting).
                    $(this)
                        .removeClass("experiment-container-minimized")
                        .find("button.disabled")
                            .removeClass("disabled")
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
                                    .parents("div.experiment-container")
                                        .toggleClass("not-live", !starting)
                                        .toggleClass("archived", archiving)
                                        .find("textarea")
                                            .focus()
                                            .end()
                                        .find(".seeing-alternative")
                                            .css("display", "none");

                                if (stopping) {
                                    $(this)
                                        .parents("ul")
                                            .prev("button")
                                                .button("toggle")
                                                .end()
                                            .end()
                                        .parents("div.experiment-container")
                                            .find(".seeing-alternative[data-alternative-number=\"" + alternativeNumber + "\"]")
                                                .css("display", "inline");
                                }

                                if (archiving) {
                                    $(this)
                                        .parents(".experiment-controls")
                                            .find(".btn")
                                                .not(".archive-experiment")
                                                    .remove();
                                }

                                if (deleting) {
                                    $(this)
                                        .parents("div.experiment-container")
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
                                    complete: function(data, a, b) {
                                    },
                                    error: function(jqXHR, textStatus, errorThrown) {
                                        alert("Something went wrong. You should probably reload and try again.");
                                    }
                                });

                                setTimeout(function() {
                                    GAEDashboard.updateControls();
                                }, 1);
                            })
                            .end()
                        .find(".experiment-summary-content")
                            .empty()
                            .append($("#progress-bar").clone().css("visibility", "visible"))
                            .animate({height: 250}, 250);

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
                    .find("a.conversions-link")
                        .click(function(e) {

                            e.preventDefault();

                            GAEDashboard.loadConversionsContent($(this).data("experiment-name"));

                            $(this)
                                .parents("ul")
                                    .find(".active")
                                        .removeClass("active")
                                        .end()
                                    .end()
                                .parents("div.experiment-container")
                                    .css("min-height", function() { return $(this).height(); })
                                    .find("div.experiment-conversions-content")
                                        .empty()
                                        .append($("#progress-bar").clone().css("visibility", "visible"))
                                        .end()
                                    .end()
                                .parents("li")
                                    .addClass("active")
                                    .end();

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
    updatePreviewButtons: function(canonicalName) {
        $("div.experiment-container[data-canonical-name=\"" + canonicalName + "\"]")
            .find(".preview-alternative")
                .each(function(el) {
                    alternativeNum = GAEDashboard.readCookie(canonicalName);
                    if (alternativeNum == $(this).data("alternative-number")) {
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
                setTimeout(function() {
                    button
                        .removeClass("disabled")
                        .text("Save notes and emotions");
                }, 2000);
            }
        });
    },

    /**
     * Load historical participation/conversion data for a specific experiment
     * or metric.
     */
    loadConversionsContent: function(experimentName) {
        $.ajax({
            url: "/gae_bingo/api/v1/experiments/conversions",
            data: {
                experiment_name: experimentName,
                archives: this.archives ? 1 : 0
            },
            dataType: "json",
            type: "GET",
            success: function(data) {

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
                            alternativeNum = GAEDashboard.readCookie($(this).data("canonical-name"));
                            if (alternativeNum == $(this).data("alternative-number")) {
                                GAEDashboard.eraseCookie($(this).data("canonical-name"));
                            } else {
                                GAEDashboard.setCookie($(this).data("canonical-name"), $(this).data("alternative-number"), 365);
                            }
                            GAEDashboard.updatePreviewButtons(data.canonical_name);
                        })
                        .end();

                GAEDashboard.updatePreviewButtons(data.canonical_name);
                GAEDashboard.renderHighchart(data);

            }
        });
    },

    /**
     * Render the chart of historical conversions snapshots.
     */
    renderHighchart: function(data) {

        if (!data.timeline_series.length) {
            return;
        }

        Highcharts.setOptions({
            global: {
                useUTC: false
            }
        });

        var chart = new Highcharts.Chart({
          chart: {
             renderTo: "highchart-" + data.canonical_name,
             type: "spline"
          },
          credits: {
              enabled: false
          },
          title: {
            text: ""
          },
          xAxis: {
             type: "datetime"
          },
          yAxis: {
             title: {
                text: data.y_axis_title
             },
             min: 0
          },
          series: data.timeline_series
        });
    }

};

$(function(){ GAEDashboard.init(); });
