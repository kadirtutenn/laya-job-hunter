# Decision layer design

The default workflow favors deterministic rules and a local decision model. It does not call a generative API or send profile data to a remote AI service.

| Layer | Responsibility | Default implementation |
|---|---|---|
| L0 Deterministic | Required-field/type checks, keyword matching, LaTeX escaping, URL and profile validation | Python functions and validators |
| L1 Laya | Typed fit/seniority/skill decisions and keep/reorder/highlight/ask decisions tied to supplied candidate evidence | Local Ollaya `laya` router at `127.0.0.1:11435` |
| L2 Workflow cache | Reuse successful workflow settings while keeping candidate data local | Local SQLite; profile and browser state are ignored by Git |
| L3–L4 Generation routing | Generate prose only when requested and when candidate evidence supports it | Disabled by default; no API key or generative-model dependency configured |
| L5–L6 Advanced reasoning | Escalate unusually complex job descriptions or CV structures | Not enabled in the base install; configure separately if needed |
| L7 Human approval | Verify unsupported experience, meaning-changing edits, sensitive answers, and every final application submission | Form preparation does not click submit; user reviews and submits manually |

Laya is a decision model, not a prose generator. Its score is a model output, not a calibrated probability unless the user has calibrated it on representative labeled data. This repository ships no candidate profile, base CV, or candidate-specific cache.

## Token and privacy defaults

- Deterministic checks run before model calls.
- Laya requests send only the job/profile fields needed for the requested decision to the locally running Ollaya service.
- No generative model is configured by default, so normal fit checks use no text-generation tokens.
- If a user later adds remote generation, they must opt in and review which CV and job data leave the device.
- Avoid caching candidate text in shared or remote caches.
