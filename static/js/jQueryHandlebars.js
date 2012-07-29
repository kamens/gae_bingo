/**
 * jQueryHandlebars is a little jQuery plugin that makes it easy to render
 * a handlebars template. Example:
 *
 *  <script id="tmpl-monkey" type="x-handlebars-template">
 *      Gorillas are {{adjective}}.
 *  </script>
 *  ...
 *  <script>
 *      var html = $("#tmpl-monkey").handlebars({adjective: "scary"});
 *  </script>
 */

(function ($) {
    $.fn.handlebars = function (data) {
    	if (Handlebars && data) {
            var template = Handlebars.compile(this.html());
    	    return template(data);
        }
    };
})(jQuery);

