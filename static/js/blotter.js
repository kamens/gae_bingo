// a small javascript library for interacting with gae_bingo's blotter
// requires jquery 1.5+

// Example usage
/*

blot = Blotter()
// score a conversion
Blotter.bingo("mario_proficient")
// check user's status in a test
blot.ab_test("mario points", function(d){console.log(d)})
// { "mario points" : "on" }
blot.ab_test()
// ==> returns { "mario points" : "on" }
blot.tests 
// ==> returns { "mario points" : "on" }

// you can specify default callbacks when initializing
blottie = blotter({success : function(d, ts, jqx){}, error: function(jqx, ts, e){}})

// if you're just playing, there are some console-friendly defaults available
blotto = blotter( { debug : true } )

// if you've installed gae_bingo's blotter in a non-default location, you can set its path as well
dauber = blotter( { path : "/dauber" } )

// Blotter ( settings )
// where settings is a key/value pair that takes the following defaults
## path
defaults to
## success
## error
{
  path : "path to gae_bingo/blotter" || 
  success : function(){},
  error : function(){}
)

*/

// 
var Blotter = function( spec ){
  spec = (typeof spec === "undefined") ? {} : spec;
  var path = spec.path || "/gae_bingo/blotter";

  var defaultSuccess = (spec.success !== undefined) ? spec.success : $.noop;
  var defaultError = (spec.error !== undefined) ? spec.error : $.noop;

  defaultSuccess = (spec.debug === undefined) ? defaultSuccess : function(d){console.log("blotter success:",d);};
  defaultError = (spec.debug === undefined) ? defaultError : function(d){console.error("blotter error:",d);};

  var tests = {};

  // ab_test takes a testName which is the name of a given ab_test
  var ab_test = function( testName, successCallback, errorCallback ){
    // set defaults for callbacks
    errorCallback = errorCallback || defaultError;
    successCallback = successCallback || defaultSuccess;

    if (!testName){
      // return all stored tests and values
      return tests;
    }else{
      jQuery.ajax({
        url: path,
        data : { 
          canonical_name : testName
        },
        success : function(d, ts, jx){ tests[testName] = d[testName]; successCallback(d,ts,jx);},
        error : errorCallback
      });
     }
  };

  // convert calls a bingo. on success, no data is returned but successCallback is fired anyway
  // on failure (no experiment found for conversion name) errorCallback is fired
  // successCallback is called even if a bingo has already been recorded for a given conversion
  var convert = function( conversion, successCallback, errorCallback ){
    // set defaults for callbacks
    errorCallback = errorCallback || defaultError;
    successCallback = successCallback || defaultSuccess;

    jQuery.ajax({
      url: path,
      type : "POST",
      data : { convert : conversion },
      success : successCallback,
      error : errorCallback
    });
  };



  return {
    ab_test : ab_test,
    bingo : convert,
    tests : tests
  };
  
};