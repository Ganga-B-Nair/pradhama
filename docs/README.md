# TRACE — Temporal-Relational Agentic Correlation Engine: Requirements

Version 1.0 · 16 Oct 2026

## About these documents

These three documents define TRACE v1: a pilot-ready build for one Kerala Cyber Police Station, delivered in 9 months. Seven decisions below must be settled before Month 1 sprint planning; the first one blocks architecture.

| Document | Answers | Main readers |
| --- | --- | --- |
| [PRD.md](PRD.md) — Product Requirements | What we are building, for whom, and why; what success looks like | Founders, Cyberdome partners, mentors, evaluators |
| [TRD.md](TRD.md) — Technical Requirements | How it is built: architecture, agents, data, APIs, security, deployment | Engineers |
| [SRS.md](SRS.md) — Software Requirements Specification | Numbered, testable requirements with acceptance criteria and traceability | Engineers, QA, security auditors |

**Conventions.** "Shall" means mandatory. Priority uses MoSCoW: **M** (Must, v1 pilot), **S** (Should, v1 if time allows), **C** (Could, post-pilot). Requirement IDs (FR-INT-01, NFR-SEC-03) are stable; if a requirement is dropped, mark it withdrawn and don't reuse its ID.

## Decisions to settle before development

| # | Decision | Why it matters | Recommendation |
| --- | --- | --- | --- |
| D1 | **Where the LLM runs.** The pitch says "no evidence leaves the agency's environment", but the stack calls the Anthropic Claude API, which is a cloud service. | This contradiction will be the first question a police IT or security reviewer asks. It also shapes the architecture and the cost model. | Put every model call behind one internal **LLM Gateway** (TRD §2.4). For the pilot, use Claude through an India-region cloud deployment under a written data-processing agreement with the agency, and send only text extracts, never raw media. Keep an on-premise open-weight model as the fallback for air-gapped stations. Reword the pitch to "evidence files never leave the agency; only redacted text is sent for processing" until this is settled. |
| D2 | **Claude model version.** The form names `claude-sonnet-4-6`. | Model versions get retired. Hard-coding one creates a migration risk partway through the pilot. | Default to the current model, `claude-sonnet-5`, set as a configuration value. Pin one version per release and re-run the evaluation set (TRD §2.10) before any upgrade. |
| D3 | **Legal citation for e-FIR and Zero FIR** | The pitch cites BNSS. A wrong section number undermines credibility. | Believed to be **BNSS 2023, Section 173** (an e-FIR must be signed within 3 days). Have a legal mentor verify this before submission (Appendix B). |
| D4 | **Who operates TRACE at the counter** | Officer-only use is simpler. Letting complainants upload files themselves through a link or kiosk adds identity, consent and abuse controls. | v1 is **officer-operated**: the officer uploads with the complainant present. Complainant self-upload (by QR link) is a post-pilot item. |
| D5 | **Integration with CCTNS or the Kerala e-FIR system** | Direct integration needs government approval and API access that won't be ready in 9 months. | v1 exports a draft FIR as PDF and JSON for the officer to transcribe or attach. API integration is a phase-2 item. |
| D6 | **Source of the labelled manipulation dataset** | Without one, false-positive rates can't be stated honestly. | Combine public image-forensics datasets with a synthetic set of WhatsApp-recompressed screenshots made in-house. Record exactly where each part came from. |
| D7 | **Malayalam speech-recognition model** | General-purpose Whisper models are known to be weak on Malayalam. | Benchmark Whisper large-v3 against Indic fine-tuned speech models on 30+ real complaint recordings in Month 1, then choose by word error rate (WER). |


## Appendices

### Appendix A — Glossary

| Term | Meaning |
| --- | --- |
| FIR | First Information Report: the first written record of a cognisable offence |
| e-FIR / Zero FIR | An FIR given by electronic means, or registered at any station regardless of where the offence happened |
| BNS / BNSS / BSA | Bharatiya Nyaya Sanhita, Bharatiya Nagarik Suraksha Sanhita and Bharatiya Sakshya Adhiniyam (all 2023), which replaced the IPC, CrPC and Evidence Act |
| SHO / IO | Station House Officer / Investigating Officer |
| CCTNS | Crime and Criminal Tracking Network and Systems, the national police records system |
| Cyberdome | Kerala Police's cyber security and research centre |
| Malkhana | The station's store for seized property and evidence |
| pHash / dHash | Perceptual hashes: fingerprints of an image that stay similar when it is resized or recompressed |
| DFT / ELA | Discrete Fourier Transform (frequency-domain analysis) / Error Level Analysis (JPEG recompression differences) |
| EXIF | Metadata embedded in an image file (capture time, device, GPS) |
| WER | Word error rate, the standard accuracy measure for speech-to-text |
| SUS | System Usability Scale, a 10-question usability score from 0 to 100 |
| RPO / RTO | Recovery point objective (how much data may be lost) / recovery time objective (how long recovery may take) |
| GeM / KSUM / DPIIT | Government e-Marketplace / Kerala Startup Mission / Department for Promotion of Industry and Internal Trade |

### Appendix B — Legal references to verify

These references were written from memory and have **not been checked against the statute text**. A legal mentor should confirm each one before the proposal is submitted or the BNS corpus is built.

| Reference | Believed to cover | Used in |
| --- | --- | --- |
| BNSS 2023, Section 173 | Information in cognisable cases, including information by electronic communication (e-FIR, to be signed within 3 days) and registration regardless of jurisdiction (Zero FIR) | Problem statement, D3 |
| BNSS 2023, Section 176(3) | Forensic experts visiting crime scenes for offences punishable with 7 years or more | Forensic referral context |
| BSA 2023, Section 63 | Admissibility of electronic records and the required certificate, which includes hash values | F12, FR-EXP-04 |
| BNS 2023, Sections 318–319 | Cheating; cheating by personation | BNS corpus, golden-set cases |
| IT Act 2000, Sections 66C and 66D | Identity theft; cheating by personation using a computer resource | BNS corpus: **cyber-fraud FIRs usually cite IT Act sections too, so the corpus should include them** |
| DPDP Act 2023 | Personal-data processing and the exemptions for state agencies | Privacy design, consent notice |

### Appendix C — Other open questions

- [ ] Is the suggestion corpus BNS only, or BNS plus the IT Act and other special laws? (Recommendation: BNS plus the IT Act for v1.)
- [ ] Retention period for case data and originals after export, set by agency policy.
- [ ] Who signs the pilot MoU, and does it cover the data-processing terms for D1?
- [ ] Do the 30+ consented complaint recordings for the D7 benchmark need ethics or agency approval?
- [ ] Does the station have a GPU-capable server, or is it part of the ₹1.5L pilot hardware line?
- [ ] Should the legal-aid build (US-15) share the codebase with a feature flag, or be a separate product?
