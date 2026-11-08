(() => {
  "use strict";
  const panel = document.querySelector("#business");
  const form = panel.querySelector("form");
  const fields = form.elements;
  const historyList = panel.querySelector("ol");
  const status = panel.querySelector("[role=status]");
  const retest = panel.querySelector("#business-retest");
  const followLink = panel.querySelector("#business-follow-link");
  const parameters = new URLSearchParams(location.hash.slice(1));
  // A pasted invitation or follow-up link can change only the fragment of this page.
  window.addEventListener("hashchange", () => location.reload());
  const invitation = parameters.get("invite");
  panel.querySelector("#business-consent").hidden = !invitation;
  const apiOrigin = panel.dataset.apiOrigin;
  let caseId = parameters.get("case");
  let token = parameters.get("token");
  let started = Boolean(caseId && token);
  let pending;
  let state = "open";

  function newCredential() {
    return Array.from(crypto.getRandomValues(new Uint8Array(32)),
      (byte) => byte.toString(16).padStart(2, "0")).join("");
  }

  async function call(path = "", method = "GET", data) {
    const response = await fetch(
      apiOrigin + "/api/v1/public/business/conversations/" + encodeURIComponent(caseId) + path,
      {
        method,
        credentials: "omit",
        headers: { Authorization: "Bearer " + token, ...(data && { "Content-Type": "application/json" }) },
        body: data && JSON.stringify(data),
      },
    );
    const result = await response.json();
    if (!response.ok) throw new Error(result.message || "会话操作失败");
    return result;
  }

  async function refresh() {
    if (!started) return;
    let result = await call();
    const messages = [...result.messages];
    while (result.has_more) {
      result = await call("?after=" + result.last_message_id);
      messages.push(...result.messages);
    }
    state = result.state;
    historyList.replaceChildren(...messages.map((message) => {
      const item = document.createElement("li");
      item.dataset.message = message.id;
      item.dataset.kind = message.kind;
      item.textContent = (message.kind === "customer" ? "你　" : "Business　") + message.text;
      return item;
    }));
    followLink.hidden = false;
    followLink.href = location.href;
    form.hidden = state === "closed";
    retest.hidden = state !== "awaiting_retest";
    retest.dataset.notice = result.retest_notice_id ?? "";
    status.textContent = state === "closed" ? "客户已确认，会话已关闭。" :
      state === "awaiting_retest" ? "修复版本已就绪，等待你的复试。" : "会话已保存。";
  }

  async function run(action) {
    const buttons = [...panel.querySelectorAll("button")];
    if (buttons.some((button) => button.disabled)) return;
    buttons.forEach((button) => { button.disabled = true; });
    status.textContent = "正在处理…";
    try {
      await action();
    } catch (error) {
      status.textContent = error.message;
    } finally {
      buttons.forEach((button) => { button.disabled = false; });
    }
  }

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    run(async () => {
      caseId ||= crypto.randomUUID();
      token ||= newCredential();
      const data = {
        text: fields.text.value,
        project_hint: fields.project_hint.value.trim() || null,
        version_hint: fields.version_hint.value.trim() || null,
        willing_to_continue: fields.willing_to_continue.checked,
        ...(!started && { invitation_id: invitation }),
      };
      const fingerprint = JSON.stringify(data);
      if (pending?.fingerprint !== fingerprint) {
        pending = { fingerprint, id: crypto.randomUUID() };
      }
      await call(started ? "/messages" : "", started ? "POST" : "PUT",
        { ...data, request_id: pending.id });
      started = true;
      pending = undefined;
      const fragment = new URLSearchParams({ case: caseId, token });
      if (invitation) fragment.set("invite", invitation);
      window.history.replaceState(null, "", "#" + fragment);
      fields.text.value = "";
      await refresh();
    });
  });
  panel.querySelector("#business-refresh").addEventListener("click", () => run(refresh));
  retest.addEventListener("submit", (event) => {
    event.preventDefault();
    run(async () => {
      const passed = event.submitter.value === "passed";
      const data = {
        notice_id: Number(retest.dataset.notice), passed,
        text: retest.elements.result.value || (passed ? "复试通过，可以使用。" : ""),
      };
      if (!data.text.trim()) throw new Error("请描述仍失败的操作或提示。");
      const fingerprint = JSON.stringify(data);
      if (pending?.fingerprint !== fingerprint) {
        pending = { fingerprint, id: crypto.randomUUID() };
      }
      await call("/retest", "POST", { ...data, request_id: pending.id });
      pending = undefined;
      retest.reset();
      await refresh();
    });
  });
  if (started) run(refresh);
})();
