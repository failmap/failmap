#!/usr/bin/env phantomjs
// utility to generate a list of requests that would be made by the browser when visiting a site
// useful to generate input for warmup or load testing tools like 'siege'
// $ tools/generate_requests.js https://faalkaart.nl | sort -u | grep https > urls.txt
// $ siege -vif urls.txt

var system = require('system');
var page = require('webpage').create();

page.viewportSize = {
  width: 2000,
  height: 2000,
};

page.onResourceRequested = function(request) {
  console.log(request.url);
};

page.open(system.args[1], function() {phantom.exit();});
