# ClaimSense AI: Stakeholder Map and RACI

The brief names no individuals, so this map uses roles. Names get filled in at the kickoff meeting.

## The four roles the brief asks for

| Role in the brief | Who | Why them |
|---|---|---|
| **Approver** (accountable for the pilot) | VP of Claims | Owns adjuster throughput and the claims budget. Signs the statement of work and the go-live. |
| **Reviewer of co-pilot output** | Claims Quality Lead (a senior licensed adjuster) | Reviews a sample of recommendations each week against what an experienced adjuster would decide, and owns the reference labels in the evaluation set. |
| **Daily user** | Line adjusters on the personal auto physical-damage desk | Use the co-pilot on every claim and confirm or override each recommendation. |
| **Can block rollout** | CISO (hard veto), Chief Compliance Officer (hard veto), SIU Manager (hard veto on fraud referral), Legal and Procurement (contract gate), line adjusters (quiet veto) | See the power map below. |

## Power map: who can say no

Each stakeholder is labeled with one type:
- **user:** works with the co-pilot's output.
- **blocker:** can stop the pilot or a milestone.
- **enabler:** provides what the pilot needs (money, access, systems).

| Stakeholder | Type | Wants | Veto | How we lose them |
|---|---|---|---|---|
| VP of Claims | **enabler** (sponsor) | Faster first decisions; a number for the board | None (the sponsor) | A demo with no measured result |
| Claims Quality Lead | **user** (reviewer) | Consistent, explainable decisions | Bandwidth: labels take their time | Asking them to label hundreds of cases before showing value |
| Line adjusters | **user** (daily) | Less re-keying, fewer hours per claim | **Quiet**: they route around a tool that slows them down or that they don't trust | A co-pilot that gives answers without showing where they came from |
| CISO (Security) | **blocker** | No data leaves its boundary; access stays controlled | **Hard**: approves the auth model and system access; can block Week 4 | Asking for production data, or access control written as a prompt |
| Chief Compliance Officer | **blocker** | Every adverse decision explainable and fair; a licensed adjuster accountable | **Hard**: regulatory sign-off | Any path where the model decides without a human, or a denial with no cited clause |
| SIU Manager | **blocker** | Fewer false referrals, no missed fraud | **Hard** on changes to referral | Flooding SIU with low-quality referrals |
| Legal and Procurement | **blocker** | IP, data-ownership and liability terms they can sign | **Hard**: the SoW isn't executed without them (Week 2) | A data annex or IP clause that is vague |
| Model risk management | **blocker** | A documented, tested model with monitoring | Hard (at production stage, after the pilot) | No evaluation evidence or change control |
| Claims IT: CMS, PAS and document store owners, and the cloud team | **enabler** | Stability; no surprise load or writes | Bandwidth: access, networking, deployment permissions | Needing changes to their systems before value is proven |
| CFO | **enabler** (indirect) | Return on the pilot: cost per claim and total engagement cost | Budget, through the VP of Claims | A price with no stated assumptions |

The adjusters' quiet veto is the one not on any org chart, and it's the most likely way a pilot like
this dies. That's why every recommendation shows its evidence, and why adjuster confirmation rate is
one of the four success criteria.

## RACI by deliverable (Weeks 1–5)

R = responsible (does the work), A = accountable (exactly one per row), C = consulted, I = informed.
"Security" is the CISO.

| Deliverable | Week | VP Claims | Quality Lead | Adjusters | Security | Compliance | SIU Mgr | Claims IT | Legal/Proc. | FDE |
|---|---|---|---|---|---|---|---|---|---|---|
| Engagement charter | 1 | **A** | C | C | I | C | C | I | I | R |
| Success criteria and first eval cases | 1 | **A** | C | C | I | C | C | – | – | R |
| SoW and pricing | 2 | **A** | I | – | C | C | – | I | C | R |
| Architecture diagram | 2 | C | I | I | C | I | – | C | – | **A**, R |
| Auth model and RBAC | 2–4 | I | – | I | **A** | C | – | C | – | R |
| Agent pipeline build | 3 | I | C | C | I | – | C | C | – | **A**, R |
| Eval gate threshold | 3–5 | **A** | C | I | C | C | C | I | – | R |
| Data-access service and audit trail | 4 | I | – | – | C | C | – | C | – | **A**, R |
| Runbook, dashboard and handover | 5 | **A** | I | I | C | I | I | C | I | R |
| Go-live decision | 5 | **A** | C | C | C | C | C | C | I | C |

**Why Security is consulted from Week 2.** Security is consulted on the architecture in Week 2 and
accountable for the auth model. If they first see the data-access service in Week 4, they block it
then.

**Why the FDE is only C on go-live.** The decision is the client's: the FDE supplies the evidence
(eval results, two-user test, audit records) and doesn't decide.

## RACI by decision

| Decision | VP Claims | Quality Lead | Adjusters | Security | Compliance | SIU Mgr | Claims IT | FDE |
|---|---|---|---|---|---|---|---|---|
| Success criteria agreed | **A** | C | C | I | C | C | I | R |
| Evaluation labels are correct | I | **A** | C | – | C | C (fraud cases) | – | R |
| Access to the three systems granted | I | – | – | **A** | I | – | R | C |
| Recommendation confirmed or overridden (each claim) | I | I | **A**, R | – | – | – | – | – |
| A claim referred to SIU | I | I | R | – | I | **A** | – | – |
| Policy clause corpus updated | I | C | I | I | **A** | – | R | C |
| Pilot go-live | **A** | C | C | C (sign-off) | C (sign-off) | C | C | C |
| Rollback during the pilot | I | I | I | I | I | I | C | **A**, R |

**One A per row** in both tables (`tests/test_stakeholders.py` checks it). On a single claim the
adjuster is accountable for the outcome, not the co-pilot and not the FDE. That's the constraint "a
licensed adjuster confirms every outcome", made concrete.
