# Architecture diagrams

Three views: what runs where, how the plugin gets installed, and the request path that has to
come back in under two seconds.

## 1. Services and what we own

Solid boxes are ours. Dashed is deliberately not used.

```mermaid
flowchart TB
    subgraph browser["Learner and coach"]
        catalog["frontend-app-catalog<br/>Home / About / Catalog<br/><i>extended: track cards with tier + vendor</i>"]
        learning["frontend-app-learning<br/><i>plugin slot: tier, distance to standard,<br/>reach your coach</i>"]
        dashboard["frontend-base shell<br/><i>our app holds role.home, so it owns /<br/>tab in header desktopPrimaryLinks,<br/>ahead of Courses and Discover</i>"]
    end

    subgraph lms["Open edX LMS (one process)"]
        core["edx-platform<br/>enrollment, grades, completion,<br/>notifications, auth"]
        app["<b>nelc.certification</b><br/>tracks, tiers, partners, coach groups,<br/>standard, rollup, activity<br/><i>lms.djangoapp entry point</i>"]
    end

    creds["credentials service<br/><i>issues the certificate<br/>in the client's design</i>"]
    vendors["External vendors<br/><i>deliver content in their own systems</i>"]
    discovery["course-discovery<br/><b>not used</b>"]

    catalog -->|"public track list,<br/>incl. announced"| app
    learning --> app
    dashboard --> app
    app -->|"reads enrollment, grades, completion<br/>by user_id and course_key"| core
    core -->|"openedx-events signals,<br/>e.g. COURSE_ENROLLMENT_CREATED"| app
    app -->|"CERTIFICATE_CREATED,<br/>CatalogDataSynchronizer endpoints"| creds
    vendors -->|"signed attestations,<br/>idempotent per learner+ref"| app
    app -.->|"no dependency"| discovery

    style app fill:#2d6a4f,color:#fff
    style discovery stroke-dasharray: 5 5,color:#888
```

### The landing page, and why it is not in the slice

The brief asks for the learner's landing page to be the certification dashboard. In [frontend-base](https://github.com/openedx/frontend-base)
that needs no core change and no redirect override: an app declares the
`org.openedx.frontend.role.home` role and the shell resolves `/` to it, while a nav tab is a widget
appended to `org.openedx.frontend.slot.header.desktopPrimaryLinks.v1`, which is the same slot the
shell's own `PrimaryNavLinks` uses for Courses and Discover.

Both the role and the tab are contributed by an `App` config exported from an npm package, which
Tutor installs through the `FRONTEND_APPS` filter. That package is a separate repo, so it is
outside this plugin and outside this slice. Two caveats for whoever picks it up: [Verawood](https://docs.openedx.org/en/latest/community/release_notes/verawood.html) ships the
frontend-base `learner-dashboard` app as `enabled: False`, so the shell path is opt-in for now, and
full MFE conversion to frontend-base is not expected until Xylon in June 2027 (see the [release schedule](https://openedx.atlassian.net/wiki/spaces/COMM/pages/3613392957/Open+edX+release+schedule)). Until then the
legacy equivalent is a [`frontend-component-header`](https://github.com/openedx/frontend-component-header) plugin slot, which needs an npm package just the
same.

The point of this picture is that our app and the platform are the same process. Every join the
coach view needs is a local query, not a service call. That is the whole reason discovery is not
in the solid part of the diagram.

## 2. How it installs

No [`edx-platform`](https://github.com/openedx/edx-platform) fork anywhere in this path.

```mermaid
flowchart LR
    repo["tutor-contrib-nelc<br/>(this repo)"]
    ep["tutor.plugin.v1<br/>entry point"]
    sync["PROJECT_ROOT_READY<br/>copytree into<br/>env/build/openedx/djangoapp/"]
    patch["openedx-dockerfile-post-<br/>python-requirements patch<br/>COPY + uv pip install"]
    image["openedx image<br/>with the app inside"]
    djep["lms.djangoapp<br/>entry point"]
    running["LMS at startup:<br/>INSTALLED_APPS, URLs,<br/>settings, signal receivers"]
    init["CLI_DO_INIT_TASKS<br/>migrate + seed"]

    repo --> ep -->|"tutor plugins enable nelc"| sync --> patch -->|"tutor images build openedx"| image
    image --> djep --> running
    image -->|"tutor local launch"| init --> running
```

Two details that matter. The Django app is copied rather than rendered as a Tutor template,
because Tutor's Jinja pass would try to interpret any `{{ }}` in Python source; it is therefore
deliberately not registered as an `ENV_TEMPLATE_TARGETS` entry. And the copy is
delete-then-write, because Tutor's template targets overwrite but never delete, so a file
removed from the plugin would otherwise stay in the environment and be baked into the next
image forever.

## 3. The coach view request path

The requirement is under two seconds for 200 learners across 6 tracks, on a phone, between
customer calls.

```mermaid
sequenceDiagram
    participant C as Coach (phone)
    participant A as nelc.certification
    participant S as LearnerTrackSummary
    participant E as Event receivers

    Note over E,S: Ahead of time, not during the request
    E->>S: enrollment / grade / completion /<br/>vendor attestation events
    S->>S: upsert one row per (learner, track)

    C->>A: GET /api/nelc/v1/coach/me/group/<br/>no group id in the URL
    A->>A: CoachGroup.filter(coach=request.user)
    A->>S: one query, INDEX(coach_group, track)
    S-->>A: ~1200 rows
    A->>A: drop any row whose partner<br/>disagrees with its group
    A-->>C: roster + progress + staleness
```

What is *not* on this path: no aggregation over `student_courseenrollment`, no grade
recomputation, no per-learner loop, and no call to another service. Those all happen earlier, on
events. The trade is that the numbers can be a few seconds old, and `updated_at` is returned so
the UI can say so instead of implying it is live.

### The isolation guarantee, as a diagram

```mermaid
flowchart TB
    req["GET /coach/me/group/"]
    q1["CoachGroup.filter(coach=request.user, is_active=True)"]
    q2["LearnerRecord.filter(coach_group_id__in=those groups)"]
    chk{"member.partner_id ==<br/>group.partner_id ?"}
    out["return"]
    drop["log warning, withhold"]

    req -->|"takes no group id:<br/>nothing to tamper with"| q1 --> q2 --> chk
    chk -->|yes| out
    chk -->|no| drop
```

An IDOR needs an object reference to tamper with, and this endpoint accepts none. The per-group
partner check is redundant with `LearnerRecord.clean()` on purpose, because `clean()` does not
run on bulk writes or a manual data fix, and the failure mode is leaking another company's staff
roster.
