# SOLUTIONS — sealed answer key

**Stop here if the hour isn't up.** Reading this early costs you the exercise.

Every fix below was applied to a clean copy of this repo. The suite went from
**10 failed / 11 passed** to **21 passed**. No test was modified to get there.

Three bugs, across the areas the interview brief names: a write-path API bug, a
framework-side-effect bug that shows up on two integration surfaces at once, and
a data-type bug in SQL. **Two of the three have a second defect behind the
first**, and in both cases the obvious fix goes partly green while leaving the
customer's actual problem in place.

---

## Bug 1 — TICKET-6601 — a `200` for a write that was thrown away

**Where:** `api/serializers.py`, `WebhookEndpointSerializer`.

**Reproduce** (needs the dev server):

```bash
K="Authorization: Api-Key wp_live_volta_3d81f4a9c2"
curl -s -X PATCH -H "$K" -H "Content-Type: application/json" \
  -d '{"events":["result.published"]}' localhost:8000/api/v1/webhooks/1/
# HTTP 200
# {"id":1,"url":"https://hooks.volta-automotive.example/waypoint",
#  "events":["result.published","result.updated","candidate.created"], ...}
```

200, and the body it hands back still contains all three event types. Nothing
was written.

### Root cause, part one — a `SerializerMethodField` is read-only, always

```python
class WebhookEndpointSerializer(serializers.ModelSerializer):
    events = serializers.SerializerMethodField()
```

`SerializerMethodField` has no `to_internal_value`; DRF marks it `read_only` and
**strips it out before validation**. `validated_data` never contains `events`,
so `ModelSerializer.update()` never touches the column. There is no error to
raise, because from DRF's point of view nothing was submitted.

Whoever added it was formatting the output. Read-only was a side effect they did
not intend and the framework did not mention.

### Root cause, part two — and this is the one that caused the outage

Volta's config script does not send `url`. It sends **`target_url`**, the field
name from our v0 API. And DRF **silently discards keys the serializer does not
declare**:

```bash
curl -s -X PATCH -H "$K" -H "Content-Type: application/json" \
  -d '{"target_url":"https://ingest.volta-automotive.example/v2/waypoint"}' \
  localhost:8000/api/v1/webhooks/1/
# HTTP 200, url unchanged
```

So there are **two independent reasons** their PATCH did nothing, and they have
identical symptoms. `url` is a perfectly ordinary writable field — a PATCH that
actually names `url` works, and `test_patching_the_url_changes_it` passes
throughout. If you fix only the method field, `events` starts working, the
customer's script still cannot move the URL, and you have shipped them another
two weeks of 410s.

`test_a_payload_we_cannot_apply_is_rejected` is the one that stays red until you
fix the second half. That is deliberate.

### Fix

```python
class StrictFieldsMixin:
    """Refuse any payload carrying a key this serializer cannot apply."""

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if not isinstance(self.initial_data, dict):
            return attrs
        writable = {name for name, field in self.fields.items() if not field.read_only}
        unknown = set(self.initial_data) - writable
        if unknown:
            raise serializers.ValidationError(
                {name: "This field cannot be written." for name in sorted(unknown)}
            )
        return attrs


class WebhookEndpointSerializer(StrictFieldsMixin, serializers.ModelSerializer):
    events = serializers.ListField(
        child=serializers.ChoiceField(choices=WebhookEndpoint.EVENT_TYPES),
        allow_empty=True,
    )

    class Meta:
        model = WebhookEndpoint
        fields = ("id", "url", "events", "active", "created_at")
        read_only_fields = ("created_at",)
```

Two things happened here and both matter. `events` became writable *and
validated* — a `ChoiceField` child means a typo'd event name is now a 400 rather
than a subscription that silently never fires. And unknown keys are refused, so
the class of bug ends rather than this instance of it.

### The principle worth stating out loud

**An API that ignores what it cannot apply is worse than one that fails.** A 400
costs the customer one deploy. A 200 that means nothing cost Volta two weeks and
264 events, and it burned our own support time too — our engineer confirmed "the
endpoint still shows the old URL" on 10 June and read that as evidence of
replication lag rather than as the answer.

DRF's default (ignore unknown keys) is a deliberate compatibility choice and it
is fine for optional read filters. On a configuration write it is a trap. This
is worth raising as a platform-wide question, not a one-serializer patch: every
write endpoint we own has the same default.

### Blast radius — and the honest limit on it

Volta: **264 `result.published` events undelivered between 2026-05-29 and
2026-06-11**, all to a host returning 410. They are in `WebhookDelivery` with
`status_code=410`, so they can be re-driven once the URL is corrected — nothing
was lost, only undelivered.

For everyone else, be honest: **we cannot tell from the logs who else hit this.**
We log the method, path and status of a PATCH, never the body, so a request whose
fields were silently dropped is indistinguishable in the log from one that
applied cleanly. All we can say is that no endpoint's `events` list has changed
via the API since the method field shipped. Saying "I can bound this for Volta
but not for the fleet, and here is exactly why" is the correct answer, and it
doubles as the argument for the guardrail: **log the keys we rejected or
ignored.**

### What was a red herring

The internal note's replica-lag theory. There is one SQLite database and no
replica; the GET was reading the same row the PATCH claimed to have written.
Worse, the note's advice — "wait 24h and re-check" — is what turned a one-day
ticket into a two-week outage. Volta's own framing ("either your API is lying or
something is reverting it") is the more accurate of the two, and the first half
of it is right.

### Escalation note

```
REPRO:      PATCH /api/v1/webhooks/1/ with {"events":[...]} -> 200, unchanged.
            PATCH with {"target_url":"..."} -> 200, unchanged. PATCH with
            {"url":"..."} -> 200, changed.
IMPACT:     Volta: 264 result.published events undelivered since 2026-05-29
            (410 from the host they retired). Any customer changing `events`,
            or using the v0 field name `target_url`, has the same silent no-op.
            We cannot enumerate the latter from logs - we do not log bodies.
HYPOTHESIS: `events` is a SerializerMethodField, which DRF treats as read-only
            and strips before validation, so it never reaches validated_data.
            Separately, DRF silently drops keys the serializer does not declare,
            so `target_url` is discarded too. Both answer 200.
FIX:        Make `events` a validated ListField, and reject payloads containing
            any key we cannot apply with a 400 naming it. Then re-drive the 264
            deliveries. Longer term: apply the strict-fields rule to every write
            serializer, and log ignored keys.
```

### Saying it out loud

> "Your PATCH was never applied, and you were right to distrust the 200. Two
> separate things dropped it. The event list was accidentally configured as a
> read-only field on our side, so we removed it from the request before we ever
> looked at it. And your script sends `target_url`, which was our field name two
> versions ago — our API now ignores field names it doesn't recognise instead of
> rejecting them. Both come back 200, which is our bug, not your integration's.
> Nothing is lost: 264 events are queued against the old host and we'll re-drive
> them once the URL is corrected. We're also changing the API to refuse anything
> it can't apply, so this can't happen quietly again."

Leading with *"you were right to distrust the 200"* and *"nothing is lost"* —
before the DRF mechanics — is the instinct being tested.

---

## Bug 2 — TICKET-6608 — a bulk update that skipped everything `save()` does

**Where:** `core/services.py`, `publish_reports()`.

```python
return (
    ScoreReport.objects.filter(id__in=report_ids, status=ScoreReport.GRADED)
    .update(status=ScoreReport.PUBLISHED, published_at=timezone.now())
)
```

**Reproduce** — read the state Sasha is describing, no writes:

```bash
python manage.py shell -c "from core.models import ScoreReport as S; \
b = S.objects.filter(organization__slug='northgate', published_at__day=9); r = b.first(); \
print(b.count(), r.updated_at, r.published_at, sum(x.deliveries.count() for x in b))"
# 48  2026-06-03 09:12:00+00:00  2026-06-09 15:04:00+00:00  0
```

Released on the 9th. Last changed on the 3rd. Zero deliveries.

### Root cause — `QuerySet.update()` is a SQL `UPDATE`, and nothing else

`.update()` compiles straight to `UPDATE ... SET ... WHERE ...`. It does not
instantiate the model, so:

1. `updated_at = models.DateTimeField(auto_now=True)` never fires. `auto_now`
   lives in `DateTimeField.pre_save()`, which only runs on an instance save.
2. `post_save` never fires, so `core/signals.py::queue_result_published` never
   runs and no `WebhookDelivery` is queued.

**One cause, two symptoms that arrive as separate complaints.** Sasha reported
"Greenhouse has none of them" *and* "we never got the webhook" and reasonably
assumed one network-shaped explanation for both.

The sync symptom is worse than it looks. The connector polls
`?updated_since=<last run>` and the feed filters `updated_at__gt`. Those 48 rows
have an `updated_at` of 2026-06-03, which is **behind every poll the connector
will ever make again**. They are not late. They are permanently invisible to
that feed, and would have stayed invisible forever.

### The customer handed you the experiment

> "on Wednesday I released two more candidates one at a time... both were in
> Greenhouse inside a minute."

The single-report path (`publish_report`) calls `report.save()`, so `auto_now`
runs and the signal fires. Two code paths for one operation, one of them
correct. `logs/app.log` states the difference in two lines:

```
2026-06-09 15:04:02  publish org=northgate action=batch  reports=48 webhooks_queued=0
2026-06-10 11:20:03  publish org=northgate action=single report=prt_000409 webhooks_queued=1
```

followed by fifteen-minute polls returning `results=0`, then `results=2` the
moment two were released individually. **When a customer tells you which two
runs differed, the debugging job is to find what differs between those two code
paths — not to theorise about the network.**

### The partial fix that goes green and still fails the customer

```python
.update(status=..., published_at=now, updated_at=now)   # NOT ENOUGH
```

This is the fix everybody reaches for. It restores `updated_at`,
`test_bulk_publish_advances_updated_at` and the feed test both pass — and
**`test_bulk_publish_queues_one_webhook_per_report` is still red**, because the
signal still never ran. Half the customer's complaint, fixed.

### Fix

```python
@transaction.atomic
def publish_reports(report_ids):
    """Release a batch of graded reports to the customer's ATS."""
    reports = list(
        ScoreReport.objects.filter(id__in=report_ids, status=ScoreReport.GRADED)
    )
    for report in reports:
        publish_report(report)
    return len(reports)
```

Bulk release is now defined as *releasing each report*, which is what the README
oracle says it is, and there is exactly one place where "publish" is implemented.
The `@transaction.atomic` still makes the batch all-or-nothing.

Say the trade-off out loud before someone asks: this is N saves instead of one
UPDATE. For 48 rows inside one transaction that is irrelevant. If batches were
100k, the answer is not to go back to `.update()` — it is to keep the single
definition of publishing and move the fan-out to a task queue. **Correctness
first, then measure.**

### The 48 rows still need fixing

The code fix does nothing for the reports already in the broken state — they are
`published`, so `publish_reports` will not pick them up again. They need a
one-off backfill, and `save()` is enough to do it: `auto_now` advances
`updated_at`, and the signal's `get_or_create` queues each delivery exactly once
without duplicating anything.

```python
import datetime as dt
from core.models import ScoreReport

for report in ScoreReport.objects.filter(
    organization__slug="northgate", published_at__date=dt.date(2026, 6, 9)
):
    report.save()
```

Naming the backfill unprompted is a large part of the signal here. A fix that
leaves the reported records broken has not closed the ticket.

### Blast radius

Every customer who has ever used the batch release screen, for as long as it has
shipped — their bulk-released reports are absent from their sync feed
permanently and generated no webhooks. Northgate is the one who noticed. The
query to enumerate it is
`ScoreReport.objects.filter(status="published", updated_at__lt=F("published_at"))`:
a published report whose last-changed time predates its own release is, by
definition, one that was released without being saved.

That predicate is also the **guardrail** worth proposing — a database constraint
or a monitoring check on `updated_at >= published_at` catches this class of bug
without anyone having to remember the rule.

### What was a red herring

The internal note's firewall theory. It is superficially attractive — a burst of
48 webhooks versus a trickle of 2 — and it is refuted by our own data before you
ever contact the customer: **we never attempted the 48 deliveries.** There are no
`WebhookDelivery` rows and no delivery attempts in the log. A firewall drop
would show as attempts with a timeout or a 5xx. "We didn't fail to deliver, we
never tried" ends that theory in one sentence, and it is the difference between
sending the customer on a two-day network-forensics detour and answering them.

### Escalation note

```
REPRO:      48 Northgate reports have status=published, published_at=2026-06-09
            15:04, updated_at=2026-06-03 09:12, and zero WebhookDelivery rows.
            Releasing one report individually produces both correctly.
IMPACT:     Every customer using batch release, since it shipped. Bulk-released
            reports are invisible to ?updated_since= permanently (their
            updated_at is older than any future poll) and queue no webhooks.
            Northgate: 48 candidates, hiring decisions blocked since 09 June.
HYPOTHESIS: publish_reports uses QuerySet.update(), which is a plain SQL UPDATE:
            auto_now on updated_at is never applied and post_save never fires,
            so neither the sync feed nor the webhook fan-out sees the change.
            publish_report() uses save() and is unaffected.
FIX:        Publish through the model save path so both bulk and single release
            take the same route. Backfill the 48 with report.save() - the
            signal's get_or_create makes that safe to re-run. Add a check on
            updated_at >= published_at so this cannot recur silently.
```

### Saying it out loud

> "The 48 are genuinely released — that part of your screen is telling you the
> truth, and nothing needs re-releasing by hand. What went wrong is everything
> that was supposed to happen *because* of the release. When results are released
> in a batch we take a shortcut that writes the new status straight to the
> database, and that shortcut skips both the 'last changed' stamp your bridge
> polls on and the step that queues your webhook. So your bridge asks 'anything
> new since 3pm?' and these records still say they last changed on the 3rd —
> which is also why waiting doesn't help. Releasing one at a time takes a
> different path that does both properly, which is exactly why your Wednesday
> test worked. We're making the batch path do what the single path does, and
> we'll push your 48 through today. Your firewall is fine — we never attempted
> those deliveries at all."

*"Your firewall is fine — we never attempted those deliveries"* is the sentence
that repairs the trust our internal note was about to spend.

---

## Bug 3 — TICKET-6613 — a number stored as text, compared as text

**Where:** `core/models.py` (`ScoreReport.raw_score` is a `CharField`), used in
`reporting/shortlist.py` **and** `reporting/pass_rates.py`.

**Reproduce:**

```bash
curl -s -H "Authorization: Api-Key wp_live_lakeshore_9a54f1bb37" \
  localhost:8000/api/v1/shortlists/4/
# 23 candidates; the first six are "n/a"; "9" sits between 91 and 88;
# Nadia Farouk (100) is absent
```

### Root cause — string comparison, in both directions

`raw_score` holds the partner's value verbatim in a `CharField`, so every
comparison against it is lexicographic:

| Value | `>= "60"` as text | Should be |
|---|---|---|
| `"100"` | **False** — `'1' < '6'` | True |
| `"98"` | True | True |
| `"9"` | **True** — `'9' > '6'` | False |
| `"60"` | True | True |
| `"6"` | False — `"6"` is a shorter prefix of `"60"` | False |
| `"n/a"` | **True** — `'n' > '6'` | excluded |

One comparison, wrong in **both** directions: it excludes the best candidate in
the cohort and admits a 9 and six people who never sat the test. Sorting has the
same defect — descending text order puts `"n/a"` above everything, then
`98, 96, 94, 91, 9, 88, …`, which is exactly the list Tess is reading.

Note there is no explicit `str()` anywhere. `filter(raw_score__gte=assessment.pass_mark)`
passes an **int**, and Django's `CharField.get_prep_value()` coerces it to
`"60"`. In the raw SQL, SQLite applies the column's TEXT affinity to the bound
parameter and compares as text for the same reason. Both call sites do the wrong
thing without anyone writing anything that looks wrong.

Tess's arithmetic is right, including the parts she was least sure of:

| | Reported | Truth |
|---|---|---|
| Shortlist size | 23 | **17** |
| Pass rate | 53.5% | **46.0%** (17 of 37) |
| Average score | 45.84 | **53.27** |
| Not attempted | 0 | **6** |

The average is dragged down because SQLite's `AVG` on a text column coerces
`'n/a'` to `0.0` and averages over all 43 rows: `1971 / 43 = 45.84`, where the
true figure is `1971 / 37 = 53.27`.

### The fix everyone reaches for is also wrong

`CAST(raw_score AS INTEGER)` on its own **passes some tests and creates a new
bug**: SQLite's `CAST('n/a' AS INTEGER)` is `0` — silently, no error. The six
no-shows stop being top-ranked and become bottom-ranked zeros, which is still
wrong (they are not zero-scorers, they are not scorers), and they stay in the
average and the denominator. Worth naming explicitly: **the same cast raises on
Postgres.** A fix whose safety depends on the database engine's tolerance for
garbage is not a fix.

`test_reports_with_no_numeric_score_are_not_counted_as_zero` is the test that
holds the line here.

### Fix — exclude non-numeric values explicitly, then compare as numbers

```python
# reporting/shortlist.py
from django.db.models import IntegerField
from django.db.models.functions import Cast

NUMERIC = r"^[0-9]+$"

def scored_reports(assessment):
    return considered_reports(assessment).filter(raw_score__regex=NUMERIC).annotate(
        score=Cast("raw_score", IntegerField())
    )

def shortlist(assessment):
    qualified = scored_reports(assessment).filter(score__gte=assessment.pass_mark)
    return [... for report in qualified.order_by("-score", "candidate__full_name")]
```

```sql
-- reporting/pass_rates.py
SELECT COUNT(*)                                                     AS reports,
       SUM(CASE WHEN r.raw_score GLOB '[0-9]*' THEN 0 ELSE 1 END)   AS not_attempted,
       SUM(CASE WHEN r.raw_score GLOB '[0-9]*'
                 AND CAST(r.raw_score AS INTEGER) >= %s
                THEN 1 ELSE 0 END)                                  AS passed,
       AVG(CASE WHEN r.raw_score GLOB '[0-9]*'
                THEN CAST(r.raw_score AS INTEGER) END)              AS average_score
```

`AVG` ignores NULL inputs, so the `CASE` with no `ELSE` removes the no-shows from
the average rather than zeroing them.

### There are two call sites, and one test exists to catch you missing one

`test_the_summary_agrees_with_the_shortlist` **passes on the shipped code** —
both call sites are wrong in the same way, so they agree with each other at 23.
Fix the ORM and forget the raw SQL and it **turns red**, because now the
dashboard says 23 and the shortlist says 17. A test that starts green and breaks
when you half-fix something is doing its job; if you see a green test go red
after a change, that is information, not noise.

The general habit: when you find a wrong comparison against a column, **grep for
every other use of that column before you fix the one you found.**

### The real fix, which you should propose rather than do under the clock

`raw_score` should not be a `CharField`. The durable fix is a migration to a
nullable `IntegerField` plus an explicit `attempted` flag, with validation at the
ingest endpoint so a non-numeric score is rejected or recorded as a non-attempt
at the boundary rather than stored and re-interpreted by every reader. Every
patch above is a reader compensating for a writer that accepted anything.
"No score" and "a score of zero" are different facts; storing them in the same
column guarantees this bug class recurs.

### What was a red herring — and it would have cost real money

**Tess's conclusion is wrong and her proposed remedy would have achieved
nothing.** The grades are correct. Every one of the 43 reports holds exactly what
the partner delivered — `logs/app.log` confirms the delivery
(`delivered=43 attempted=37 not_attempted=6`) and the numbers she counted by hand
match the stored values. Re-running the cohort through the grading partner would
have cost a night, partner fees and candidate goodwill, and produced the same
wrong shortlist, because nothing about the read path would have changed.

Support's internal note repeats her theory back to her — *"the scores in the
database look wrong"* — which is the one thing that is demonstrably not true.
Take the arithmetic, reject the conclusion.

### Blast radius

Every assessment, every customer, every shortlist and dashboard summary, for as
long as this has shipped. It bites hardest wherever scores span a digit boundary
(any cohort containing both a 100 and a two-digit score) or where the partner
delivered `n/a`. Reporting only — **no grade was altered and no candidate's score
is wrong in the database.** Nothing needs re-running; the shortlists that were
acted on need re-issuing.

That last distinction is the one to lead with. Tess is deciding tonight whether
to spend money on a re-grade.

### Escalation note

```
REPRO:      GET /api/v1/shortlists/4/ returns 23 candidates: six with raw_score
            "n/a" ranked top, one with "9" ranked 11th, and "100" absent.
            pass-rates reports 53.5% and average 45.84 against a true 46.0% /
            53.27 over 37 attempts.
IMPACT:     Every assessment and every customer. Shortlists mis-ranked and
            mis-membered wherever scores cross a digit-length boundary or a
            candidate did not attempt. Lakeshore are making offers on Monday
            from this list. Read path only - no stored grade is wrong.
HYPOTHESIS: raw_score is a CharField, so `>= pass_mark` and ORDER BY compare as
            text: "9" > "60", "100" < "60", "n/a" > "60". AVG additionally
            coerces "n/a" to 0 and averages it in. Same defect in both the ORM
            shortlist and the raw-SQL summary.
FIX:        Exclude non-numeric scores explicitly, then cast and compare as
            integers, in both call sites. Do NOT cast alone - CAST('n/a') is 0
            on SQLite. Propose migrating raw_score to a nullable IntegerField
            with an `attempted` flag and validation at ingest. No re-grade is
            needed; re-issue the affected shortlists.
```

### Saying it out loud

> "Please don't re-grade — the scores are all correct, and re-running the cohort
> would give you the same wrong list. This is entirely about how we sort and
> filter them. We stored those scores as text rather than as numbers, and text
> compares character by character: '9' comes after '6', so a 9 looks bigger than
> 60; '100' starts with a 1, so it looks smaller than everything; and 'n/a',
> which is what we record when someone doesn't sit the assessment, comes after
> every digit, which is why your six no-shows are at the top. Same reason the
> average is low — the no-shows were being counted as zeros. It affects every
> customer, not just you. Nobody's score changed, and we'll have you a corrected
> shortlist today."

Answering the re-grade question in the first six words, before any explanation,
is the whole test on this ticket.

---

## The symptom collisions

Built in deliberately. Interviewers probe exactly here.

**"You told us it worked and it didn't"** — tickets 6601 and 6608. They are
opposites, and one question separates them: **did the row change?**

- **6601:** the write never happened. The input was discarded at the edge of the
  system, before any business logic ran. The stored row is untouched.
- **6608:** the write absolutely happened — `status` is `published` and
  `published_at` is correct. What is missing is everything that was supposed to
  happen *as a consequence*: the timestamp, the event.

"Nothing was written" and "everything was written except the side effects" need
completely different investigations. Look at the row first; it answers this in
one query.

**"Records you sent us never arrived"** — 6601 and 6608 again, from the
customer's side. In 6601 the events were queued and attempted and rejected by
*their* host, so we have 264 rows of evidence and can re-drive them. In 6608
there is nothing to re-drive because nothing was ever queued. **Delivered-and-
failed versus never-attempted is the first thing to check on any "we didn't get
it" report**, and it lives in the delivery table, not in the customer's firewall.

**"The list is wrong"** — 6608 and 6613. One is missing records that exist and
are correct; the other contains the right records ranked and filtered by a broken
comparison. 6608 is a write-path bug with a read-path symptom; 6613 is purely
read-path. Fixing either moves the other not at all.

---

## Scorecard

| | Bug 1 (silent 200) | Bug 2 (bulk update) | Bug 3 (text score) |
|---|---|---|---|
| Found it from the symptom, not by grepping | | | |
| Quoted the rule from README before editing | | | |
| Reproduced it before fixing | | | |
| Checked what was still red after the first fix | | | |
| Rejected the wrong theory in the internal note | | | |
| Handled the already-broken data, not just the code | | | |
| Explained it to the customer without jargon | | | |
| Named the guardrail, not "more tests" | | | |

- **Bug 1** is the one where two independent causes produce one symptom, and
  fixing the visible one leaves the outage running.
- **Bug 2** is the one where the customer ran the experiment for you, and where
  the obvious fix goes green on three tests and still ships half the bug.
- **Bug 3** is the one where the reporter's arithmetic is right, her conclusion
  is wrong, and acting on her request would have cost money and fixed nothing —
  and where a test that was green before your change turns red if you fix only
  one of the two call sites.

## Retro

- Did you find each one from the **symptom**, or by grepping for something
  suspicious?
- For each bug, did you deal with the **data already in the broken state**, or
  only the code?
- Which ticket did you nearly close after the first green test, and what would
  the customer have said the next day?
- Can you explain each root cause to the reporter in two sentences with no
  jargon?

## A harder second pass

Re-arm with `git checkout -- api core reporting dashboard`, then delete the
`tests/` directory and work the three tickets from the complaints and
`logs/app.log` alone. That is the version of this that matches the actual job.
