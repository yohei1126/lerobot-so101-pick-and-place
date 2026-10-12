# 解説レポート（提出 PDF）雛形

公式提出物は **PDF のみ**。原稿の正本はこのディレクトリの Markdown。

## 提出ファイル名

```text
説明資料_PAI最終課題_yohei1126.pdf
```

- OmniCampus アカウント名: `yohei1126`
- 氏名・所属・メールアドレスなどの個人情報は一切記載しない

## PDF 生成

依存: `pandoc` と `typst`（スクリプトが `--pdf-engine=typst` で固定）。

```bash
# リポジトリルートから
./scripts/build_report_pdf.sh yohei1126
```

出力先: `report/説明資料_PAI最終課題_yohei1126.pdf`（gitignore 対象）

入力の既定は [`説明資料_PAI最終課題_yohei1126.md`](説明資料_PAI最終課題_yohei1126.md)。別ファイルを使う場合:

```bash
./scripts/build_report_pdf.sh yohei1126 path/to/draft.md
```

## 個人情報チェックリスト（提出前）

- [ ] 表紙・本文に氏名・所属・メール・電話・学生証番号がない
- [ ] 図・スクリーンショットに氏名やメールが映り込んでいない
- [ ] OmniCampus アカウント名（`yohei1126`）以外の個人識別子を書いていない
- [ ] 出力 PDF のファイル名が公式規則どおりである
- [ ] GitHub README / コミットメッセージにもメール等を載せていない（公開リポジトリ）

## 関連

- 提出全体: [`docs/submission.md`](../docs/submission.md)
- ハード縮退: [`docs/plan_b.md`](../docs/plan_b.md)
