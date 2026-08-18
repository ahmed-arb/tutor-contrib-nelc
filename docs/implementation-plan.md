# Implementation plan

What the slice does not build, in the order I would build it, and how each phase would be judged
done. The [architecture note](../ARCHITECTURE.md) carries the reasoning; this carries the sequence.

Two rules drove the ordering. Nothing is scheduled before the thing it depends on, and the phase
holding the largest unproven claim comes early rather than late. That claim is the two-second coach
view, so it lands in phase 2, before any of it is dressed in a UI.

Everything below is a Tutor plugin change or a Django app change in this repo. No phase requires an
`edx-platform` fork.

## Already built

| Piece | Where |
| --- | --- |
| `PartnerCompany`, `Tier`, `CoachGroup`, `LearnerRecord`, `LearnerActivity` | `nelc/certification/models.py` |
| Coach-scoped roster endpoint | `nelc/certification/api/` |
| Enrollment receiver | `nelc/certification/receivers.py` |
| Landing page and header tab | `nelc/certification/views.py`, `tutornelc/plugin.py` |

## Phase 1: the track spine

Everything else depends on there being a track.

- **Models**: `Track`, `TrackStep`, `TrackStepGroup`, `CertificationStandard`, `TrackEnrollment`,
  `TrackEnrollmentAudit`, `Vendor` as a bare reference table.
- **Tier gate**: enforced in one place, on the join path, using `LearnerRecord.meets_tier()`, which
  the slice already implements and tests. Nomination in bulk goes through the same gate; a coach
  cannot nominate a learner past it.
- **Authoring**: Django admin only. Studio authoring is deferred until tracks change often enough
  to justify it, which for a fixed certification programme may be never.
- **Joining a track enrolls in its course steps**, so progress has something to read.
- **Done when**: a track with required and optional steps can be authored, a learner at the wrong
  tier is refused, one at the right tier joins and appears enrolled in the step courses, and every
  join and leave leaves an audit row.

## Phase 2: progress, and the two-second view

The risk phase. Ordered before any coach UI on purpose.

- **`LearnerTrackSummary`** maintained by receivers on `COURSE_ENROLLMENT_CREATED`,
  `PERSISTENT_GRADE_SUMMARY_CHANGED` and completion, one row per learner per track, unique on
  `(learner_record, track)`, indexed on `(coach_group, track)`.
- **Start synchronous**, in the receiver. Move to the event bus the first time enrollment or
  grading latency is complained about, not before. The rollup is idempotent either way, so the move
  is a deployment change rather than a redesign.
- **Prove the claim first**: seed 200 learners across 6 tracks with realistic grade and completion
  rows, then measure the coach endpoint. If one indexed read does not hold under a p95 target on a
  throttled connection, that is the moment to find out, not after a mobile UI exists.
- **Then the coach view**: the roster endpoint the slice already ships, extended with progress and
  a staleness timestamp, and a mobile-first page. `updated_at` is returned so the UI can say how
  old the numbers are instead of implying they are live.
- **Done when**: the 200 by 6 case meets the target with a recorded number, and a coach on a phone
  sees their whole group with distance-to-standard per track.

## Phase 3: certification

- **Evaluate the standard**: weighted grade across required steps plus minimum counts from
  `TrackStepGroup`, run when a summary row changes rather than on a schedule.
- **Grant**: a `Certification` row, a tier change recorded as an event, and issuance through the
  credentials service using the client's own template. We expose the endpoints
  `CatalogDataSynchronizer` expects and point `tutor-credentials` at us.
- **Notify**: step completed, falling behind the group, certification granted. All three ride the
  platform's notifications app rather than a mailer of ours.
- **Done when**: a learner who passes the bar without finishing every course is certified, holds a
  certificate in the client's design, and the three notifications fired.

## Phase 4: the public catalogue

- **Extend `frontend-app-catalog`**, enabled by `ENABLE_CATALOG_MICROFRONTEND`, fed by an
  unauthenticated read endpoint of ours.
- **Announced tracks**: `Track.status` of `announced` with no steps still lists, carrying tier and
  vendor. This is the requirement discovery cannot satisfy, so it is worth an explicit test that a
  track with zero steps and no course runs appears.
- **Done when**: an anonymous visitor sees every track including next quarter's, each with its tier
  and its vendor, and joining still refuses the under-tiered.

## Phase 5: the vendor adapter

Last, because it is contract-shaped and cannot be finished without a real vendor to integrate with.

- **One adapter per vendor** behind a shared interface, so vendor two is a class rather than a
  refactor.
- **Attestations**, signed, idempotent on `(vendor, vendor_ref, learner)`. We store the assertion
  and the grade it carries, never the vendor's content.
- **Evaluation is unchanged**: a vendor step contributes to the standard exactly as a course step
  does, which is the payoff for `TrackStep.kind` existing from phase 1.
- **Done when**: a replayed attestation changes nothing, an unsigned one is rejected, and a vendor
  step counts toward certification.

## Riding along

- **The activity feed** for the partner programme team: `LearnerActivity` exists from the slice, so
  this is a cursor-paginated read endpoint scoped by partner, deliverable in phase 1.
- **The in-course panel**: a `frontend-app-learning` plugin slot showing tier, distance to the
  standard and a contact-coach action. Needs phase 2's summary to have anything to show.
- **Offline grading**: a `StaffGradedXBlock` step, which needs nothing built since Verawood already
  ships the block. Usable as soon as phase 1 can hold a step.

## Not planned

Personalised paths, Studio track authoring, employee-ID storage, and coaches editing progress
directly. The last two are declined rather than deferred, with reasons, in the architecture note.
