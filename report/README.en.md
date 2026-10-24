# Submission report (PDF) build procedure

The official submission for this assignment is a PDF document only. While report drafts still live in this directory (`説明資料_PAI最終課題_yohei1126.{ja,en}.md`), the manuscript is planned to move to `yohei1126/utokyo-ai-courses` (`PhysicalAI-Applied1-202609/`). Pass the Markdown path explicitly to the build script.

## Submission file specification

Name the submission file according to the course specification as follows.

```text
説明資料_PAI最終課題_yohei1126.pdf
```

- OmniCampus account name: `yohei1126`
- Anonymity: Do not include personally identifying information such as real name, affiliation, or email address.

## PDF build procedure

This build uses `pandoc` and `typst` (`--pdf-engine=typst`) internally. The input Markdown path is **required**.

```bash
# Run from the repository root (JA manuscript example)
./scripts/build_report_pdf.sh yohei1126 report/説明資料_PAI最終課題_yohei1126.ja.md

# English manuscript
./scripts/build_report_pdf.sh yohei1126 report/説明資料_PAI最終課題_yohei1126.en.md
```

After execution, the PDF is written to `report/説明資料_PAI最終課題_yohei1126.pdf` (not tracked by Git).

To use a draft elsewhere (including after the move to `utokyo-ai-courses`), pass that path as the second argument.

```bash
./scripts/build_report_pdf.sh yohei1126 path/to/draft.md
```

## Pre-submission checklist (privacy)

Before submitting, verify the following so anonymity is preserved.

- [ ] Cover and body contain no real name, affiliation, email, phone number, or student ID
- [ ] Figures and terminal screenshots do not show personal usernames or email addresses
- [ ] No personal identifiers other than the OmniCampus account name (`yohei1126`)
- [ ] Generated PDF filename matches the naming rule
- [ ] Public README and commit history contain no personal contact information

## Related documents

- Full submission requirements: [`docs/submission.md`](../docs/submission.en.md)
- Degraded mode when real-robot work is blocked: [`docs/plan_b.md`](../docs/plan_b.en.md)
