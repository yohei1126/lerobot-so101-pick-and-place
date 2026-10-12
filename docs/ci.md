# CI（ローカル相当）

```bash
pip install -e "port_pick_align/[training,dev]"

ruff check port_pick_align scripts
ruff format --check port_pick_align scripts
(cd port_pick_align && mypy src/port_pick_align)

(cd port_pick_align && pytest -m unit -q)
(cd port_pick_align && pytest -m integration -q)
```

GitHub Actions（`.github/workflows/ci.yml`）では lint と unit を並列実行し、unit 成功後に integration を実行する。
