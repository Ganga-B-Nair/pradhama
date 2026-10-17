## Initial README for TRACE by PRADHAMA

## Running it

Requirements: Docker Desktop, and [Ollama](https://ollama.com) running on the host with the plan's CPU model:

```
ollama pull qwen2.5:3b-instruct
docker compose up -d --build
```

Open http://localhost:3000 and sign in as **Officer** (`officer` / `officer123`) or **SHO** (`sho` / `sho123`).

- Evidence: create a case, record consent, then add up to **10 files** under Evidence (select, review, upload). Originals are hashed on arrival and stored in MongoDB GridFS (`evidence.files` / `evidence.chunks`); nothing is written to disk. The narration recording is added under Narration and doesn't use an evidence slot.
- QR codes from a phone: set `PUBLIC_BASE_URL=http://<laptop LAN IP>:3000` before `docker compose up`.
- `DEMO_CACHE=1` (default in compose) reuses the last good speech-to-text / LLM output if a model step fails (§9).
- What the timeline can read: WhatsApp exports (`.txt`, or the `.zip` the app produces; Android and iPhone formats), bank SMS (pasted `.txt`, or an SMS-backup `.csv`), bank statements (text-based PDF, `.xlsx`, `.csv`), call logs (`.csv` with common column names), and payment/SMS screenshots via OCR (Tesseract, English). Scanned (image-only) PDFs are not read; upload the pages as images instead. Long statements are trimmed to the incident dates (±2 days), and the Analysis step says how many rows it left out.
- Tests: `docker compose run --rm backend pytest -q` (uses a separate `trace_test` database).
- Pre-pull the Whisper `small` model (~480 MB, once, kept in the `whisper_models` volume) before the demo — otherwise the first narration spends its time limit downloading it:
  `docker compose exec backend python -c "from faster_whisper import WhisperModel; WhisperModel('small', device='cpu', compute_type='int8')"`

Without Ollama the pipeline still completes: narration is read by rules and the draft is written from templates, and the Analysis screen says so.

## Repo layout

- `docs/HACKATHON_PLAN.md` — the current build plan (architecture, tech stack, task split, schedule, risk register) for the 20-hour hackathon build. **Read this first.**
- `docs/PRD.md` / `docs/TRD.md` / `docs/SRS.md` / `docs/README.md` — the full 9-month pilot requirements the hackathon plan scopes down from.
- `backend/` — FastAPI app: MongoDB + Neo4j, the agent pipeline (`app/agents`, LangGraph in `app/worker.py`), custody chain (`app/custody.py`), export and verify. Document shapes live in `app/schemas.py`.
- `frontend/` — Next.js 14 app; screens follow `trace_ui_demo.html` and use its styling. `/api/*` is proxied to the backend.
- `contracts/` — the original H1 contract drafts (the live shapes are in `backend/app/schemas.py`).
- `docker-compose.yml` — MongoDB, Neo4j, backend and frontend. Ollama stays native on the host (see the plan for why).

## Form answers

### Idea Name
TRACE — Temporal-Relational Agentic Correlation Engine

### AI Track
**AI in Social Impact**

### What problem are you trying to solve?

An FIR is the most consequential document in an Indian criminal case. Everything downstream — investigation direction, chargesheet, trial — is built on it. Yet it is still assembled by hand, at a counter, under time pressure.

A complainant arrives with a jumble of raw material: forty WhatsApp screenshots in no order, bank SMS alerts, call logs, photographs, and a verbal account given in Malayalam. The station writer must convert this into a chronologically coherent English narrative, identify applicable BNS sections, and file within statutory limits. Four failures repeat constantly:

- **Incomplete first reports.** Critical details are never asked for, because nobody notices they're missing until the investigating officer picks up the file weeks later — by which time screenshots are deleted and memories have faded.
- **No chronology.** Evidence arrives as a pile, not a sequence. In cyber-fraud cases the order of transactions *is* the offence, and reconstructing it manually often never happens properly.
- **Unverified media.** Generative tools have made fabricated screenshots, morphed images, and cloned voice notes cheap and common. A station writer has no way to distinguish an authentic screenshot from a synthesised one, and forensic labs are backlogged for months, so nearly nothing gets referred.
- **Language loss.** The complainant speaks Malayalam; the FIR is written in English. Names and specifics are lost in an undocumented, unverifiable translation step.

The BNSS has made e-FIR and Zero FIR statutory realities, but the tooling underneath is still a plain text box. The law modernised; the workflow did not.

*(Confirm the BNSS section number for e-FIR before submitting, or keep the reference general.)*

### Who faces this problem and why it matters

**Station House Officers and FIR writers** across Kerala's police stations, who spend 45–90 minutes per complaint on manual assembly and still produce reports with gaps.

**Complainants** — disproportionately women, senior citizens, and victims of digital financial fraud — asked to narrate traumatic events while simultaneously organising their own evidence, who often leave without knowing what they failed to mention.

**Forensic laboratories**, already backlogged, which currently receive referrals with no triage — everything or nothing, with no signal about which files actually warrant examination.

Why it matters: a weak FIR is an access-to-justice problem, not a paperwork problem. Cases collapse in court on evidentiary gaps that originated at the counter on day one. And as fabricated digital evidence becomes trivial to produce, an intake process with no authenticity check becomes an attack surface — both for false complaints and for genuine complaints undermined by unexamined media.

### What solution are you proposing?

TRACE is an AI case-assembly assistant that sits between raw evidence and a filed FIR.

The complainant or officer uploads whatever exists — chat exports, screenshots, audio, call logs, bank statements, photographs — and narrates the incident by voice in Malayalam or English. Four specialist agents run in sequence:

**1. Content Triage Agent** classifies and screens every incoming file. It routes each item by evidence type (financial record, conversation, media, call log), computes a perceptual hash to collapse the duplicate screenshots that dominate real complaint bundles, and runs frequency-domain analysis to flag media whose compression and noise characteristics are inconsistent with the claimed capture source. Flagged files are marked *for forensic review*, not adjudicated — the output is a prioritised referral list that tells an overloaded lab which three files matter out of ninety.

**2. Metadata Agent** establishes provenance. It extracts EXIF, GPS coordinates, and creation timestamps from every file, geocodes locations, and flags conflicts between a file's claimed origin and its embedded metadata. This turns "here is a photograph" into "this photograph carries these coordinates and this timestamp" — an evidentiary fact rather than an assertion.

**3. Timeline Agent** reconstructs chronology. It extracts entities, dates, amounts, and events across all evidence and narration, then assembles a single ordered sequence. This becomes the body of the FIR — the coherent narrative currently written from scratch.

**4. Gap Hunter Agent** runs completeness and consistency checks over the assembled case graph using Neo4j Cypher queries, surfacing unanswered questions **while the complainant is still present**: a referenced transfer with no attached record, an unexplained delay between incident and report, a named person with no contact detail, a device placing itself in two locations too far apart to be physically possible.

The output is a structured draft FIR with an ordered narrative, an evidence manifest with authenticity flags, advisory BNS section suggestions, and a prioritised list of questions to ask before filing. Every uploaded file is hashed into a SHA-256 chain at intake, so chain of custody begins at the counter rather than at the malkhana.

Four design commitments, each defensible under questioning:

- **The officer files, not the AI.** BNS suggestions are advisory with citations attached; nothing auto-submits.
- **Triage flags, it does not judge.** Manipulation detection produces a review recommendation with stated confidence and stated limitations. We are explicit that frequency analysis catches crude tampering and misses sophisticated forgery; the agent's value is triage throughput, not verdicts.
- **Gap Hunter never scores credibility.** Inconsistent recall is a documented trauma response, not evidence of deception. The agent reports what information is *absent*, in neutral language addressed to the officer — never an assessment of the complainant.
- **Original Malayalam is preserved alongside the English.** Translation is a visible, auditable layer, never a silent replacement.

### Tech stack

**Backend:** FastAPI (Python 3.11), LangGraph orchestrating the four agents, Anthropic Claude API (claude-sonnet-4-6) for narrative synthesis, Malayalam translation, and gap reasoning.

**Databases:** PostgreSQL 15 (SQLAlchemy + Alembic) for case and audit records; Neo4j 5 for the entity-relationship graph powering Gap Hunter's Cypher consistency queries.

**AI/ML:** openai-whisper for Malayalam and English voice-complaint transcription; spaCy NER for English entity extraction; OpenCV for DFT frequency-domain manipulation screening; imagehash for perceptual-hash deduplication; Pillow + piexif for EXIF; langdetect for language routing; Nominatim for GPS geocoding.

**Frontend:** Next.js 14, Tailwind, shadcn/ui, vis-timeline for the chronology view.

**Integrity:** SHA-256 hash chain across all evidence and audit entries, QR-verifiable PDF export. Single-party hash chain, deliberately not a blockchain — tamper-evidence without the operational overhead or trust assumptions a distributed ledger would impose on a single-agency deployment.

**Deployment:** Docker Compose, built for on-premise deployment inside police network infrastructure. No evidence leaves the deploying agency's environment.

**Security:** file-type allowlist, 50MB cap, Cypher injection guard, 30s timeouts with graceful degradation on every model call.

### Primary target user

**Primary:** Station House Officers and FIR writers at Kerala Police stations, especially Cyber Police Stations and Cyberdome units, where evidence volume per complaint is highest and manual collation fails most visibly.

**Secondary:** State forensic laboratories, which receive TRACE's triage output as a prioritised referral queue; District Legal Services Authorities and legal aid clinics assisting complainants pre-filing.

**Beachhead:** Kerala cyber-fraud and financial-crime complaints. Evidence-dense, chronology-critical, rising sharply in volume, and increasingly contaminated with synthetic media.

### Go-to-market & commercialization

*(Put this in the field labelled "Enter a value for this field.")*

**Channel.** We have an existing working relationship with **Kerala Cyberdome** through the HackP hackathon, where TRACE's predecessor advanced to the Kochi round. That is a warm entry point, not a cold pitch. We convert it into a single-station pilot at a Cyber Police Station, instrumented for three metrics: minutes saved per FIR, gaps caught at intake versus discovered later, and forensic referrals correctly prioritised.

**Sequence.** Single-station pilot (months 1–4) → district rollout (months 5–9) → state MoU with Kerala Police (months 10–18) → replication to other state forces, where the BNSS e-FIR mandate applies identically and the product needs only a language-layer swap.

**Revenue.** Annual per-station SaaS licensing on on-premise deployment, tiered by station volume, plus an implementation-and-training fee at rollout. Government procurement runs through GeM listing and state IT department empanelment. A parallel non-government line sells a lighter build to legal aid organisations and law firms for pre-litigation case assembly — the same four agents pointed at a different output document.

**Why we can win it.** Existing digital forensics tools are built for post-registration investigation and priced for central agencies. Nothing is built for the intake counter. That is an unserved point in the workflow, and it is where a case is most cheaply fixed.

### Development timeline

**9 months** to a production-ready, pilot-deployable system.

Months 1–2: four-agent pipeline hardened, live Claude integration, Malayalam accuracy testing on real complaint audio, manipulation-screening calibrated against a labelled dataset to establish honest false-positive rates. Months 3–4: officer-facing UI built with station-side feedback, BNS section retrieval layer. Months 5–6: security hardening, on-premise packaging, single-station pilot launch. Months 7–9: pilot iteration, audit and compliance review, multi-station readiness.

### Funding required (INR)

**₹15,00,000** over 12 months.

| Line | Amount |
|---|---|
| Team stipends (4 members, 12 months) | ₹7,20,000 |
| Cloud, LLM API, Whisper compute | ₹1,80,000 |
| Security audit & compliance review | ₹2,00,000 |
| Company registration, legal, IP | ₹1,00,000 |
| Pilot deployment, hardware, officer training | ₹1,50,000 |
| Contingency | ₹1,50,000 |

A leaner ₹6,00,000 reaches pilot-ready in 6 months if the formal security audit is deferred until after pilot validation. The ₹15L figure aligns with KSUM's seed loan ceiling, our intended follow-on instrument.

### Plans for starting a company

We intend to incorporate as a **Private Limited company registered in Kerala within the pre-incubation period**, filing for DPIIT startup recognition immediately after — a prerequisite for government procurement eligibility.

The path: incorporate → KSUM incubation and Idea Grant → Cyberdome pilot MoU → GeM listing and Kerala state IT empanelment → state-level contract. All four founders are third-year students, so the first 18 months run alongside coursework, with full-time transition on graduation.

Because the customer is a state police force, we treat regulatory and procurement readiness as a product requirement rather than a later concern. Data localisation, on-premise-only deployment, and audit-log completeness are being built into v1 rather than retrofitted — they are the conditions of sale, not features.
