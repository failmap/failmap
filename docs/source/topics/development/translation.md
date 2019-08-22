# Translation

Translating should be straightforward. It does not require a running installation of websecmap, but it's practical
to actually see the results before committing them to the repository.


## Translating components and general texts:
Translations are loaded based on the user agent (will be changed to cookie setting).

There are two locations where translations are stored. Messages used in a lot of places, such as scanner 
results, are stored here:

https://gitlab.com/internet-cleanup-foundation/web-security-map/blob/master/websecmap/map/static/js/translations/websecmap.js


Other translations are done "per component". You'll find a translation section on each component here:
https://gitlab.com/internet-cleanup-foundation/web-security-map/tree/master/websecmap/map/static/js/components


For example, the intro text is defined in the intro component, here:
https://gitlab.com/internet-cleanup-foundation/web-security-map/blob/master/websecmap/map/static/js/components/intro.vue


You can add translations using the vue-i18n format. This has a lot of options and is documented here:
https://kazupon.github.io/vue-i18n/


Adding your language should be straightforward, as examples are given in English and Dutch. Just copy and 
paste your own language under it and create a pull request.

