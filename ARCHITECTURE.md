# Partner certification platform: architecture note

Open edX [Verawood](https://docs.openedx.org/en/latest/community/release_notes/verawood.html), [Tutor v22](https://docs.tutor.edly.io). ERD and diagrams: [docs/erd.md](docs/erd.md),
[docs/diagrams.md](docs/diagrams.md), kept out of the note to protect the page budget.

## 1. What I decided for you

**A track is a program, and a standard is a bar rather than a checklist.** The brief pairs
"courses taken in order" with "granted on passing a standard, not on finishing every course".
One model: ordered steps, each required or optional, plus a rule for passing. I assumed the
rule is a weighted grade threshold across required steps plus a minimum count from optional
groups, which is the shape my [Proposed Catalog Plugin](https://openedx.atlassian.net/wiki/spaces/OEPM/pages/5026938891/Proposed+Catalog+Plugin) already argues for: "Complete all 2
courses in Core Courses AND Complete at least 1 of 2 courses in Specialization Courses."

**Tiers are ranked, so the gate is a comparison**, not a lookup table:
`learner.tier.rank >= track.required_tier.rank`. One integer column, and tier becomes a
business object the client extends without a deploy.

**Tier is granted, not derived.** Derived from grades, a re-scored course would silently
demote someone mid-track.

**A learner sits under one coach at a time**, a nullable foreign key rather than a membership
table. The decision most likely to be wrong: co-coaching, handovers or history need a
membership table with dates. I would rather add it when asked than carry it empty.

**Joining a track enrolls the learner in its course steps**, otherwise joining is not
observable and progress has nothing to read.

The call that could most reasonably have gone the other way is not building on
[`learning_paths`](https://github.com/open-craft/learning-paths-plugin), below. Without vendor steps, adopting it and patching its gaps wins.

## 2. Approach

**Leave [course-discovery](https://github.com/openedx/course-discovery) alone.** Its programs are catalogue metadata in a separate service with
its own database, while every query here joins to LMS enrollment, grades and completion. That
boundary is what puts the two-second coach view out of reach. It is also the deprecated direction:
the Proposed Catalog Plugin exists to replace discovery with an in-LMS Django plugin, and this is
that pattern applied to a single client.

**Native stackable pathways are not in Verawood; they are announced for [Willow](https://docs.openedx.org/en/latest/community/release_notes/willow.html), December 2026.**
[`open-craft/learning-paths-plugin`](https://github.com/open-craft/learning-paths-plugin) exists today, but its step is a `CourseKeyField` (no vendor or
unbuilt steps), its `level` is unenforced (no tier gate), and its visibility is `invite_only` plus
`is_staff` (no partner scoping). So build alongside it, keeping Track isomorphic so Willow is a
migration, not a redesign.

**One Tutor plugin, one LMS Django app** via the `lms.djangoapp` entry point, no fork. To change
platform behaviour: filter, then our own method called from core, then monkey-patch, then subclass,
the ladder [WikiLearn](https://github.com/wikimedia/tutor-contrib-wikilearn) used to retire four forks.

**Coach view:** a denormalised rollup, one row per learner per track, written by receivers, so
1200 rows come off one index on `(coach_group, track)` instead of being aggregated per request.
Live aggregation cannot reach two seconds on a phone; the price is seconds of staleness.

**In-course:** a [`frontend-app-learning`](https://github.com/openedx/frontend-app-learning) plugin slot showing tier, distance to the standard and a
contact-coach action, so no course content changes.

**Landing page:** `student_dashboard()` redirects `/dashboard` to
`settings.LEARNER_HOME_MICROFRONTEND_URL` whenever the `learner_home_mfe.enabled` waffle flag is
on, so pointing that setting at our page and turning the flag on is the whole change. Both are
this plugin's: a settings patch and an init task. The header tab is inline JSX injected through
`PLUGIN_SLOTS` into `org.openedx.frontend.layout.header_desktop_main_menu.v1`, ahead of Courses
and Discover, which stay. No fork, no core change and no npm package, since a tab is just an
anchor. Built and verified; the page itself is a placeholder.

**Catalogue:** extend [`frontend-app-catalog`](https://github.com/openedx/frontend-app-catalog),
the [Course About, Index and Course Catalog MFE conversion](https://openedx.atlassian.net/wiki/spaces/OEPM/pages/5010718766/Proposal+Course+About+page+Index+Page+and+Course+Catalog+MFE+conversion)
that landed in [Ulmo](https://docs.openedx.org/en/latest/community/release_notes/ulmo.html) and ships
in [`tutor-mfe`](https://github.com/overhangio/tutor-mfe) v22 behind `ENABLE_CATALOG_MICROFRONTEND`.
Track status is draft, announced, active or retired, so a next-quarter track with no steps still
lists its tier and vendor, which discovery cannot do.

**Vendor results:** `kind=vendor` steps carry no course key; results arrive as signed attestations,
one adapter per vendor, idempotent on `(vendor, vendor_ref, learner)`. We keep the assertion and
its grade, never the content.

**Certificates and the feed:** grant on the standard, issue via the [credentials service](https://github.com/openedx/credentials) with the client's
template through the endpoints `CatalogDataSynchronizer` expects. Notifications ride the platform's
notifications app; the program team reads the activity table as a partner-scoped feed.

**How the rest gets built.** Five phases ordered by dependency and by where the risk sits, with the
coach view early because its two-second claim is the one thing here I cannot yet back with a
measurement: [docs/implementation-plan.md](docs/implementation-plan.md).

## 3. Where the data lives

All ours, in the LMS database, with no foreign keys into platform tables. `PartnerCompany` is the
scoping root. `Tier` carries a `rank`. `CoachGroup` holds coach and partner. `LearnerRecord` is one
row per learner, one-to-one to `auth_user`, with no name, email or employee ID of its own. `Track`,
`TrackStep`, `TrackStepGroup`, `Vendor` and `CertificationStandard` are the track spine;
`TrackEnrollment` and its audit rows are soft-deleted; `LearnerTrackSummary` is the rollup the coach
view reads; `LearnerActivity` is append-only and feeds both the programme team and the rollup;
`Certification` records grants. Columns and cardinalities: [docs/erd.md](docs/erd.md).

Steps reference courses by key string, per the [Catalog Plugin](https://openedx.atlassian.net/wiki/spaces/OEPM/pages/5026938891/Proposed+Catalog+Plugin)'s rule that a catalogue holds
"references to courses, but will not store them directly to ensure data integrity and never be out
of date, like discovery". Every join to the platform is read-only and on `user_id` or a course key:
`auth_user`, `student_courseenrollment`, `grades_persistentcoursegrade`, the completion aggregator,
`course_overviews`.

## 4. What I would defer or decline

**Decline the mechanism, not the need: coaches editing progress directly.** A certification whose
progress its reviewer can set is not a certification. Give the offline work a graded home instead:
a [`StaffGradedXBlock`](https://github.com/openedx/staff-graded-xblock) step, staff-scored via CSV
import, whose `weight` caps how far it can move the standard. The coach scores that one block and
cannot touch other steps, completion or the tier. Scores land in `grades_persistentcoursegrade`
like any other, so the rollup recomputes with no special case and
`PERSISTENT_GRADE_SUMMARY_CHANGED` feeds the activity table. Costs nothing to adopt: the block is
already pinned in Verawood's base requirements.

**Decline: employee IDs on the learner record.** Partner-controlled identifiers for people who
are not our users, with no retention agreement, which would subject our table to each partner's
data policy and hand us a cross-partner correlation key we have no use for. What coaches
actually want is roster reconciliation against their HR system: an opaque per-partner external
reference on the enrollment, owned by the partner, plus export keyed on it. If the ID itself is
required, it belongs in its own table with its own retention rule and access log.

**Defer:** the vendor integration (contract-shaped, needs a real vendor), track authoring in
Studio (admin suffices until tracks change weekly), personalised paths, nomination beyond bulk
invite. Everything in section 3 past the five models in the README is design only.

## 5. Notes

**Unsure about three things.** Whether tracks need runs as courses do; the Catalog Plugin
proposal lists this as open and I ducked it by treating tracks as evergreen, which a cohort held
to its starting syllabus would overturn. Whether the rollup is maintained synchronously or over
the event bus; I would start synchronous and move it the first time enrollment latency is
complained about. And whether one coach per learner survives a real partner org chart, which the
first handover request settles.

**Where I used AI, and where I did not.** Claude Code did the reference sweep, the scaffolding and
most of the prose. The direction was mine, and three interventions changed substance rather than
wording. The thesis, a dedicated in-LMS plugin over extending course-discovery, came from my own
[Proposed Catalog Plugin](https://openedx.atlassian.net/wiki/spaces/OEPM/pages/5026938891/Proposed+Catalog+Plugin)
proposal. On offline grading it wanted to invent an attestation trail; I redirected it to a
staff-graded XBlock, reusing the platform's grading pipeline instead of a parallel one. On the
landing page it twice concluded a package outside this plugin was needed; I pointed it at how we did
header tabs at WikiLearn, and it turned out to be inline JSX plus one Django setting.

**What it got wrong that we caught.** It reported stackable pathways as a Verawood feature, echoing
a vendor blog; the release notes put that under "Upcoming in Willow", which would have inverted the
central decision here. It claimed Verawood does not ship `staff-graded-xblock` on the strength of a
command that had silently failed. And its first coach endpoint scoped members by the coach's
partners rather than per group, leaking across partners for a coach working with two companies.
