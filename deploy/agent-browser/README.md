# 本地浏览器工程镜像

在固定 OpenHands Agent Server 1.59.0 基础上增加 Python Playwright 1.64.1，沿用基础镜像 Chromium。四个 Python wheel 固定版本和官方 PyPI SHA256，安装阶段断网，工程期间无需下载。镜像运行身份仍为 10001:10001，挂载、网络、资源及停止规则沿用 Worker。

Windows 仓库根目录准备 Linux CPython 3.13 wheel 缓存（缓存位于忽略的 work 中）：

```powershell
python -m pip download --index-url https://pypi.org/simple --require-hashes --only-binary=:all: --platform manylinux1_x86_64 --platform manylinux_2_17_x86_64 --platform manylinux_2_28_x86_64 --python-version 3.13 --implementation cp --abi cp313 --dest work/playwright-wheelhouse -r deploy/agent-browser/requirements.lock
```

将缓存复制到 WSL 仓库同名目录；源码同步脚本排除 work，缓存需单独复制。WSL 仓库根构建：

```bash
docker build --network none --build-context wheelhouse=./work/playwright-wheelhouse -t onefde-agent-browser:1.59.0-playwright1.64.1 deploy/agent-browser
docker image inspect --format '{{.Id}}' onefde-agent-browser:1.59.0-playwright1.64.1
```

构建输出 ID 必须与 `backend/src/onefde/worker/config.py` 的审核值匹配。新构建若产生不同 ID，核对基础镜像、锁文件与浏览器冒烟后明确更新审核值；仅改标签不能通过校验。`/srv/onefde-local/private/compose.env` 的 `ONEFDE_BROWSER_AGENT_IMAGE` 选择该固定 ID，Compose Worker 转成 `ONEFDE_WORKER_SERVER_IMAGE`。不设置时保持原基础镜像。

项目测试使用系统浏览器的实际路径：

```python
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, executable_path="/usr/bin/chromium")
    try:
        page = browser.new_page()
        # Use the project's actual local page and acceptance assertions.
    finally:
        browser.close()
```

Worker 仅在选择已审核浏览器镜像时把包版本与启动参数加入工程上下文。不要用无参数 launch() 隐式要求下载 Playwright 专属浏览器。本地真实点击、手机视口及 MiMo 工程复验见[测试事实](../../docs/operations/testing.md#playwright-与-mimo-技能实测2026-11-07)；不是云端生产隔离验收。
