# Waypoint — support escalation drill

Waypoint connects a hiring platform to the applicant tracking systems its
customers run. Grading partners deliver score reports into our public API,
recruiters release those results, and we push them into the customer's ATS —
over webhooks, and over an incremental sync feed their connector polls. Our own
dashboard ranks each cohort into a shortlist and reports how it performed.

It is the morning of **12 June 2026**. **Three escalations are open. All three
are real.** Your job is to reproduce each one, find the cause, fix it, and be
able to explain it out loud to the person who reported it.

Budget **60 minutes** — roughly 15 minutes a ticket, leaving time to write up
your findings. If you are stuck past 20 minutes on one, move on and come back;
that decision is part of the drill.

---

## Setup

```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt     # Linux/macOS: .venv/bin/pip

.venv/Scripts/python manage.py migrate
.venv/Scripts/python manage.py seed_demo
.venv/Scripts/python -m pytest -q                 # expect: 10 failed, 11 passed
.venv/Scripts/python manage.py runserver          # http://127.0.0.1:8000/
```

If you get anything other than **10 failed / 11 passed**, the environment is
off. Fix that before you start the clock.

Three pages are worth having open: `/` is the shortlist and the cohort summary
behind it, `/releases/` is what has been pushed to the ATS, and `/webhooks/` is
the endpoint configuration and recent deliveries.

Sign-ins are `tobrien / waypoint` (Lakeshore Media), `sfrye / waypoint`
(Northgate Financial), `dmoreau / waypoint` (Volta Automotive) and
`wpops / waypoint` (superuser). Live API keys are in
`core/management/commands/seed_demo.py`.

> **Every bug here has at least one failing test — and a green suite is still
> not the finish line.** Two of the three have a second defect behind the first,
> and the obvious fix takes some tests green while leaving the customer's actual
> problem in place. Read what is still red after each change.

`logs/app.log` is a slice of production logging over the period the tickets
cover. It is a second evidence channel, and for at least one ticket it is a
faster route in than the source.

---

## The rules the code is supposed to implement

This section is the **oracle**. When something looks wrong, the question is not
"what does the code do" but "what does this section say it should do."

**Writes.** A `200` on a write means every field the caller sent was applied and
the body reflects what is now stored. A request carrying a field we do not
apply — because it is unknown to us, or because it is not writable — is refused
with `400` naming that field. We never answer success for a change we did not
make.

**Releasing results.** A report is released the same way however it is
released. Releasing it moves its last-changed time to the moment of release,
makes it visible to anyone polling the incremental feed from an earlier
timestamp, and queues exactly one `result.published` event for every active
endpoint subscribed to it. **Releasing a batch is releasing each report in it** —
one at a time and fifty at once must be indistinguishable from the outside.

**The incremental feed.** `GET /api/v1/results/?updated_since=<T>` returns every
report whose state changed after `T`, oldest change first. A connector that
polls with the timestamp of its last successful run sees every change exactly
once.

**Scores.** A score is a number. Ranking, the pass mark, and averages all
compare it as one. Grading partners deliver `n/a` for a candidate who did not
attempt the assessment; **that is not a score of zero.** It is excluded from the
ranking, from the pass-mark comparison and from the average, and reported
separately as not attempted.

**Tenancy.** Every API response is scoped to the organization that owns the
credential on the request, and one customer's configuration is not reachable
with another customer's key.

---

## Open tickets

### TICKET-6601 — Volta Automotive — "Your API told us the change was applied. It wasn't."
**Severity: high.** Two weeks of results never reached their ATS.

> Daniel Moreau, Integrations Lead, Volta Automotive:
>
> "On 29 May we moved our webhook receiver to a new host and retired the old
> one. Our config script does what it has always done: `PATCH` the endpoint with
> the new URL and the shorter event list — we only want `result.published` now,
> the other two were noise. It got a **200**. It has got a 200 every time it has
> run since, and it runs on every deploy.
>
> Your side is still calling the host we retired on 29 May. That host returns
> **410 Gone** and has done for two weeks. Your dashboard shows the old URL and
> all three event types, exactly as before.
>
> So either your API is lying to us about applying the change, or something is
> reverting it. Which is it? And what happens to the results we've missed?"

**Internal note (support):** Confirmed the endpoint still shows the old URL on
our side (10 June). No errors in the API logs — all their PATCHes are 200s.
Possibly read-replica lag or their script caching a stale response; suggested
they wait 24h and re-check.

---

### TICKET-6608 — Northgate Financial — "48 released candidates never reached Greenhouse"
**Severity: high.** Hiring decisions blocked, customer chasing daily.

> Sasha Frye, Talent Operations, Northgate Financial:
>
> "On Tuesday afternoon I released the whole Java Backend batch — 48 candidates
> — from the releases screen. Your UI said released, and the dashboard shows all
> 48 as released with Tuesday's date on them.
>
> Greenhouse has none of them. Our bridge polls you every 15 minutes with the
> timestamp of its last run, and it has come back empty every single time since.
> We also never got the webhook we normally get.
>
> Here's the part I can't explain: on Wednesday I released **two** more
> candidates one at a time from their individual pages, and both were in
> Greenhouse inside a minute. Same assessment, same recruiter, same bridge.
>
> Are the 48 actually released or not?"

**Internal note (support):** Their bridge is on a self-hosted box behind a
corporate firewall. The single releases got through and the batch didn't, so
this smells like their firewall dropping the burst of webhook traffic. Asked
them to whitelist our egress range and re-test.

---

### TICKET-6613 — Lakeshore Media — "Your scoring engine is broken — re-grade the cohort"
**Severity: high.** Customer is making hiring decisions off this today.

> Tess O'Brien, Head of Talent, Lakeshore Media:
>
> "I pulled the shortlist for the June backend screen this morning and it is
> nonsense. There are **23 people on it**. Six of them **never sat the
> assessment** — they're at the very top of the list. Someone who scored **9** is
> above candidates who scored in the eighties.
>
> And Nadia Farouk, who got **100** — the best result we've had this cycle, I saw
> the report myself — **isn't on the shortlist at all.**
>
> Your dashboard also tells me 53% of the cohort passed and the average was 45.8.
> I counted by hand from the reports: 37 people actually sat it, 17 of them made
> the 60 mark. That's 46%, not 53%.
>
> Your grading is clearly broken. Can you re-run the whole cohort through the
> partner tonight? We're supposed to be sending offers Monday."

**Internal note (support):** Tess's numbers check out against the raw reports,
so the scores in the database look wrong. Recommend we take her up on the
re-grade and re-run the cohort with the partner this evening.

---

## What "done" looks like

1. **`pytest -q` is green.** Do not edit a test to make it pass — fix the code
   underneath. And when something goes green, check what is still red before
   moving on: on two of these tickets the first fix is not the whole fix.
2. **You can reproduce each bug before you fix it** — a `curl`, a shell
   one-liner, a click in the UI. Being able to *show* a bug is worth more than
   guessing it.
3. **You have written an escalation note for each ticket.** This is half the
   exercise.

```
REPRO:      the smallest exact sequence that shows the bug
IMPACT:     who is affected, how many, and what it costs them
HYPOTHESIS: the mechanism, stated so an engineer can confirm or kill it in one read
FIX:        what you changed, or what you'd propose and why
```

A good hypothesis names the **mechanism** ("the field is read-only on the
serializer, so the value is dropped before it is ever written") rather than the
symptom ("the change doesn't save"). Aim for that.

## Things worth noticing

- **Every internal note above points at the wrong layer**, and one of them
  proposes an action that would cost the customer real money and fix nothing.
- One ticket is answered by comparing two things the system did that should have
  been identical, and were not. The customer has already told you which two.
- Two of these tickets reduce to "records we sent you never arrived" and they
  have nothing in common beyond that sentence. Being able to say why, in one
  line each, is exactly what gets probed.
- One customer has done the arithmetic for you and drawn the wrong conclusion
  from it. Both halves of that matter: take the numbers, reject the conclusion.
- After you fix something and a test goes green, ask what *else* could produce
  the same symptom before you move on.

## Stretch goals

- For TICKET-6601: establish the blast radius. How many events were affected,
  over what window, and which of them can still be re-delivered?
- For TICKET-6613: the customer wants a re-grade tonight. Write the two
  sentences that talk her out of it without dismissing her.
- For each ticket: name the **specific** guardrail that would have caught this
  before a customer did. Not "more tests" — the actual mechanism.
- For TICKET-6601 and TICKET-6608: both are cases of the system reporting
  success for work it did not do. Is that one class of bug or two?

## When you're done

`SOLUTIONS.md` is the answer key: root cause per bug, a model escalation note,
notes on how to explain each one out loud, and a scorecard.

**Don't open it until you've finished or the hour is up.** Reading it early
costs you the entire value of the exercise.

To re-arm the drill after solving: `git checkout -- api core reporting dashboard`
