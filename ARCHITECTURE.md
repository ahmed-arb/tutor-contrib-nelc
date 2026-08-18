# Partner certification platform: architecture note

Open edX Verawood, Tutor v22. ERD and diagrams: [docs/erd.md](docs/erd.md),
[docs/diagrams.md](docs/diagrams.md), kept out of the note to protect the page budget.

## 1. What I decided for you

**A track is a program, and a standard is a bar rather than a checklist.** The brief pairs
"courses taken in order" with "granted on passing a standard, not on finishing every course".
One model: ordered steps, each required or optional, plus a rule for passing. I assumed the
rule is a weighted grade threshold across required steps plus a minimum count from optional
groups, which is the shape the Proposed Catalog Plugin already argues for: "Complete all 2
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
`learning_paths`, below. Without vendor steps, adopting it and patching its gaps wins.

## 2. Approach

**Leave course-discovery alone.** Its programs are catalogue metadata in a separate service with
its own database, while every query here joins to LMS enrollment, grades and completion. That
boundary is what puts the two-second coach view out of reach. It is also the deprecated direction:
the Proposed Catalog Plugin exists to replace discovery with an in-LMS Django plugin, and this is
that pattern applied to one client.

**Native stackable pathways are not in Verawood; they are announced for Willow, December 2026.**
`open-craft/learning-paths-plugin` exists today, but its step is a `CourseKeyField` (no vendor or
unbuilt steps), its `level` is unenforced (no tier gate), and its visibility is `invite_only` plus
`is_staff` (no partner scoping). So build alongside it, keeping Track isomorphic so Willow is a
migration, not a redesign.

**One Tutor plugin, one LMS Django app** via the `lms.djangoapp` entry point, no fork. To change
platform behaviour: filter, then our own method called from core, then monkey-patch, then subclass,
the ladder WikiLearn used to retire four forks.

**Coach view:** a denormalised rollup, one row per learner per track, written by receivers, so
1200 rows come off one index on `(coach_group, track)` instead of being aggregated per request.
Live aggregation cannot reach two seconds on a phone; the price is seconds of staleness.

**In-course:** a `frontend-app-learning` plugin slot showing tier, distance to the standard and a
contact-coach action, so no course content changes.

**Landing page:** a frontend-base app declaring the `org.openedx.frontend.role.home` role, its tab
appended to the header's `desktopPrimaryLinks` slot ahead of Courses and Discover. The shell
resolves `/` from whichever app holds that role, so no core change and no redirect override.
Outside the slice because tab and role ship as an npm package installed via `FRONTEND_APPS`.

**Catalogue:** extend `frontend-app-catalog` (landed in Ulmo, in `tutor-mfe` v22 behind
`ENABLE_CATALOG_MICROFRONTEND`). Track status is draft, announced, active or retired, so a
next-quarter track with no steps still lists its tier and vendor, which discovery cannot do.

**Vendor results:** `kind=vendor` steps carry no course key; results arrive as signed attestations,
one adapter per vendor, idempotent on `(vendor, vendor_ref, learner)`. We keep the assertion and
its grade, never the content.

**Certificates and the feed:** grant on the standard, issue via credentials with the client's
template through the endpoints `CatalogDataSynchronizer` expects. Notifications ride the platform's
notifications app; the program team reads the activity table as a partner-scoped feed.

## 3. Where the data lives

Ours, in the LMS database, with no foreign keys into platform tables. `PartnerCompany` is the
scoping root; `Tier` carries `code` and `rank`; `CoachGroup` holds coach, partner and name.
`LearnerRecord` is one row per learner: `user` one-to-one to `auth_user` plus partner, tier and
coach group, and no name, email or employee ID. `Track`, `TrackStep`, `TrackStepGroup`,
`Vendor` and `CertificationStandard` are the track spine. `TrackEnrollment` plus audit rows are
soft-deleted; `LearnerTrackSummary` is the rollup the coach view reads; `LearnerActivity` is
append-only and is both the feed and the rollup's source; `Certification` records grants.

Steps reference courses by key string, per the Catalog Plugin's rule that a catalogue holds
"references to courses, but will not store them directly to ensure data integrity and never be
out of date, like discovery". Every join to the platform is on `user_id` or a course key,
read-only: `auth_user`, `student_courseenrollment`, `grades_persistentcoursegrade`, completion
aggregator, `course_overviews`.

## 4. What I would defer or decline

**Decline the mechanism, not the need: coaches editing progress directly.** A certification whose
progress its reviewer can set is not a certification. Give the offline work a graded home instead:
a `StaffGradedXBlock` step, staff-scored via CSV import, whose `weight` caps how far it can move the
standard. The coach scores that one block and cannot touch other steps, completion or the tier.
Scores land in `grades_persistentcoursegrade` like any other, so the rollup recomputes with no
special case and `PERSISTENT_GRADE_SUMMARY_CHANGED` feeds the activity table. Residual risk worth
naming: grading needs a course staff role, which is broader than one block, so offline-graded steps
belong in their own course to keep that grant narrow. One line in our dockerfile patch installs the
block, which Verawood does not ship.

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

**Where I used AI.** Claude Code, for the reference sweep across the Verawood notes,
`learning-paths-plugin`, `frontend-app-catalog` and `tutor-mfe`, and to draft the plugin
scaffolding against the WikiLearn and prior-client patterns.

**What it got wrong that I caught.** It reported stackable pathways as a Verawood feature,
echoing a vendor blog and search summaries; the release notes put that line under "Upcoming in
Willow (December 2026)". That would have inverted this note's central decision, so it is the
claim I checked against primary sources. Its first coach endpoint also scoped members by the set
of partners the coach works with rather than per group, which leaks across partners for any
coach with groups at two companies; I rewrote it as two queries with an explicit per-group
check.
