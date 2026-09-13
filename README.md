# iData

Intelligent Data Agent monorepo.

## IDI（本批）

实施工程师侧数据源接入与元数据治理（US-001～US-006）。设计见 `docs/design/idi-us001-006.md`。

### 启动后端

```bash
cd apps/idi/backend
python3 -m pip install -e .
IDI_DATA_DIR=/tmp/idi-data python3 src/main.py
```

### 启动前端

```bash
cd apps/idi/frontend
npm install
NEXT_PUBLIC_IDI_API_BASE=http://127.0.0.1:8000 npm run dev
```

### 验证

```bash
cd apps/idi/backend
PYTHONPATH=src python3 -m pytest -q
```
