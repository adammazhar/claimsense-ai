# The MCP door (Milestone 4)

The co-pilot reaches the client systems only through one governed MCP server, under the adjuster's own
token. The scope gate and the audit run in code inside the door, and the CMS filters rows again
underneath it. Decisions: D-031 to D-037. Matrix: [access-control.md](../engagement/access-control.md).

```mermaid
flowchart LR
  adjuster["Adjuster<br/>bearer seat token"] -->|"POST /v1/claims/{id}/recommendation"| api

  subgraph frontend["frontend network"]
    api["Co-pilot API + pipeline<br/>(deterministic spine)"]
    agents["Agents<br/>Coverage Check, Claim Assessment<br/>tool: search_clauses only"]
    api --> agents
  end

  subgraph door["MCP door (MCPServer, streamable HTTP)"]
    auth["Token check<br/>seat → user, role, scope"] --> gate["Scope gate<br/>deny by default"]
    gate --> audit[("Audit trail<br/>append-only, hash-chained")]
  end

  api -->|"get_claim, get_policy, get_claim_documents,<br/>submit_draft_recommendation (code only)"| auth
  agents -->|"search_clauses(query)<br/>claim bound by code"| auth

  subgraph backend["backend network: only the door joins"]
    cms["CMS<br/>row filter by seat"]
    pas["Policy admin (PAS)"]
    docs["Document store"]
    clauses["Clause library"]
  end

  gate --> cms
  gate --> pas
  gate --> docs
  gate --> clauses
```

A denial is written to the audit trail before its structured error (`forbidden_scope`) goes back to the
API, which returns it to the caller as a 403.
