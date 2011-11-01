var GAEDashboard = {
    
    loadExperiments: function() {
        $.ajax({
            url: "/gae_bingo/api/v1/experiments",
            dataType: "json",
            type: "GET",
            success: function(data) {

                $("#progress-bar").css("visibility", "hidden");

                $( "#main" ).append( $("#tmpl-experiments").mustache(data) );
                $( "#main .experiment-container-minimized" ).click( function(e) {

                    if (!$(this).is(".experiment-container-minimized")) {
                        // Already expanded
                        return;
                    }

                    GAEDashboard.loadExperimentSummary( $(this).data( "canonical-name" ) );

                    $(this)
                        .removeClass("experiment-container-minimized")
                        .find(".experiment-summary-content")
                            .empty()
                            .append($("#progress-bar").clone().css("visibility", "visible"))
                            .animate({height: 250}, 250);

                    e.preventDefault();

                });
            }
        });
    },

    loadExperimentSummary: function(canonicalName) {
        $.ajax({
            url: "/gae_bingo/api/v1/experiments/summary",
            data: { canonical_name: canonicalName },
            dataType: "json",
            type: "GET",
            success: function(dataSummary) {
                var jel = $( "div.experiment-container[data-canonical-name=\"" + dataSummary.canonical_name + "\"] .experiment-summary-content" );
                jel
                    .css("min-height", jel.height())
                    .stop()
                    .css("height", "")
                    .html( $( "#tmpl-experiment-summary" ).mustache( dataSummary ) )
                    .find( "a.conversions-link" )
                        .click(function(e) {

                            GAEDashboard.loadConversionsContent( $(this).data( "experiment-name" ) );

                            $(this)
                                .parents("ul.wat-cf")
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
                                .parent()
                                    .addClass("active")
                                    .end()

                            e.preventDefault();

                        })
                        .first()
                            .click();
            }
        });
    },

    loadConversionsContent: function(experimentName) {
        $.ajax({
            url: "/gae_bingo/api/v1/experiments/conversions",
            data: { experiment_name: experimentName },
            dataType: "json",
            type: "GET",
            success: function(data) {

                $( "div.experiment-container[data-canonical-name=\"" + data.canonical_name + "\"]")
                    .css("min-height", "")
                    .find( "div.experiment-conversions-content" )
                        .html( $("#tmpl-experiment-conversions-content").mustache( data ) )
                        .end()
                    .find( ".control-experiment" )
                        .click(function(e) {

                            e.preventDefault();

                            if ($(this).is(".end-experiment")) {
                                if (!confirm("Are you sure you want to end this experiment and choose alternative #" + $(this).data("alternative-number") + "?" +
                                                "\n\n***If you have multiple experiments running with the same experiment name, " +
                                                "you will end and choose this alternative for all of them. You can always resume this experiment later.***")) {
                                    return;
                                }
                            }

                            $.ajax({
                                url: "/gae_bingo/api/v1/experiments/control",
                                data: {
                                    canonical_name: $(this).data("canonical-name"),
                                    alternative_number: $(this).data("alternative-number"),
                                    action: $(this).val()
                                },
                                dataType: "json",
                                type: "POST",
                                complete: function(data) {
                                    window.location.reload();
                                }
                            });

                            $(this).replaceWith($(this).data("replace-with"));

                        });

                GAEDashboard.renderHighchart(data);

            }
        });
    },

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
             renderTo: 'highchart-' + data.canonical_name,
             type: 'spline'
          },
          credits: {
              enabled: false
          },
          title: {
            text: ''
          },
          xAxis: {
             type: 'datetime'
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

}

$(GAEDashboard.loadExperiments);
