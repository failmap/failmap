// Registry Sentry for error reporting
let sentry_token = document.head.querySelector("[name=sentry_token]").getAttribute('content');
let version = document.head.querySelector("[name=version]").getAttribute('content');
if (sentry_token) {
    Raven.config(sentry_token, {release: version}).install();
}

// https://stackoverflow.com/questions/7625991/
// how-to-properly-add-entries-for-computed-values-to-the-django-internationalizati
var dynamic_translations = function(){
     gettext('2 weeks ago');
     gettext('3 weeks ago');
     gettext('1 month ago');
     gettext('2 months ago');
     gettext('3 months ago');
     gettext('7 days ago');
     gettext('now');
};

$(document).ready(function () {
    failmap.initializemap("nl");
    views();
    lazyload();
    d3stats();

    // if browser contains report anchor with organization id load that organization
    let match = RegExp('report-([0-9]+)').exec(location.hash);
    if (match) {
        let organization_id = match[1];
        location.href = '#report';
        vueReport.selected = organization_id;
    }

});
