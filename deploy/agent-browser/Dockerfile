FROM ghcr.io/openhands/agent-server:1.59.0-python@sha256:96038f92dc66228e389a95c2e5081dfc2cd4f5d307f051a7df9b1d50ccb86be7
USER root
COPY requirements.lock /tmp/onefde-browser-requirements.lock
RUN --mount=type=bind,from=wheelhouse,target=/tmp/onefde-browser-wheels,ro \
    python -m pip install --no-cache-dir --no-index --require-hashes \
      --find-links=/tmp/onefde-browser-wheels -r /tmp/onefde-browser-requirements.lock \
    && python -c "from playwright.sync_api import sync_playwright; import shutil; assert shutil.which('chromium')"
ENV ONEFDE_CHROMIUM_EXECUTABLE=/usr/bin/chromium
USER 10001:10001
