# ClaimSense AI: Stakeholder Map and RACI

The brief names no individuals, so this map uses roles. Names get filled in at the kickoff meeting.

## The four roles the brief asks for

| Role in the brief | Who | Why them |
|---|---|---|
| **Approver** (accountable for the pilot) | VP of Claims | Owns adjuster throughput and the claims budget. Signs the statement of work and the go-live. |
| **Reviewer of co-pilot output** | Claims Quality Lead (a senior licensed adjuster) | Reviews a sample of recommendations each week against what an experienced adjuster would decide, and owns the reference labels in the evaluation set. |
| **Daily user** | Line adjusters on the personal auto physical-damage desk | Use the co-pilot on every claim and confirm or override each recommendation. |
| **Can block rollout** | CISO (hard veto), Chief Compliance Officer (hard veto), SIU Manager (hard veto on fraud referral), line adjusters (quiet veto) | See the power map below. |

## Power map: who can say no

| Stakeholder | Wants | Veto | How we lose them |
|---|---|---|---|
| VP of Claims | Faster first decisions; a number for the board | None (the sponsor) | A demo with no measured result |
| Claims Quality Lead | Consistent, explainable decisions | Bandwidth: labels take their time | Asking them to label hundreds of cases before showing value |
| Line adjusters | Less re-keying, fewer hours per claim | **Quiet**: they route around a tool that slows them down or that they don't trust | A co-pilot that gives answers without showing where they came from |
| CISO | No data leaves its boundary; access stays controlled | **Hard**: controls client data and system access | Asking for production data, or access control written as a prompt |
| Chief Compliance Officer | Every adverse decision explainable and fair; a licensed adjuster accountable | **Hard**: regulatory sign-off | Any path where the model decides without a human, or a denial with no cited clause |
| SIU Manager | Fewer false referrals, no missed fraud | **Hard** on changes to referral | Flooding SIU with low-quality referrals |
| CMS, PAS and document store owners (claims IT) | Stability; no surprise load or writes | Bandwidth | Needing changes to their systems before value is proven |
| Model risk management | A documented, tested model with monitoring | Hard (at production stage, after the pilot) | No evaluation evidence or change control |

The adjusters' quiet veto is the one not on any org chart, and it's the most likely way a pilot like
this dies. That's why every recommendation shows its evidence, and why adjuster confirmation rate is
one of the four success criteria.

## RACI

R = responsible (does the work), A = accountable (exactly one per decision), C = consulted,
I = informed.

| Decision | VP Claims | Quality Lead | Adjusters | CISO | Compliance | SIU Mgr | Claims IT | FDE |
|---|---|---|---|---|---|---|---|---|
| Success criteria agreed | **A** | C | C | I | C | C | I | R |
| Evaluation labels are correct | I | **A** | C | – | C | C (fraud cases) | – | R |
| Access to the three systems granted | I | – | – | **A** | I | – | R | C |
| Recommendation confirmed or overridden (each claim) | I | I | **A**, R | – | – | – | – | – |
| A claim referred to SIU | I | I | R | – | I | **A** | – | – |
| Policy clause corpus updated | I | C | I | I | **A** | – | R | C |
| Pilot go-live | **A** | C | C | C (sign-off) | C (sign-off) | C | C | R |
| Rollback during the pilot | I | I | I | I | I | I | C | **A**, R |

Each row has exactly one A. On a single claim the adjuster is accountable for the outcome, not the
co-pilot and not the FDE. That's the constraint "a licensed adjuster confirms every outcome", made
concrete.
