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

本地无其它库时，创建数据源可选方言 `sqlite`，在 `params.path` 中填写已存在的 SQLite 文件路径，即可完成测连与反射。
