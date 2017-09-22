from subprocess import call

# todo: add this to the check in script? Not doing this now since it might change files you don't
# want to change?
isort = ".tox/py34/bin/isort"
call([isort, "-rc", "failmap_admin", "tests"])
