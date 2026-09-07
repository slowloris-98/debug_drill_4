"""Load the Waypoint demo dataset.

Nine customer organizations, their assessments, the candidates who sat them,
the score reports their grading partners delivered, and the webhook endpoints
their ATS connectors receive events on.

    python manage.py seed_demo
"""

import datetime as dt
import random

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import connection, transaction

from core.models import (
    ApiKey,
    Assessment,
    Candidate,
    Organization,
    ScoreReport,
    WebhookDelivery,
    WebhookEndpoint,
)
from core.services import publish_report, publish_reports

UTC = dt.timezone.utc


def at(month, day, hour=9, minute=0):
    return dt.datetime(2026, month, day, hour, minute, tzinfo=UTC)


ORGANIZATIONS = [
    # name, slug, ats, username, full name, api key
    ("Volta Automotive", "volta", "greenhouse", "dmoreau", "Daniel Moreau",
     "wp_live_volta_3d81f4a9c2"),
    ("Northgate Financial", "northgate", "greenhouse", "sfrye", "Sasha Frye",
     "wp_live_northgate_6b27ce80d4"),
    ("Lakeshore Media", "lakeshore", "lever", "tobrien", "Tess O'Brien",
     "wp_live_lakeshore_9a54f1bb37"),
    ("Ardent Health", "ardent", "workday", "rkeeler", "Ruth Keeler",
     "wp_live_ardent_2f6d90ac15"),
    ("Quillon Software", "quillon", "lever", "bmarsh", "Ben Marsh",
     "wp_live_quillon_7c03be49f8"),
    ("Meridian Freight", "meridian", "greenhouse", "avargas", "Ana Vargas",
     "wp_live_meridian_5e18d7f206"),
    ("Calder Insurance", "calder", "workday", "jpatel", "Jyoti Patel",
     "wp_live_calder_4a92c60be1"),
    ("Pinehurst Retail", "pinehurst", "lever", "mkovac", "Milan Kovac",
     "wp_live_pinehurst_8d71fa35c9"),
    ("Selwyn Energy", "selwyn", "greenhouse", "hlarsen", "Hanne Larsen",
     "wp_live_selwyn_1b40e92d7a"),
]

# Lakeshore Media, "Backend Engineer — Screen (June 2026)". Delivered by the
# grading partner over 2026-06-05 and 2026-06-06.
LAKESHORE_COHORT = [
    ("Nadia Farouk", "100"),
    ("Marcus Okonjo", "98"),
    ("Elena Petrova", "96"),
    ("Samuel Adeyemi", "94"),
    ("Priti Ranganathan", "91"),
    ("Jonas Berg", "88"),
    ("Amara Nwosu", "85"),
    ("Ravi Deshmukh", "82"),
    ("Clara Jensen", "79"),
    ("Tobias Lindgren", "76"),
    ("Yuki Tanaka", "73"),
    ("Fiona Mackay", "70"),
    ("Omar Haddad", "68"),
    ("Grace Mbeki", "65"),
    ("Lucas Ferreira", "63"),
    ("Ines Dominguez", "61"),
    ("Ahmed Chaudhry", "60"),
    ("Rosa Villanueva", "58"),
    ("Peter Novak", "55"),
    ("Sana Iqbal", "52"),
    ("Daniel Ochoa", "49"),
    ("Mei Ling Chua", "47"),
    ("Aaron Whitfield", "44"),
    ("Zoe Karras", "41"),
    ("Ibrahim Toure", "38"),
    ("Helena Brandt", "35"),
    ("Victor Almeida", "33"),
    ("Naomi Sato", "30"),
    ("Callum Fraser", "28"),
    ("Beatriz Rocha", "25"),
    ("Karan Malhotra", "22"),
    ("Sophie Delacroix", "19"),
    ("Andre Botha", "15"),
    ("Linnea Holm", "12"),
    ("Colin Radcliffe", "9"),
    ("Tunde Bakare", "6"),
    ("Marta Kowalski", "4"),
    ("Devon Pryce", "n/a"),
    ("Isabel Moreno", "n/a"),
    ("Kwame Asante", "n/a"),
    ("Freya Halvorsen", "n/a"),
    ("Simon Achebe", "n/a"),
    ("Rania Khoury", "n/a"),
]

FIRST_NAMES = [
    "Aisha", "Bruno", "Carmen", "Dmitri", "Eve", "Farid", "Greta", "Hassan",
    "Iris", "Jamal", "Kiara", "Leon", "Mira", "Niall", "Oksana", "Pablo",
    "Qadir", "Rosa", "Sven", "Tamar", "Umar", "Vera", "Wesley", "Xiulan",
    "Yara", "Zane", "Anita", "Bilal", "Chiara", "Derek", "Esme", "Felipe",
]
LAST_NAMES = [
    "Abara", "Bennett", "Costa", "Duval", "Ellis", "Farrow", "Gulliver",
    "Hoang", "Imamura", "Jansen", "Kaur", "Lombardi", "Mensah", "Nilsen",
    "Ortega", "Pryor", "Quill", "Rahman", "Silva", "Thorne", "Ubeda",
    "Vance", "Whitlock", "Xu", "Yilmaz", "Zubair",
]


class Command(BaseCommand):
    help = "Load the Waypoint demo dataset."

    def handle(self, *args, **options):
        self.rng = random.Random(20260612)
        self.stamps = {}

        with transaction.atomic():
            self._reset()
            organizations = self._organizations()
            self._endpoints(organizations)
            self._volta(organizations["volta"])
            self._northgate(organizations["northgate"])
            self._lakeshore(organizations["lakeshore"])
            for slug in ("ardent", "quillon", "meridian", "calder", "pinehurst", "selwyn"):
                self._filler(organizations[slug])
            self._apply_timestamps()
            self._delivery_outcomes(organizations)

        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {Organization.objects.count()} organizations, "
                f"{Candidate.objects.count()} candidates, "
                f"{ScoreReport.objects.count()} score reports."
            )
        )

    # ------------------------------------------------------------------ setup

    def _reset(self):
        WebhookDelivery.objects.all().delete()
        WebhookEndpoint.objects.all().delete()
        ScoreReport.objects.all().delete()
        Candidate.objects.all().delete()
        Assessment.objects.all().delete()
        ApiKey.objects.all().delete()
        Organization.objects.all().delete()
        User.objects.all().delete()

        # Re-seeding produces the same identifiers as the first run.
        if connection.vendor == "sqlite":
            with connection.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM sqlite_sequence WHERE name LIKE 'core_%%'"
                )

    def _organizations(self):
        User.objects.create_superuser("wpops", "wpops@waypoint.example", "waypoint")

        organizations = {}
        for name, slug, ats, username, full_name, key in ORGANIZATIONS:
            first, _, last = full_name.partition(" ")
            user = User.objects.create_user(
                username,
                f"{username}@{slug}.example",
                "waypoint",
                first_name=first,
                last_name=last,
                is_staff=True,
            )
            organization = Organization.objects.create(
                name=name,
                slug=slug,
                ats_provider=ats,
                owner=user,
                created_at=at(1, 12),
            )
            ApiKey.objects.create(
                organization=organization,
                key=key,
                label="production",
                created_at=at(1, 12),
            )
            organizations[slug] = organization
        return organizations

    def _endpoints(self, organizations):
        WebhookEndpoint.objects.create(
            organization=organizations["volta"],
            url="https://hooks.volta-automotive.example/waypoint",
            secret="whsec_volta_5f2c8ab1",
            events=[
                WebhookEndpoint.RESULT_PUBLISHED,
                WebhookEndpoint.RESULT_UPDATED,
                WebhookEndpoint.CANDIDATE_CREATED,
            ],
            active=True,
            created_at=at(1, 14),
        )
        WebhookEndpoint.objects.create(
            organization=organizations["northgate"],
            url="https://ats-bridge.northgate-financial.example/waypoint",
            secret="whsec_northgate_c091d4e7",
            events=[WebhookEndpoint.RESULT_PUBLISHED],
            active=True,
            created_at=at(1, 20),
        )
        WebhookEndpoint.objects.create(
            organization=organizations["quillon"],
            url="https://quillon-software.example/integrations/waypoint",
            secret="whsec_quillon_7ae30c15",
            events=[WebhookEndpoint.RESULT_PUBLISHED],
            active=True,
            created_at=at(2, 3),
        )
        WebhookEndpoint.objects.create(
            organization=organizations["meridian"],
            url="https://hooks.meridian-freight.example/waypoint",
            secret="whsec_meridian_b6420fd9",
            events=[WebhookEndpoint.RESULT_PUBLISHED],
            active=True,
            created_at=at(2, 17),
        )

    # ------------------------------------------------------------- data build

    def _assessment(self, organization, name, pass_mark, created):
        return Assessment.objects.create(
            organization=organization,
            name=name,
            max_score=100,
            pass_mark=pass_mark,
            created_at=created,
        )

    def _candidate(self, organization, index, full_name, created):
        slug = organization.slug
        return Candidate(
            organization=organization,
            external_ref=f"cnd_{slug}_{index:04d}",
            full_name=full_name,
            email=(
                full_name.lower()
                .replace(" ", ".")
                .replace("'", "")
                + f".{index}@{slug}-candidates.example"
            ),
            created_at=created,
        )

    def _reports(self, organization, assessment, rows, graded_at):
        """`rows` is a list of (full_name, raw_score). Returns the saved reports."""
        start = Candidate.objects.filter(organization=organization).count() + 1
        candidates = [
            self._candidate(organization, start + offset, name, graded_at - dt.timedelta(days=7))
            for offset, (name, _) in enumerate(rows)
        ]
        Candidate.objects.bulk_create(candidates)
        candidates = list(
            Candidate.objects.filter(
                organization=organization,
                external_ref__in=[c.external_ref for c in candidates],
            ).order_by("external_ref")
        )

        sequence = ScoreReport.objects.count() + 1
        reports = [
            ScoreReport(
                organization=organization,
                assessment=assessment,
                candidate=candidate,
                raw_score=score,
                status=ScoreReport.GRADED,
                partner_ref=f"prt_{sequence + offset:06d}",
                created_at=graded_at - dt.timedelta(days=1),
                graded_at=graded_at,
            )
            for offset, (candidate, (_, score)) in enumerate(zip(candidates, rows))
        ]
        ScoreReport.objects.bulk_create(reports)
        return list(
            ScoreReport.objects.filter(
                partner_ref__in=[r.partner_ref for r in reports]
            ).order_by("partner_ref")
        )

    def _random_rows(self, count, na_count=0):
        rows = []
        for _ in range(count - na_count):
            name = f"{self.rng.choice(FIRST_NAMES)} {self.rng.choice(LAST_NAMES)}"
            rows.append((name, str(self.rng.randint(4, 100))))
        for _ in range(na_count):
            name = f"{self.rng.choice(FIRST_NAMES)} {self.rng.choice(LAST_NAMES)}"
            rows.append((name, "n/a"))
        return rows

    def _release_individually(self, reports, published_at, spread_minutes=90):
        for offset, report in enumerate(reports):
            publish_report(report)
            moment = published_at + dt.timedelta(
                minutes=(offset * spread_minutes) % (60 * 24)
            )
            self.stamps[report.id] = (moment, moment)

    def _leave_graded(self, reports, graded_at):
        for report in reports:
            self.stamps[report.id] = (graded_at, None)

    # ------------------------------------------------------------- customers

    def _volta(self, organization):
        first = self._assessment(
            organization, "Embedded C — Screen (June 2026)", 60, at(4, 2)
        )
        second = self._assessment(
            organization, "Firmware QA — Screen (June 2026)", 55, at(4, 2)
        )

        early = self._reports(organization, first, self._random_rows(36, na_count=2), at(5, 18, 8))
        self._release_individually(early, at(5, 20, 9), spread_minutes=240)

        late_first = self._reports(
            organization, first, self._random_rows(114, na_count=6), at(5, 27, 8)
        )
        self._release_individually(late_first, at(5, 29, 10), spread_minutes=95)

        late_second = self._reports(
            organization, second, self._random_rows(150, na_count=7), at(6, 1, 8)
        )
        self._release_individually(late_second, at(6, 2, 9), spread_minutes=70)

    def _northgate(self, organization):
        assessment = self._assessment(
            organization, "Java Backend — Phase 1 (June 2026)", 60, at(5, 6)
        )

        steady = self._reports(
            organization, assessment, self._random_rows(60, na_count=3), at(6, 1, 7, 30)
        )
        self._release_individually(steady, at(6, 1, 11), spread_minutes=110)

        batch = self._reports(
            organization, assessment, self._random_rows(48, na_count=2), at(6, 3, 9, 12)
        )
        publish_reports([report.id for report in batch])
        for report in batch:
            self.stamps[report.id] = (at(6, 3, 9, 12), at(6, 9, 15, 4))

        pair = self._reports(
            organization, assessment, self._random_rows(2), at(6, 3, 9, 12)
        )
        self._release_individually(pair, at(6, 10, 11, 20), spread_minutes=6)

        waiting = self._reports(
            organization, assessment, self._random_rows(10, na_count=1), at(6, 10, 7, 45)
        )
        self._leave_graded(waiting, at(6, 10, 7, 45))

    def _lakeshore(self, organization):
        screen = self._assessment(
            organization, "Backend Engineer — Screen (June 2026)", 60, at(5, 28)
        )
        analyst = self._assessment(
            organization, "Data Analyst — Screen (May 2026)", 65, at(4, 30)
        )

        cohort = self._reports(organization, screen, LAKESHORE_COHORT, at(6, 6, 18, 40))
        self._leave_graded(cohort, at(6, 6, 18, 40))

        earlier = self._reports(
            organization, analyst, self._random_rows(34, na_count=2), at(5, 11, 8)
        )
        self._release_individually(earlier[:22], at(5, 12, 10), spread_minutes=130)
        self._leave_graded(earlier[22:], at(5, 11, 8))

    def _filler(self, organization):
        first = self._assessment(
            organization, "Software Engineer — Screen (May 2026)", 60, at(4, 8)
        )
        second = self._assessment(
            organization, "Technical Support — Screen (June 2026)", 55, at(5, 4)
        )

        graded_first = self._reports(
            organization, first, self._random_rows(40, na_count=2), at(5, 14, 8)
        )
        self._release_individually(graded_first[:30], at(5, 15, 10), spread_minutes=150)
        self._leave_graded(graded_first[30:], at(5, 14, 8))

        graded_second = self._reports(
            organization, second, self._random_rows(40, na_count=3), at(6, 4, 8)
        )
        self._release_individually(graded_second[:26], at(6, 5, 10), spread_minutes=115)
        self._leave_graded(graded_second[26:], at(6, 4, 8))

    # --------------------------------------------------------------- finalise

    def _apply_timestamps(self):
        for report_id, (updated_at, published_at) in self.stamps.items():
            if published_at is None:
                ScoreReport.objects.filter(pk=report_id).update(updated_at=updated_at)
                continue
            ScoreReport.objects.filter(pk=report_id).update(
                updated_at=updated_at, published_at=published_at
            )
            WebhookDelivery.objects.filter(report_id=report_id).update(
                created_at=published_at
            )

    def _delivery_outcomes(self, organizations):
        retired = at(5, 29, 0, 0)
        volta = WebhookDelivery.objects.filter(
            endpoint__organization=organizations["volta"]
        )
        volta.filter(created_at__lt=retired).update(status_code=200, attempts=1)
        volta.filter(created_at__gte=retired).update(status_code=410, attempts=5)

        WebhookDelivery.objects.exclude(
            endpoint__organization=organizations["volta"]
        ).update(status_code=200, attempts=1)
