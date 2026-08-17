# Data model

Two diagrams. The first is what the slice actually migrates. The second is the full design,
including the tables the note argues for but the slice does not build.

**Bold** entities below are built and migrated. The rest are design only. Nothing in this app
holds a foreign key into a platform table; the boundary is drawn with `user_id` and course key
strings, following the Proposed Catalog Plugin's rule that a catalogue keeps "references to
courses, but will not store them directly to ensure data integrity and never be out of date,
like discovery".

## 1. The slice

Five tables. Enough to record a coach's group assignment and a learner's tier, and to react to
an enrollment.

```mermaid
erDiagram
    auth_user ||--o| LearnerRecord : "one-to-one, user_id"
    auth_user ||--o{ CoachGroup : "coaches"
    PartnerCompany ||--o{ CoachGroup : "scopes"
    PartnerCompany ||--o{ LearnerRecord : "employs"
    Tier ||--o{ LearnerRecord : "current tier"
    CoachGroup ||--o{ LearnerRecord : "member of, nullable"
    LearnerRecord ||--o{ LearnerActivity : "append-only history"
    auth_user ||--o{ LearnerActivity : "actor, nullable"

    auth_user {
        int id PK "platform table, read-only"
        string username
        string email
    }
    PartnerCompany {
        int id PK
        slug code UK "scoping root"
        string name
        bool is_active
    }
    Tier {
        int id PK
        slug code UK
        string name
        int rank UK "gate is a rank comparison"
    }
    CoachGroup {
        int id PK
        int coach_id FK "auth_user"
        int partner_id FK
        string name
        bool is_active
        string _unique "UNIQUE(coach, partner, name)"
    }
    LearnerRecord {
        int id PK
        int user_id FK "UNIQUE, auth_user"
        int partner_id FK
        int tier_id FK "nullable, null gates out of everything"
        int coach_group_id FK "nullable, one coach at a time"
        string _index "INDEX(coach_group, partner)"
    }
    LearnerActivity {
        int id PK
        int learner_record_id FK
        string event_type
        string course_key "key string, never an FK"
        int actor_id FK "nullable, who did it if not the learner"
        datetime occurred_at
        json context
    }
```

Two things worth noting. `LearnerRecord.coach_group` and `LearnerRecord.partner` must agree,
enforced in `clean()` and re-checked per group in the endpoint, because the failure mode is
handing a coach another company's roster. And `LearnerActivity` has no `modified` column and no
delete permission in the admin: a coach's offline adjustment is a new row naming them as actor,
never an edit to an old one.

## 2. The full design

Adds the track spine, the certification standard, the vendor boundary and the read model that
answers the two-second requirement.

```mermaid
erDiagram
    PartnerCompany ||--o{ CoachGroup : ""
    PartnerCompany ||--o{ LearnerRecord : ""
    Tier ||--o{ LearnerRecord : "current"
    Tier ||--o{ Track : "required to join"
    CoachGroup ||--o{ LearnerRecord : ""
    LearnerRecord ||--o{ TrackEnrollment : ""
    LearnerRecord ||--o{ LearnerActivity : ""
    LearnerRecord ||--o{ LearnerTrackSummary : ""
    LearnerRecord ||--o{ Certification : ""
    Track ||--o{ TrackStep : "ordered"
    Track ||--o{ TrackStepGroup : "pick N of M"
    Track ||--|| CertificationStandard : "the bar"
    Track ||--o{ TrackEnrollment : ""
    Track ||--o{ LearnerTrackSummary : ""
    Track ||--o{ Certification : ""
    TrackStepGroup ||--o{ TrackStep : "membership"
    Vendor ||--o{ TrackStep : "delivers"
    Vendor ||--o{ VendorAttestation : "asserts"
    TrackStep ||--o{ VendorAttestation : "evidence for"
    TrackEnrollment ||--o{ TrackEnrollmentAudit : ""

    Track {
        string key PK "track-v1:org+number+run"
        uuid uuid UK "credentials compatibility"
        string name
        int required_tier_id FK "the gate"
        string status "draft, announced, active, retired"
        string announced_for "e.g. 2026-Q4, for unbuilt tracks"
    }
    TrackStep {
        int id PK
        string track_id FK
        int order
        string kind "course or vendor"
        string course_key "nullable: unbuilt or vendor-delivered"
        int vendor_id FK "nullable"
        string vendor_ref "nullable, the vendor's own id"
        bool is_required
        float weight
        int step_group_id FK "nullable"
    }
    TrackStepGroup {
        int id PK
        string track_id FK
        string name "e.g. Specialization"
        int min_steps_required "the pick-N-of-M rule"
    }
    CertificationStandard {
        int id PK
        string track_id FK "one-to-one"
        float required_grade "weighted mean across required steps"
        float required_completion
    }
    Vendor {
        int id PK
        slug code UK
        string name
        string ingest_mode "webhook or pull"
    }
    VendorAttestation {
        int id PK
        int vendor_id FK
        int step_id FK
        int learner_record_id FK
        float asserted_grade
        datetime asserted_at
        string signature
        string _unique "UNIQUE(vendor, vendor_ref, learner)"
    }
    TrackEnrollment {
        int id PK
        int learner_record_id FK
        string track_id FK
        string source "self or nomination"
        int nominated_by_id FK "nullable"
        bool is_active "soft delete, never hard"
        string partner_external_ref "opaque, partner-owned; NOT an employee ID"
    }
    LearnerTrackSummary {
        int id PK
        int learner_record_id FK
        string track_id FK
        int coach_group_id FK "denormalised for the index"
        int steps_total
        int steps_complete
        float weighted_grade
        float distance_to_standard
        string status
        datetime updated_at
        string _index "UNIQUE(learner, track), INDEX(coach_group, track)"
    }
    Certification {
        int id PK
        int learner_record_id FK
        string track_id FK
        int granted_tier_id FK
        datetime granted_at
        string credential_uuid "issued by the credentials service"
    }
```

### Why `LearnerTrackSummary` exists

It is the only answer to "under two seconds for 200 learners across 6 tracks" that survives a
phone on a customer site. Computed live, that view is a fan-out across
`student_courseenrollment`, `grades_persistentcoursegrade`, the completion aggregator and
`VendorAttestation`, per learner per track. Precomputed, it is 1200 rows on one index. It is
maintained by the same receivers that write `LearnerActivity`, and `updated_at` lets the UI say
how stale it is rather than pretending it is live.

## Joins to the platform

All read-only, all on `user_id` or a course key string:

| Platform table | What we read | Joined on |
| --- | --- | --- |
| `auth_user` | identity, so we never copy names or emails | `LearnerRecord.user_id` |
| `student_courseenrollment` | whether the learner is in a course step | `user_id` + `course_id` |
| `grades_persistentcoursegrade` | the grade a step contributes to the standard | `user_id` + `course_id` |
| completion aggregator | progress within a step | `user_id` + `course_key` |
| `course_overviews` | display data for a step | `course_key` |

There is no reverse direction. Nothing in `edx-platform` knows this app exists, which is what
makes an upgrade to Willow a matter of our own migrations rather than a merge.
