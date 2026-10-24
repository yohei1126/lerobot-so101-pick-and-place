# Submission requirements and checklist

OmniCampus needs a PDF report, a public GitHub URL, and a 1–3 minute YouTube task video for the University of Tokyo “Physical AI Applied Course 1” final assignment. Deadline: 2026-11-02 10:00 JST. The authoritative course spec follows the L07 overview materials in the course repository.

## Schedule

| Item | Date/time |
| --- | --- |
| Submission opens | 2026-10-19 (Mon) |
| Deadline | 2026-11-02 (Mon) 10:00 (JST) |

## OmniCampus requirements

### 1. PDF report (filename and build)

- Filename: `説明資料_PAI最終課題_yohei1126.pdf`
- Report source: [`report/説明資料_PAI最終課題_yohei1126.md`](../report/説明資料_PAI最終課題_yohei1126.en.md)
- Build command:
  ```bash
  ./scripts/build_report_pdf.sh yohei1126
  ```

### 2. Source repository (GitHub URL)

- Visibility: must be Public.
- Enter the repository top-level URL in the submission form.

## YouTube video requirements

| Item | Spec |
| --- | --- |
| Content | Continuous robot (real or simulated) task execution (MP4) |
| Length | 1–3 minutes (speed-up allowed; if used, state it in on-screen text or the description) |
| Title | `PAI最終課題_yohei1126` |
| Visibility | Unlisted (required) or public (recommended; bonus eligible) |
| Options | Select “Not made for kids” and “No age restriction”; disable Premiere |

## Personal information policy

Do not include or film personally identifiable information (name, affiliation, email, phone, etc.) in any submission artifact (PDF report, source, commit history, video).  
The only allowed identifier is the OmniCampus account name (`yohei1126`). See [`report/README.md`](../report/README.en.md) for details.

## Rubric ↔ report chapter mapping

| Criterion | Report chapter |
| --- | --- |
| Creativity | Ch.1 (problem setting and social context) |
| Technical skill | Ch.2 (system design), Ch.3 (data quality), Ch.4 (model choice / training) |
| Practicality | Ch.5 (quantitative eval), Ch.7 (field deployment vision) |
| Presentation | Ch.8 (results video structure) |

Hardware delay/failure or failed runs remain valid evaluation targets if Chapter 6 argues root cause and technical improvements. For degraded operation when the real robot is unavailable, see [plan_b.md](plan_b.en.md).

## Pre-submission checklist

- [ ] PDF filename matches `説明資料_PAI最終課題_yohei1126.pdf`
- [ ] GitHub repository is Public
- [ ] YouTube title, length, and visibility meet requirements
- [ ] Confirmed no personally identifiable information in any submission artifact
- [ ] (If Plan B) Simulation or public-data execution video and discussion are complete
