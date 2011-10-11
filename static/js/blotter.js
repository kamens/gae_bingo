// Blotter is a js library for client-side interaction with gae_bingo
// the only hard requirement is jquery 1.5+
// 
// because JSON.stringify is still not widely supported, consider including
// json2.js from https://github.com/douglascrockford/JSON-js 
// if it's not found, it will ab_test will be read-only.

// Blotter is available on the dashboard page if you open a console and want
// to test it out.

// Example usage
/*
    // score a conversion
    Blotter.bingo( "mario_yay" )

    // create a new a/b test split 90/10 with three possible conversions
    Blotter.ab_test( "mario points", { "on" : 90, "off" : 10 }, [ "mario_yay", "mario_boo", "mario_indifferent" ] )

    // check user's status in a test
    Blotter.ab_test( "mario points", null, null, function( d ) { console.log( d ); } )

    // see all tests requested so far
    Blotter.tests
    // ==> returns { "mario points" : "on" }

    // you can specify default callbacks
    Blotter.init({
      success : function( d, ts, jqx ) { console.log( "woo!", d ); },
      error : function( jqx, ts, e ) { console.error( "nuts", jqx )}
    })

    // if you're just playing around, there are some console-friendly defaults available
    // which you can access by defining debug as an init parameter
    Blotter.init( { "debug" : true } )

*/
 
var Blotter = (function() {
  var path = "/gae_bingo/blotter";

  var defaultSuccess = $.noop;
  var defaultError = $.noop;

  var tests = {};

  // init takes a spec object which is totally optional,
  // you can define the following properties on it
  // * path (string) : the path to gae_bingo/blotter
  // * success (function) : a jQuery ajax succes callback like:
  //   function(data, textStatus, jqXHR){ ... }
  // * error (function) : a jQuery ajax error callback like:
  //   function(jqXHR, textStatus, errorThrown){ ... }
  // * debug : if debug is defined, defaultError and defaultSuccess 
  //   are set to console.log/error the result of a query
  var init = function( spec ) {
    spec = (typeof spec === "undefined") ? {} : spec;
    
    path = spec.path || path;
    
    defaultSuccess = (spec.success !== undefined) ? spec.success : defaultSuccess;
    defaultError = (spec.error !== undefined) ? spec.error : defaultError;
    
    // set debugging console-callbacks if spec.debug set
    defaultSuccess = (spec.debug === undefined) ? defaultSuccess :
      function( d, ts, jx) { console.log( "blotter success(" + jx.status + "):", d ); };
    defaultError = (spec.debug === undefined) ? defaultError :
      function( jx, ts ) { console.error( "blotter error (" + jx.status + "):", jx ); };
  };

  // ab_test takes a testName which is the name of a given ab_test
  // alt
  var ab_test = function( canonical_name, alternative_params, conversion_name, successCallback, errorCallback ) {
    // set defaults for callbacks
    errorCallback = errorCallback || defaultError;
    successCallback = successCallback || defaultSuccess;

    // don't init ab tests on browsers without JSON support
    var stringify = JSON.stringify || $.noop;

    var testdata = { 
      "canonical_name" : canonical_name,
      "alternative_params" : stringify(alternative_params),
      "conversion_name" : stringify(conversion_name)
    };

    jQuery.ajax({
      type: "POST",
      url: path,
      data : testdata,
      success : function(d, ts, jx) { 
        tests[canonical_name] = d; 
        successCallback( d, ts, jx);
      },
      error : errorCallback
    });
  };

  // convert calls a bingo. on success, no data is returned but successCallback is fired anyway
  // on failure (no experiment found for conversion name) errorCallback is fired
  // successCallback is called even if a bingo has already been recorded for a given conversion
  var convert = function( conversion, successCallback, errorCallback ) {
    // set defaults for callbacks
    errorCallback = errorCallback || defaultError;
    successCallback = successCallback || defaultSuccess;

    var post_conversion = function(name){
      jQuery.ajax({
        url: path,
        type : "POST",
        data : { convert : name },
        success : successCallback,
        error : errorCallback
      });
    };

    if( typeof conversion === "string" ) {
      post_conversion( '"'+conversion+'"' );
    }else if( $.isArray( conversion ) ) {
      $.each( conversion, function( i, v ) {
        post_conversion('"'+v+'"');
      });
    }


  };

  return {
    init : init,
    ab_test : ab_test,
    bingo : convert,
    tests : tests
  };
  
})();



