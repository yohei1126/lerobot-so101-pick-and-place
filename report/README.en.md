# Submission report (PDF) build procedure

The official submission for this assignment is a PDF document only. The canonical manuscript is the Markdown file in this directory (`説明資料_PAI最終課題_yohei1126.md`), and the build script produces the PDF.

## Submission file specification

Name the submission file according to the course specification as follows.

```text
説明資料_PAI最終課題_yohei1126.pdf
```

- OmniCampus account name: `yohei1126`
- Anonymity: Do not include personally identifying information such as real name, affiliation, or email address.

## PDF build procedure

This build uses `pandoc` and `typst` (`--pdf-engine=typst`) internally.

```bash
# Run from the repository root
./scripts/build_report_pdf.sh yohei1126
```

After execution, the PDF is written to `report/説明資料_PAI最終課題_yohei1126.pdf` (not tracked by Git).

By default, [`説明資料_PAI最終課題_yohei1126.md`](説明資料_PAI最終課題_yohei1126.en.md) is used as the input manuscript. To use a different draft, pass its path as the second argument.

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
