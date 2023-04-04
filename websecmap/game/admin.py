import logging
import re
import urllib
from datetime import datetime, timedelta, timezone
from random import choice, choices, randint

import tldextract
from constance import config
from django.contrib import admin
from django.db import transaction
from django.utils.safestring import mark_safe
from import_export.admin import ImportExportModelAdmin
from jet.admin import CompactInline

from websecmap.app.admin import generate_game_user
from websecmap.app.models import GameUser
from websecmap.game.models import Contest, OrganizationSubmission, Team, UrlSubmission
from websecmap.organizations.models import Coordinate, Organization, OrganizationType, Url
from websecmap.scanners.scanner.http import resolves

log = logging.getLogger(__package__)


class TeamInline(CompactInline):
    model = Team
    extra = 0
    can_delete = False
    ordering = ["name"]


class OrganizationSubmissionInline(CompactInline):
    model = OrganizationSubmission
    extra = 0
    can_delete = False
    ordering = ["organization_name"]
    readonly_fields = [
        "organization_country",
        "added_by_team",
        "organization_type_name",
        "organization_name",
        "organization_address",
        "organization_evidence",
        "organization_address_geocoded",
        "organization_wikipedia",
        "organization_wikidata_code",
        "organization_in_system",
        "has_been_accepted",
        "has_been_rejected",
        "added_on",
    ]


class UrlSubmissionInline(CompactInline):
    model = UrlSubmission
    extra = 0
    can_delete = False
    readonly_fields = [
        "added_by_team",
        "for_organization",
        "url",
        "url_in_system",
        "has_been_accepted",
        "has_been_rejected",
        "added_on",
    ]


@admin.register(Contest)
class ContestAdmin(ImportExportModelAdmin, admin.ModelAdmin):

    list_display = ("name", "target_country", "from_moment", "until_moment", "admin_user", "teams")
    search_fields = ("name", "target_country")
    list_filter = ("name", "target_country")

    @staticmethod
    def teams(obj):
        return Team.objects.all().filter(participating_in_contest__name=obj.name).count()

    fieldsets = (
        (
            None,
            {
                "fields": ("name", "from_moment", "until_moment"),
                "description": "<span style='color: red'>"
                "Don't forget to disable subdomain discovery AND to onboard every 1 minute.</span>",
            },
        ),
        (
            "Configuration",
            {
                "fields": ("target_country", "url_organization_discovery_help", "admin_user"),
            },
        ),
    )

    actions = []

    @transaction.atomic
    def add_contest(self, request, queryset):
        # create a new contest
        contest = Contest()
        contest.target_country = "NL"
        contest.from_moment = datetime.now(timezone.utc)
        contest.until_moment = datetime.now(timezone.utc) + timedelta(days=3)
        contest.admin_user = generate_game_user()
        contest.name = f"new_contest_{datetime.now(timezone.utc).date()}"
        contest.save()

        # create a number of team members.
        for _ in range(12):
            generate_team(contest)

        self.message_user(request, "Contest user, contest and teams have been created.")

    add_contest.short_description = "Add contest (select one)"
    actions.append("add_contest")

    @transaction.atomic
    def add_a_dozen_teams(self, request, queryset):
        for contest in queryset:
            for _ in range(12):
                generate_team(contest)

        self.message_user(request, "Urls have been rejected.")

    add_a_dozen_teams.short_description = "Add 12 teams"
    actions.append("add_a_dozen_teams")

    # todo: generate a printout for teams and this contest, to hand out.
    def show_printout(self, request, queryset):
        for contest in queryset:
            from django.http import HttpResponse

            content = ""
            content += create_printout(contest)
            return HttpResponse(content)

    show_printout.short_description = "Create Printout"
    actions.append("show_printout")

    inlines = [TeamInline]


def generate_team(contest):
    new_team = Team()
    new_team.name = generate_team_name()
    new_team.color = generate_pastel_color()
    new_team.participating_in_contest = contest
    new_team.secret = generate_team_password()
    new_team.allowed_to_submit_things = True
    new_team.save()


def create_printout(contest):
    login_url = f"{config.PROJECT_WEBSITE}/game/"
    game_url = f"{config.PROJECT_WEBSITE}/game/scores/"

    username = f"{contest.admin_user.username}"  # associate an account to login.
    game_user = GameUser.objects.all().filter(user=contest.admin_user).first()
    if not game_user or game_user.password is None:
        raise ValueError("Set a game user for this contest, do so in the users list. Also set the password.")

    password = f"{game_user.password}"

    # todo: margin top per page.
    content = "<style>body{font-family: verdana, sans-serif;}</style>"
    content += """<style media='print'>
            /* show background colors in print */
            * { -webkit-print-color-adjust: exact !important;
                color-adjust: exact !important;
            }
            @page {
                size: auto;   /* auto is the initial value */
                margin: 0;  /* this affects the margin in the printer settings */
                padding-top: 72px;
                padding-bottom: 72px;
            }
            body  {
                padding-left: 66px;
            }
            .noprint, .noprint * {
                display: none !important;
            }
               </style>"""
    content += f"<h1>{contest.name}</h1>"
    content += f"<p>Starts at {contest.from_moment}. Deadline: {contest.until_moment}.</p>"
    content += "<br />"
    content += "<h2>Teams</h2>"
    teams = Team.objects.all().filter(participating_in_contest=contest, allowed_to_submit_things=True)
    compiled_regex = re.compile(r"<.*?>")
    for team in teams:
        teamcontent = ""
        teamcontent += "<hr style='page-break-after: always; border: 0px; padding-bottom: 20px;'>"
        teamcontent += (
            "<p style='font-weight: bold; font-size: 2em; "
            "padding-top: 100px; margin-bottom: 0px; padding-bottom: 0px;'>"
            f"Hi team <span style='background-color: {team.color};'>{team.name}</span>!</p>"
            "<br><br>"
        )
        teamcontent += "Thanks for joining this contest! These instructions try to help you get started.<br><br>"
        teamcontent += "To participate, first go to the gaming interface: <br>"
        teamcontent += f"<b>{login_url}</b> <br>"
        teamcontent += "<br />"
        teamcontent += "Then <b>click login</b> at the top right corner.<br>"
        teamcontent += "<br />"
        teamcontent += "Use the following account information: <br>"
        teamcontent += f"Username: <b>{username}</b><br>"
        teamcontent += f"Password: <b>{password}</b><br />"
        teamcontent += "<br />"
        teamcontent += f"Then, select this contest: <b>{contest.name}</b><br />"
        teamcontent += "<br />"
        teamcontent += "Then select your team and fill in it's secret:<br />"
        teamcontent += (
            f"Team: <span style='background-color: {team.color}; width: 60px; height: 20px;'>"
            f"<b>{team.name}</b></span><br />"
        )
        teamcontent += f"Secret: <b>{team.secret}</b><br />"
        teamcontent += "<br />"
        teamcontent += "If you have any questions, please ask the contest organizer!<br>"
        teamcontent += "<br />"
        teamcontent += "Have fun!<br>"
        teamcontent += f"<i>-- the {contest.name} contest organizers</s><br>"
        teamcontent += "<br /><br />"
        teamcontent += "<i>P.S. It's possible to see the scorebord without logging in at:</i><br>"
        teamcontent += f"<i>{game_url}</i><br>"
        teamcontent += "<br />"

        # only the beginning of the tag, so the closing style and any properties etc don't matter.
        without_html = teamcontent.replace("<br", "\n<br")
        without_html = compiled_regex.sub("", without_html)

        stuff = urllib.parse.quote(without_html)
        mailcontent = ""
        mailcontent += (
            "<a class='noprint' href='mailto:address"
            f"?subject=Your {contest.name} Contest Login Info"
            f"&body={stuff}'>E-Mail this</a>"
        )

        content += teamcontent
        content += mailcontent

    return content


def generate_team_password():
    """
    The password has to be fairly simple

    :return:
    """

    # do not include similar characters like g9, liI1 etc. J oO0Q B8, YV
    letters = "ACDEFGHKLMNPRSTUVWXZ234567"  # len = 26

    password = "".join(choices(letters, k=16))
    # to make it easier to read, add spaces per 4 characters.
    return f"{password[0:4]}-{password[4:8]}-{password[8:12]}-{password[12:16]}"


def generate_pastel_color():
    def rand():
        return randint(125, 255)

    return f"#{rand():02X}{rand():02X}{rand():02X}"


def generate_team_name():
    return generate_team_name_docker()


def generate_team_name_docker():
    # generate nice names like docker container names
    # https://github.com/moby/moby/blob/master/pkg/namesgenerator/names-generator.go

    # slightly redacted list to make all names always positive.
    traits = [
        "admiring",
        "adoring",
        "affectionate",
        "amazing",
        "awesome",
        "blissful",
        "bold",
        "brave",
        "charming",
        "clever",
        "cool",
        "compassionate",
        "competent",
        "confident",
        "crazy",
        "dazzling",
        "determined",
        "dreamy",
        "eager",
        "ecstatic",
        "elastic",
        "elated",
        "elegant",
        "eloquent",
        "epic",
        "fervent",
        "festive",
        "flamboyant",
        "focused",
        "friendly",
        "gallant",
        "gifted",
        "goofy",
        "gracious",
        "happy",
        "hardcore",
        "heuristic",
        "hopeful",
        "infallible",
        "inspiring",
        "jolly",
        "jovial",
        "keen",
        "kind",
        "laughing",
        "loving",
        "lucid",
        "magical",
        "mystifying",
        "modest",
        "musing",
        "naughty",
        "nifty",
        "nostalgic",
        "objective",
        "optimistic",
        "peaceful",
        "pensive",
        "practical",
        "priceless",
        "quizzical",
        "recursing",
        "relaxed",
        "reverent",
        "romantic",
        "serene",
        "sharp",
        "silly",
        "sleepy",
        "sweet",
        "tender",
        "trusting",
        "unruffled",
        "upbeat",
        "vibrant",
        "vigilant",
        "vigorous",
        "wizardly",
        "wonderful",
        "youthful",
        "zealous",
        "zen",
    ]

    # See the elaborate explanations of all these names in the original file.
    names = [
        "albattani",
        "allen",
        "almeida",
        "antonelli",
        "agnesi",
        "archimedes",
        "ardinghelli",
        "aryabhata",
        "austin",
        "babbage",
        "banach",
        "banzai",
        "bardeen",
        "bartik",
        "bassi",
        "beaver",
        "bell",
        "benz",
        "bhabha",
        "bhaskara",
        "black",
        "blackburn",
        "blackwell",
        "bohr",
        "booth",
        "borg",
        "bose",
        "boyd",
        "brahmagupta",
        "brattain",
        "brown",
        "burnell",
        "buck",
        "burnell",
        "cannon",
        "carson",
        "cartwright",
        "chandrasekhar",
        "chaplygin",
        "chatelet",
        "chatterjee",
        "chebyshev",
        "cocks",
        "cohen",
        "chaum",
        "clarke",
        "colden",
        "cori",
        "cray",
        "curran",
        "curie",
        "darwin",
        "davinci",
        "dewdney",
        "dhawan",
        "diffie",
        "dijkstra",
        "dirac",
        "driscoll",
        "dubinsky",
        "easley",
        "edison",
        "einstein",
        "elbakyan",
        "elgamal",
        "elion",
        "ellis",
        "engelbart",
        "euclid",
        "euler",
        "faraday",
        "feistel",
        "fermat",
        "fermi",
        "feynman",
        "franklin",
        "gagarin",
        "galileo",
        "galois",
        "ganguly",
        "gates",
        "gauss",
        "germain",
        "goldberg",
        "goldstine",
        "goldwasser",
        "golick",
        "goodall",
        "gould",
        "greider",
        "grothendieck",
        "haibt",
        "hamilton",
        "haslett",
        "hawking",
        "hellman",
        "heisenberg",
        "hermann",
        "herschel",
        "hertz",
        "heyrovsky",
        "hodgkin",
        "hofstadter",
        "hoover",
        "hopper",
        "hugle",
        "hypatia",
        "ishizaka",
        "jackson",
        "jang",
        "jennings",
        "jepsen",
        "johnson",
        "joliot",
        "jones",
        "kalam",
        "kapitsa",
        "kare",
        "keldysh",
        "keller",
        "kepler",
        "khayyam",
        "khorana",
        "kilby",
        "kirch",
        "knuth",
        "kowalevski",
        "lalande",
        "lamarr",
        "lamport",
        "leakey",
        "leavitt",
        "lederberg",
        "lehmann",
        "lewin",
        "lichterman",
        "liskov",
        "lovelace",
        "lumiere",
        "mahavira",
        "margulis",
        "matsumoto",
        "maxwell",
        "mayer",
        "mccarthy",
        "mcclintock",
        "mclaren",
        "mclean",
        "mcnulty",
        "mendel",
        "mendeleev",
        "meitner",
        "meninsky",
        "merkle",
        "mestorf",
        "minsky",
        "mirzakhani",
        "moore",
        "morse",
        "murdock",
        "moser",
        "napier",
        "nash",
        "neumann",
        "newton",
        "nightingale",
        "nobel",
        "noether",
        "northcutt",
        "noyce",
        "panini",
        "pare",
        "pascal",
        "pasteur",
        "payne",
        "perlman",
        "pike",
        "poincare",
        "poitras",
        "proskuriakova",
        "ptolemy",
        "raman",
        "ramanujan",
        "ride",
        "montalcini",
        "ritchie",
        "rhodes",
        "robinson",
        "roentgen",
        "rosalind",
        "rubin",
        "saha",
        "sammet",
        "sanderson",
        "shannon",
        "shaw",
        "shirley",
        "shockley",
        "shtern",
        "sinoussi",
        "snyder",
        "solomon",
        "spence",
        "sutherland",
        "stallman",
        "stonebraker",
        "swanson",
        "swartz",
        "swirles",
        "taussig",
        "tereshkova",
        "tesla",
        "tharp",
        "thompson",
        "torvalds",
        "tu",
        "turing",
        "varahamihira",
        "vaughan",
        "visvesvaraya",
        "volhard",
        "villani",
        "wescoff",
        "wiles",
        "williams",
        "williamson",
        "wilson",
        "wing",
        "wozniak",
        "wright",
        "wu",
        "yalow",
        "yonath",
        "zhukovsky",
    ]

    return f"{choice(traits).capitalize()} {choice(names).capitalize()}"


# todo: submissioninline, read only... there are going to be MANY new things...
@admin.register(Team)
class TeamAdmin(ImportExportModelAdmin, admin.ModelAdmin):

    list_display = ("name", "team_color", "participating_in_contest", "allowed_to_submit_things")
    search_fields = ("name", "participating_in_contest__name")
    list_filter = ("name", "participating_in_contest__name", "participating_in_contest__target_country")

    fieldsets = (
        (None, {"fields": ("name", "color", "participating_in_contest", "allowed_to_submit_things")}),
        (
            "secret",
            {
                "fields": ("secret",),
            },
        ),
    )

    @staticmethod
    def team_color(obj):
        return mark_safe(f"<div style='background-color: {obj.color}; width: 60px; height: 20px;'></div>")

    actions = []

    @transaction.atomic
    def allow_team(self, request, queryset):
        for team in queryset:
            team.allowed_to_submit_things = True
            team.save()

        self.message_user(request, "Teams are allowed .")

    allow_team.short_description = "Allow to submit"
    actions.append("allow_team")

    @transaction.atomic
    def disallow_team(self, request, queryset):
        for team in queryset:
            team.allowed_to_submit_things = False
            team.save()

        self.message_user(request, "Teams are disallowed.")

    disallow_team.short_description = "Disallow to submit"
    actions.append("disallow_team")

    # UrlSubmissionInline will make the load slow / non-loading.
    inlines = [
        OrganizationSubmissionInline,
    ]


@admin.register(UrlSubmission)
class UrlSubmissionAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    list_display = ("added_by_team", "for_organization", "url", "has_been_accepted", "has_been_rejected", "added_on")
    search_fields = ("added_by_team__name", "organization_name", "url")

    list_filter = (
        "has_been_accepted",
        "has_been_rejected",
        "added_by_team__name",
        "added_by_team__participating_in_contest__name",
    )

    fields = (
        "added_by_team",
        "for_organization",
        "url",
        "url_in_system",
        "has_been_accepted",
        "has_been_rejected",
        "added_on",
    )

    ordering = ("for_organization", "url")

    actions = []

    @transaction.atomic
    def reset_judgement(self, request, queryset):
        for urlsubmission in queryset:
            urlsubmission.has_been_accepted = False
            urlsubmission.has_been_rejected = False
            urlsubmission.save()
        self.message_user(request, "URL be accepted/rejected again.")

    reset_judgement.short_description = "Reset acceptance / rejection."
    actions.append("reset_judgement")

    @transaction.atomic
    def accept(self, request, queryset):
        for urlsubmission in queryset:

            # don't add the same thing over and over, allows to re-select the ones already added without a problem
            # once rejected, can't be accepted via buttons: needs to be a manual action
            if urlsubmission.has_been_accepted or urlsubmission.has_been_rejected:
                continue

            # it's possible that the url already is in the system. If so, tie that to the submitted organization.
            # could be dead etc... (stacking?)
            url = Url.objects.all().filter(url=urlsubmission.url, is_dead=False).first()

            if not url:
                log.debug("adding new url: %s", urlsubmission.url)
                # if it already exists, then add the url to the organization.
                url = Url(url=urlsubmission.url)
                url.save()

            # the organization is already inside the submission and should exist in most cases.
            url.organization.add(urlsubmission.for_organization)
            url.save()

            # add some tracking data to the submission
            urlsubmission.url_in_system = url
            urlsubmission.has_been_accepted = True
            urlsubmission.save()

        self.message_user(request, "Urls have been accepted and added to the system.")

    accept.short_description = "✅  Accept"
    actions.append("accept")

    @transaction.atomic
    def reject(self, request, queryset):
        for urlsubmission in queryset:
            urlsubmission.has_been_rejected = True
            urlsubmission.save()

        self.message_user(request, "Urls have been rejected.")

    reject.short_description = "❌  Reject"
    actions.append("reject")


@admin.register(OrganizationSubmission)
class OrganizationSubmissionAdmin(ImportExportModelAdmin, admin.ModelAdmin):
    list_display = (
        "added_by_team",
        "organization_name",
        "organization_type_name",
        "has_been_accepted",
        "has_been_rejected",
        "added_on",
    )
    search_fields = ("added_by_team__name", "organization_name", "organization_type_name")

    list_filter = (
        "added_by_team__name",
        "has_been_accepted",
        "has_been_rejected",
        "added_by_team__participating_in_contest__name",
    )

    fields = (
        "added_by_team",
        "organization_country",
        "organization_type_name",
        "organization_name",
        "organization_address",
        "organization_address_geocoded",
        "organization_wikipedia",
        "organization_wikidata_code",
        "suggested_urls",
        "has_been_accepted",
        "has_been_rejected",
        "organization_in_system",
        "added_on",
    )

    actions = []

    @transaction.atomic
    def accept(self, request, queryset):
        for osm in queryset:

            # don't add the same thing over and over, allows to re-select the ones already added without a problem
            # once rejected, can't be accepted via buttons: needs to be a manual action
            # todo: make it possible to reject afterwards, and delete all subdomains etc.
            if osm.has_been_accepted or osm.has_been_rejected:
                log.debug("Organization has already been accepted or rejected.")
                continue

            # this might revive some old organizations, so domain knowledge is required.
            # In this case the organization already exists with the same name, type and alive.
            # this means we don't need to add a new one, or with new coordinates.
            layer = OrganizationType.objects.get(name=osm.organization_type_name)
            already_exists = (
                Organization.objects.all()
                .filter(
                    name=osm.organization_name,
                    country=osm.organization_country,
                    is_dead=False,
                    type=layer,
                    layers__in=layer,
                )
                .first()
            )

            if already_exists:
                log.debug("Organization with the same name already exists, in this country and type and is alive.")
                continue

            # Create a new one
            # address and evidence are saved elsewhere. Since we have a reference we can auto-update after
            # geocoding works. In the hopes some quality data has been added, which can be checked more easy then
            # adding this data in the system again(?)
            new_org = Organization(
                name=osm.organization_name,
                country=osm.organization_country,
                is_dead=False,
                type=OrganizationType.objects.get(name=osm.organization_type_name),
                created_on=datetime.now(timezone.utc),
            )
            new_org.save()
            new_org.layers.add(new_org.type)
            log.debug("Saved new organization.")

            # of course it has a new coordinate
            new_coordinate = Coordinate(
                organization=new_org,
                geojsontype="Point",
                area=osm.organization_address_geocoded,
                edit_area={"type": "Point", "coordinates": osm.organization_address_geocoded},
                created_on=datetime.now(timezone.utc),
                creation_metadata="Accepted organization submission",
            )
            new_coordinate.save()
            log.debug("Saved matching coordinate.")

            # add the toplevel urls if they exist.
            if osm.suggested_urls:
                # a disgusting way to parse this list, without using eval.
                urls = osm.suggested_urls.replace("[", "").replace("'", "").replace("]", "").replace(",", "").split(" ")
                urls = check_valid_urls(urls)
                for url in urls:

                    # don't auto add the URL, to have a bit more control over what is being added
                    # new_url = Url()
                    # new_url.url = url
                    # new_url.save()
                    # new_url.organization.add(new_org)
                    # new_url.save()

                    submission = UrlSubmission()
                    submission.url = url
                    submission.has_been_rejected = False
                    submission.has_been_accepted = False
                    submission.added_by_team = osm.added_by_team
                    submission.added_on = osm.added_on
                    # submission.url_in_system = new_url
                    submission.for_organization = new_org
                    submission.save()

            # and save tracking information
            osm.organization_in_system = new_org
            osm.has_been_accepted = True
            osm.save()
            log.debug("Saved tracking information for the game.")

        self.message_user(request, "Organizations have been accepted and added to the system.")

    accept.short_description = "✅  Accept"
    actions.append("accept")

    @transaction.atomic
    def reject(self, request, queryset):
        for organizationsubmission in queryset:
            organizationsubmission.has_been_rejected = True
            organizationsubmission.save()

        self.message_user(request, "Organisation(s) have been rejected.")

    reject.short_description = "❌  Reject"
    actions.append("reject")


def check_valid_urls(urls):
    valid = []

    for url in urls:
        url = url.lower()
        url = url.replace("https://", "")
        url = url.replace("http://", "")

        extract = tldextract.extract(url)
        if not extract.suffix:
            continue

        # tld extract has also removed ports, usernames, passwords and other nonsense.
        url = f"{extract.domain}.{extract.suffix}"

        # see if the URL resolves at all:
        if not resolves(url):
            continue

        if url not in valid:
            valid.append(url)

    return valid
