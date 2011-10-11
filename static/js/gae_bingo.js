// gae_bingo is a js library for client-side interaction with gae_bingo
// the only hard requirement is jquery 1.5+
// 
// because JSON.stringify is still not widely supported, consider including
// json2.js from https://github.com/douglascrockford/JSON-js 
// *if window.JSON is not found, gae_bingo will silently do nothing.*

// gae_bingo is available on the dashboard page if you open a console and want
// to test it out.

// Example usage
/*
    // score a conversion
    gae_bingo.bingo( "mario_yay" )

    // create a new a/b test split 90/10 with three possible conversions
    gae_bingo.ab_test( "mario points", { "on" : 90, "off" : 10 }, [ "mario_yay", "mario_boo", "mario_indifferent" ] )

    // check user's status in a test
    gae_bingo.ab_test( "mario points", null, null, function( d ) { console.log( d ); } )

    // see all tests requested so far
    gae_bingo.tests
    // ==> returns { "mario points" : "on" }

    // you can specify default callbacks
    gae_bingo.init({
      success : function( d, ts, jqx ) { console.log( "woo!", d ); },
      error : function( jqx, ts, e ) { console.error( "nuts", jqx )}
    })

    // if you're just playing around, there are some console-friendly defaults available
    // which you can access by defining debug as an init parameter
    gae_bingo.init( { "debug" : true } )

*/
 
var gae_bingo = (function() {
  var path = "/gae_bingo/blotter/";

  var defaultSuccess = $.noop;
  var defaultError = $.noop;

  var tests = {};

  // init takes a spec object which is totally optional,
  // you can define the following properties on it
  // * **path** (string) : the path to gae_bingo/blotter
  // * **success** (function) : a jQuery ajax succes callback like:
  //   function(data, textStatus, jqXHR){ ... }
  // * error (function) : a jQuery ajax error callback like:
  //   function(jqXHR, textStatus, errorThrown){ ... }
  // * **debug** : if debug is defined, defaultError and defaultSuccess 
  //   are overridden (if set) and console.log/error the result of a query
  var init = function( spec ) {
    spec = (typeof spec === "undefined") ? {} : spec;
    
    path = spec.path || path;
    
    defaultSuccess = (spec.success !== undefined) ? spec.success : defaultSuccess;
    defaultError = (spec.error !== undefined) ? spec.error : defaultError;
    
    // set debugging console-callbacks if spec.debug set
    defaultSuccess = (spec.debug === undefined) ? defaultSuccess :
      function( d, ts, jx) { console.log( "gae_bingo success(" + jx.status + "):", d ); };
    defaultError = (spec.debug === undefined) ? defaultError :
      function( jx, ts ) { console.error( "gae_bingo error (" + jx.status + "):", jx ); };
  };

  // ab_test takes a canonical_name which is the name of a given ab_test
  // if you are a dev, this will create the test and return the 'alternative' you are in (a or b)
  // by default this will be `true` or `false` if no `alternative_params` are passed.
  // * **alternative_params** (Object | Array) can be a list (in which case all list items will 
  //   be distributed equally) or it can be an object like {"in_test":15, "not_in_test": 85} 
  //   which will place 15% of participants in the test and leave 85% out of it.
  // * **conversion_name** (Array) is a list of possible conversions (i.e. things you can bingo)
  // * **successCallback** (function) overrides any success callback previously defined 
  //   (or sets one for this invocation) takes the standard JQuery success params (see gae_bingo.init)
  // * **errorCallback** (function) same as successCallback, see above
  var ab_test = function( canonical_name, alternative_params, conversion_name, successCallback, errorCallback ) {
    // set defaults for callbacks
    errorCallback = errorCallback || defaultError;
    successCallback = successCallback || defaultSuccess;

    // don't init ab tests on browsers without JSON support
    var stringify = window.JSON.stringify || $.noop;

    var testdata = { 
      "canonical_name" : canonical_name,
      "alternative_params" : stringify(alternative_params),
      "conversion_name" : stringify(conversion_name)
    };

    jQuery.ajax({
      type: "POST",
      url: path + "ab_test",
      data : testdata,
      success : function(d, ts, jx) { 
        tests[canonical_name] = d; 
        successCallback( d, ts, jx);
      },
      error : errorCallback
    });
  };

  // convert triggers a bingo. 
  // **conversion** may be either the ab_test name or a specific conversion that was
  //   created when the ab_test was initialized
  // on success, no data is returned but `successCallback` is fired anyway
  // on failure (no experiment found for conversion name) `errorCallback` is fired
  // n.b. `successCallback` is called even if a bingo has already been recorded for a given conversion
  var convert = function( conversion, successCallback, errorCallback ) {
    // set defaults for callbacks
    errorCallback = errorCallback || defaultError;
    successCallback = successCallback || defaultSuccess;
    
    var stringify = window.JSON.stringify || $.noop;

    var post_conversion = function(name){
      jQuery.ajax({
        url: path + "bingo",
        type : "POST",
        data : { convert : name },
        success : successCallback,
        error : errorCallback
      });
    };
    

    if( $.isArray( conversion ) ) {
      $.each( conversion, function( i, v ) {
        post_conversion( stringify( v ) );
      });
    } else {
      post_conversion( stringify( conversion ) );
    }


  };

  return {
    init : init,
    ab_test : window.JSON ? ab_test : $.noop,
    bingo : window.JSON ? convert : $.noop,
    tests : tests
  };
  
})();



