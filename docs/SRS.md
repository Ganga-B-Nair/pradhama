# TRACE — Software Requirements Specification (SRS)

Version 1.0 · 16 Oct 2026

> Part of the TRACE requirements set. Shared decisions (D1–D7), glossary, legal references and open questions live in [README.md](README.md). Companion documents: [PRD](PRD.md) · [TRD](TRD.md) · [SRS](SRS.md).

## 3.1 Introduction

**Purpose.** This SRS lists the testable requirements for TRACE v1. Each requirement has an ID, a priority and an acceptance criterion. QA test cases and the security audit refer to these IDs.

**Scope.** TRACE v1 handles intake, analysis, drafting, review, approval and export of a draft FIR at one police station. It does not file FIRs, connect to CCTNS, or support investigation after registration (PRD §1.3).

**References.** PRD (Part 1), TRD (Part 2), BNS 2023, BNSS 2023, BSA 2023 (Appendix B), OWASP ASVS 4.0, RFC 8785, RFC 9457.

## 3.2 Overall description

- **Product perspective:** a standalone, on-premise web application. Its output is handed to the official FIR channel by a person.
- **User classes:** FIR writer, SHO, IO, forensic analyst, administrator (PRD §1.4).
- **Operating environment:** Chromium-based browsers or Firefox (last 2 versions) on station desktops at 1366×768 or larger. The server is a Linux host running Docker (TRD §2.11).
- **Constraints:** on-premise only; data stays in India; no auto-filing; English output, with Malayalam input and the Malayalam original kept; procurement through GeM, which means audit and documentation must be complete.
- **Assumptions:** the station has a LAN, a UPS, and a microphone or headset at the counter. The complainant gives consent to processing. The agency approves the LLM hosting option (D1).
- **Dependencies:** LLM provider (D1/D2), the speech model (D7), the OSM India extract, and a BNS statute text corpus in machine-readable form.

## 3.3 Functional requirements

**FR-AUTH — Accounts and access**

| ID | Requirement | Pri. | Acceptance criterion |
| --- | --- | --- | --- |
| FR-AUTH-01 | The system shall authenticate users with a username and password. | M | A valid login returns a session. An invalid one returns a generic error without saying which field was wrong. |
| FR-AUTH-02 | The system shall lock an account for 15 minutes after 5 consecutive failed logins. | M | The 6th attempt within the lockout window is rejected and logged. |
| FR-AUTH-03 | The system shall enforce role-based permissions per TRD §2.8. | M | Every endpoint returns 403 for a role it doesn't allow (automated matrix test). |
| FR-AUTH-04 | The system shall restrict each user to the cases of their own station. | M | A cross-station case ID returns 404. |
| FR-AUTH-05 | The system shall end sessions after 15 minutes of inactivity. | M | A request after 15 minutes idle needs a new login. |

**FR-CASE — Case lifecycle**

| ID | Requirement | Pri. | Acceptance criterion |
| --- | --- | --- | --- |
| FR-CASE-01 | The system shall create a case with a unique station-scoped reference number. | M | Reference format `<STATION>-<YYYY>-<NNNNN>`, unique under concurrent creation. |
| FR-CASE-02 | The system shall record the complainant's identity, contact, preferred language and consent before evidence can be uploaded. | M | Upload is blocked until consent is recorded; consent text version is saved. |
| FR-CASE-03 | The system shall move cases through the states draft → analysing → review → approved → exported, allowing only defined transitions. | M | An illegal transition returns 409. |
| FR-CASE-04 | The system shall make an approved case read-only, except for a new export or an SHO-initiated reopen with a stated reason. | M | Edits after approval return 409; a reopen is logged with its reason. |

**FR-INT — Evidence intake**

| ID | Requirement | Pri. | Acceptance criterion |
| --- | --- | --- | --- |
| FR-INT-01 | The system shall accept multi-file uploads of these types: JPG, PNG, WEBP, HEIC, PDF, TXT, CSV, XLSX, ZIP (chat export), OGG/OPUS, MP3, M4A, WAV. | M | Each allowed type uploads. A disallowed type is rejected with a reason. |
| FR-INT-02 | The system shall reject files over 50 MB and cases over 500 MB in total. | M | A 50.1 MB file is rejected; the officer sees the limit. |
| FR-INT-03 | The system shall check each file's type by its content (magic bytes) and reject a file whose content doesn't match its extension. | M | A renamed `.exe` saved as `.jpg` is rejected. |
| FR-INT-04 | The system shall scan every file for malware before parsing it. | M | The EICAR test file is quarantined and logged. |
| FR-INT-05 | The system shall compute the SHA-256 of each original file while it uploads and write the hash to the case's audit chain before any other processing. | M | The stored hash equals `sha256sum` of the source file, and the audit entry precedes any analysis entry. |
| FR-INT-06 | The system shall store originals so they can't be overwritten, and keep all derived files apart from them. | M | An attempt to overwrite an original object fails. |
| FR-INT-07 | The system shall expand WhatsApp ZIP exports within set limits (no nested archives, at most 1,000 entries, expansion ratio under 100:1). | M | A zip-bomb test file is rejected. |
| FR-INT-08 | The system shall let the officer add files at any point before approval. | M | Files added later trigger a partial re-run. |

**FR-NAR — Narration and translation**

| ID | Requirement | Pri. | Acceptance criterion |
| --- | --- | --- | --- |
| FR-NAR-01 | The system shall record narration in the browser or accept it as an uploaded audio file. | M | A 10-minute recording saves and is hashed. |
| FR-NAR-02 | The system shall detect whether the narration is Malayalam or English and transcribe it. | M | Language is detected correctly on 95% or more of the benchmark set. |
| FR-NAR-03 | The system shall translate a Malayalam transcript into English and show the original and the translation side by side, aligned segment by segment. | M | Every English segment links to its Malayalam segment and audio time range. |
| FR-NAR-04 | The system shall let the officer correct the transcript and translation, keeping the machine version and the edit history. | M | Both versions can be retrieved; the edit is in the audit chain. |
| FR-NAR-05 | The system shall keep names, numbers and amounts as they appear in the original, transliterated, rather than translated. | M | Golden-set check: names and amounts are unchanged in 98% or more of cases. |
| FR-NAR-06 | The system shall transcribe voice notes found in the evidence the same way. | S | Voice notes appear as conversation evidence with a transcript. |

**FR-TRI — Content Triage Agent**

| ID | Requirement | Pri. | Acceptance criterion |
| --- | --- | --- | --- |
| FR-TRI-01 | The system shall classify each file as one of: financial record, conversation, media, call log, document, audio, other. | M | Classification accuracy of 90% or more on the golden set. |
| FR-TRI-02 | The system shall group near-duplicate images by perceptual hash and mark one canonical file per group. | M | 95% or more of the known duplicates in the golden set are grouped, with under 2% false grouping. |
| FR-TRI-03 | The system shall keep every duplicate file and its hash. Grouping changes only how files are displayed. | M | All originals stay listed in the full manifest. |
| FR-TRI-04 | The system shall compute a manipulation-screening score (0–1) and reasons for each image. | M | Score and reasons are present for every image or the file is marked "not screened". |
| FR-TRI-05 | The system shall present screening results only as "recommend forensic review" or "no screening concern", with confidence and a fixed statement of the method's limits. | M | The UI never uses the words "fake", "forged" or "authentic"; the limitations text appears on every flag. |
| FR-TRI-06 | The system shall produce a ranked forensic referral list from the screening score, the evidence's importance to the timeline, and any metadata conflicts. | M | The list is ordered and each item carries a reason. |
| FR-TRI-07 | The system shall screen audio for signs of synthetic speech. | C | — (post-pilot) |

**FR-MET — Metadata Agent**

| ID | Requirement | Pri. | Acceptance criterion |
| --- | --- | --- | --- |
| FR-MET-01 | The system shall extract EXIF (capture time, device, software, GPS), PDF metadata and audio tags where present. | M | Fields match `exiftool` output on the test set. |
| FR-MET-02 | The system shall reverse-geocode GPS coordinates using the self-hosted geocoder only. | M | No outbound geocoding traffic during tests (checked against the network egress log). |
| FR-MET-03 | The system shall mark each metadata check as absent, consistent or conflict, and show absence neutrally. | M | A WhatsApp-stripped image shows "metadata not available" and isn't flagged. |
| FR-MET-04 | The system shall flag a conflict when the capture time is later than the upload time, the editing-software tag doesn't fit the claimed source, or the GPS location contradicts the stated place by more than a set distance. | M | Each conflict type triggers on its test fixture. |

**FR-TML — Timeline Agent**

| ID | Requirement | Pri. | Acceptance criterion |
| --- | --- | --- | --- |
| FR-TML-01 | The system shall extract events (time, actor, action, amount, account, place) from chats, SMS, statements, call logs, narration and metadata. | M | Event recall of 90% or more on the golden set. |
| FR-TML-02 | The system shall link every event to at least one source (file and line or position, or narration segment). | M | 100% of events have a `source_ref`; clicking it opens the source. |
| FR-TML-03 | The system shall normalise all times to IST and record their precision (exact, day or approximate). | M | Mixed-format fixtures normalise correctly. |
| FR-TML-04 | The system shall merge events that describe the same occurrence from several sources, and show all the sources. | M | A bank SMS and a statement line for the same transfer become one event with two sources. |
| FR-TML-05 | The system shall display the timeline in vis-timeline with filters by type and person, and zoom. | M | 200 events render in under 1 s. |
| FR-TML-06 | The system shall not create any event that lacks a supporting source. | M | Zero events without a source on the golden set. |

**FR-GAP — Gap Hunter Agent**

| ID | Requirement | Pri. | Acceptance criterion |
| --- | --- | --- | --- |
| FR-GAP-01 | The system shall run rules G-01 to G-09 (TRD §2.6) after every timeline build. | M | Each rule fires on its fixture and stays silent on the clean fixture. |
| FR-GAP-02 | The system shall run only reviewed, parameterised Cypher queries, never Cypher written by the model. | M | Code review and test: injected Cypher in evidence text has no effect. |
| FR-GAP-03 | The system shall phrase each gap as a neutral question addressed to the officer. | M | A wording linter blocks a list of judgement words ("lying", "suspicious", "inconsistent story", "credibility" and similar). |
| FR-GAP-04 | The system shall never compute or display any credibility, truthfulness or deception score. | M | No such field exists in the schema or UI (design review). |
| FR-GAP-05 | The system shall let the officer answer a gap (by text, voice or new file) or dismiss it with a required reason. | M | A dismissal without a reason is rejected. |
| FR-GAP-06 | The system shall re-run the affected agents after an answer and update gap statuses. | M | The re-run finishes within 30 s on reference hardware. |
| FR-GAP-07 | The system shall show unresolved gaps on the SHO's approval screen. | M | Approval with open high-severity gaps needs an explicit acknowledgement. |

**FR-DRF — Draft FIR and BNS suggestions**

| ID | Requirement | Pri. | Acceptance criterion |
| --- | --- | --- | --- |
| FR-DRF-01 | The system shall generate an English narrative in chronological order using only extracted events. | M | Every sentence maps to at least one event ID (hidden trace data); no invented facts on the golden set. |
| FR-DRF-02 | The system shall include an evidence manifest: file, type, hash, duplicate group, screening result and metadata status. | M | Manifest rows equal the number of uploaded files. |
| FR-DRF-03 | The system shall suggest BNS sections, each with the statute text, the supporting facts, and the label "Advisory: for officer decision". | M | Every suggestion has an excerpt and at least one event link. |
| FR-DRF-04 | The system shall suggest only sections found in the local BNS corpus. | M | Any section outside the corpus is discarded and logged. |
| FR-DRF-05 | The system shall require the SHO to accept or reject each suggestion before approval. | M | Approval is blocked while any suggestion is pending. |
| FR-DRF-06 | The system shall let officers edit the draft freely, saving each save as a new version. | M | Version history can be shown with a diff. |
| FR-DRF-07 | The system shall never submit, file or transmit the FIR to any outside system. | M | No submission endpoint exists; egress test passes. |
| FR-DRF-08 | The system shall produce a Malayalam rendering of the final narrative for reading back to the complainant. | S | Rendering is available after approval. |

**FR-AUD — Chain of custody and audit**

| ID | Requirement | Pri. | Acceptance criterion |
| --- | --- | --- | --- |
| FR-AUD-01 | The system shall append an audit entry for every upload, view of an original, analysis run, edit, decision, approval, export and login. | M | A scripted session produces the expected entries. |
| FR-AUD-02 | The system shall chain audit entries with SHA-256 as defined in TRD §2.7. | M | Recomputing the chain matches the stored hashes. |
| FR-AUD-03 | The system shall detect and report any altered, deleted or reordered entry. | M | Tampering with one row in the test database makes verification fail at that row. |
| FR-AUD-04 | The system shall produce a signed daily station digest of all case head hashes. | S | The digest signature verifies with the station's public key. |
| FR-AUD-05 | The database shall allow only appends to the audit table. | M | UPDATE and DELETE are denied for the application role. |

**FR-EXP — Export and verification**

| ID | Requirement | Pri. | Acceptance criterion |
| --- | --- | --- | --- |
| FR-EXP-01 | The system shall export the approved draft as PDF (A4, English plus Malayalam annex) and JSON. | M | Files open in standard readers; JSON validates against its schema. |
| FR-EXP-02 | The system shall print a QR code on the PDF that encodes the case reference, export version and head hash. | M | Scanning it on the station network opens the verification result. |
| FR-EXP-03 | The system shall export the forensic referral sheet with file hashes, ranks and reasons. | M | Hashes on the sheet match the stored originals. |
| FR-EXP-04 | The system shall pre-fill hash and device details for an electronic-evidence certificate under BSA Section 63 (verify). | S | Template fields are populated from the manifest. |

**FR-ADM — Administration**

| ID | Requirement | Pri. | Acceptance criterion |
| --- | --- | --- | --- |
| FR-ADM-01 | The administrator shall create, edit, disable and re-enable users and assign roles. | M | A disabled user can't log in; history is kept. |
| FR-ADM-02 | The system shall show service health and pipeline error rates to administrators. | S | The dashboard shows status for every service. |
| FR-ADM-03 | The system shall let administrators set retention periods and run purges, with the case number and an approval recorded. | S | A purge leaves a tombstone entry in the audit chain. |

## 3.4 Non-functional requirements

| ID | Category | Requirement | Pri. |
| --- | --- | --- | --- |
| NFR-PERF-01 | Performance | Meet the budgets in TRD §2.12 on reference hardware. | M |
| NFR-PERF-02 | Performance | Support 5 concurrent officers per station without breaching the budgets. | M |
| NFR-REL-01 | Reliability | 99.5% availability during station working hours, measured monthly. | M |
| NFR-REL-02 | Reliability | A failed or timed-out model call shall never block manual completion of the FIR. | M |
| NFR-REL-03 | Reliability | Resume a pipeline from its last checkpoint after a worker restart. | M |
| NFR-REL-04 | Reliability | RPO 24 h and RTO 8 h, with a monthly restore drill. | M |
| NFR-SEC-01 | Security | Meet OWASP ASVS Level 2. | M |
| NFR-SEC-02 | Security | TLS 1.2 or later on all internal traffic; encrypted disks; personal-data columns encrypted with AES-256-GCM. | M |
| NFR-SEC-03 | Security | The only outbound network path is the LLM Gateway through an allowlisted proxy (or none, in local mode). | M |
| NFR-SEC-04 | Security | No personal data or evidence content in application logs. | M |
| NFR-SEC-05 | Security | Prompt-injection and Cypher-injection test suites pass before each release. | M |
| NFR-PRIV-01 | Privacy | Only redacted text is sent to an external LLM; raw media is never sent. | M |
| NFR-PRIV-02 | Privacy | All data is stored in India, inside the agency's environment. | M |
| NFR-PRIV-03 | Privacy | Consent is recorded with the version of the notice the complainant was shown. | M |
| NFR-USE-01 | Usability | A new officer completes a standard case after 1 hour of training. | M |
| NFR-USE-02 | Usability | SUS score of 70 or more in pilot surveys. | S |
| NFR-USE-03 | Usability | WCAG 2.1 AA for contrast and keyboard navigation. | S |
| NFR-LOC-01 | Localisation | The interface is in English with Malayalam labels available. Malayalam text renders correctly using locally bundled fonts. | M |
| NFR-MNT-01 | Maintainability | Model IDs, prompt versions, thresholds and rule parameters are set in configuration, not in code. | M |
| NFR-MNT-02 | Maintainability | 80% or more unit-test coverage on core modules; CI runs on every merge. | M |
| NFR-AI-01 | Responsible AI | Every AI output in the interface is labelled as AI-generated, with its source links. | M |
| NFR-AI-02 | Responsible AI | Screening and gap results show stated limitations; no credibility scoring of any kind. | M |
| NFR-AI-03 | Responsible AI | Before each release, publish the measured error rates (WER, event recall, screening false positives and false negatives) in an internal model card. | M |

## 3.5 Use cases

| ID | Use case | Actor | Main flow | Alternate flows |
| --- | --- | --- | --- | --- |
| UC-01 | Register a complaint with evidence | FIR writer | Open case → record consent → upload files → record narration → start analysis → watch progress | File rejected (type or size) → reason shown, others continue · transcription fails → officer types the narration |
| UC-02 | Resolve gaps with the complainant present | FIR writer | Open the gap list → ask each question → record the answer or add a file → partial re-run → status updates | Complainant doesn't know → mark "answered: not known" · not relevant → dismiss with a reason |
| UC-03 | Review and approve the draft | SHO | Review narrative → decide each BNS suggestion → review referrals → acknowledge open gaps → approve | Send back to the writer with a comment |
| UC-04 | Export and file | SHO | Export the PDF and JSON → file through the official channel (outside TRACE) → record the official FIR number in TRACE | Re-export creates a new version; the earlier ones remain |
| UC-05 | Verify an exported document | IO, auditor, court liaison | Scan the QR code → the system recomputes the chain → shows a match or a mismatch | Chain broken → mismatch at a specific entry, and an alert to the administrator |
| UC-06 | Process a forensic referral | Forensic analyst | Open the referral queue → download originals (logged) → record the outcome per file | — |

## 3.6 External interfaces

- **User interface:** responsive web app, desktop-first. Main screens: Case list, Intake, Narration, Analysis progress, Timeline, Gaps, Draft and BNS, Approval, Audit, Admin.
- **Hardware:** a USB microphone or headset; optionally a document scanner (images upload like any other file).
- **Software:** the LLM provider API through the gateway; the local Nominatim, ClamAV, MinIO, Neo4j and Postgres services.
- **Communications:** HTTPS only; SSE for progress updates; no inbound connections from outside the station network.

## 3.7 Traceability

| PRD feature | Requirements | Verified by |
| --- | --- | --- |
| F1 Intake | FR-CASE-01..04, FR-INT-01..08 | Integration tests, security tests |
| F2 Narration | FR-NAR-01..06 | WER benchmark, golden set |
| F3 Triage | FR-TRI-01..07 | Golden set, D6 calibration report |
| F4 Metadata | FR-MET-01..04 | Fixtures, egress test |
| F5 Timeline, F11 Timeline view | FR-TML-01..06 | Golden set, UI performance test |
| F6 Gap Hunter | FR-GAP-01..07 | Rule fixtures, wording linter, injection tests |
| F7 Draft FIR | FR-DRF-01..08 | Golden set (no invented facts), approval tests |
| F8 Custody and audit | FR-AUD-01..05 | Tamper tests |
| F9 Export | FR-EXP-01..04 | Export and QR tests |
| F10 Users and roles | FR-AUTH-01..05, FR-ADM-01..03 | Role-permission matrix test |
| F12 Certificate helper | FR-EXP-04 | Legal review of the template |
