# iData

Intelligent Data Agent monorepo skeleton.

## Project Structure

```text
apps/
  ida/
    frontend/
    backend/
      sandbox/
  idi/
    frontend/
    backend/
      metadata/
  shared/
    types/
    proto/
docs/
```

## Module Overview

- `apps/ida/frontend`: 面向终端用户的请求输入与结果展示前端骨架
- `apps/ida/backend`: 面向终端用户的编排与执行后端骨架
- `apps/ida/backend/sandbox`: 面向 IDA 的 Python 数据后处理沙箱骨架
- `apps/idi/frontend`: 面向实施工程师的治理与配置前端骨架
- `apps/idi/backend`: 面向实施工程师的 Python 后端骨架
- `apps/idi/backend/metadata`: 面向 IDI 的元数据处理骨架
- `apps/shared/types`: ida/idi 共享类型骨架
- `apps/shared/proto`: ida/idi 与 Python 服务共享协议骨架
