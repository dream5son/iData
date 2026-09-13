# IDI Backend

FastAPI 服务：数据源生命周期、深度连接测试、元数据抽取/同步/快照。

## 本地运行

```bash
cd apps/idi/backend
python3 -m pip install -e .
export IDI_DATA_DIR=/tmp/idi-data
python3 src/main.py
```

## 测试

```bash
PYTHONPATH=src python3 -m pytest -q
```

本地无真实库时，创建数据源可在 `params` 中设置 `__sqlite_path` 与 `__skip_tcp`，走 SQLite 桥接完成测连与反射。
