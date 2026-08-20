(() => {
  "use strict";

  const dialog = document.getElementById("privileged-action-step-up");
  if (!dialog || typeof dialog.showModal !== "function" || !window.fetch || !window.FormData) {
    return;
  }
  const endpoint = dialog.dataset.endpoint;
  const codeField = dialog.querySelector("[data-step-up-code-field]");
  const codeInput = dialog.querySelector("#privileged-action-step-up-code");
  const status = dialog.querySelector("[data-step-up-status]");
  const verify = dialog.querySelector("[data-step-up-verify]");
  const confirm = dialog.querySelector("[data-step-up-confirm]");
  const cancel = dialog.querySelector("[data-step-up-cancel]");
  const inFlightForms = new WeakSet();
  let pendingForm = null;
  let pendingTicket = null;

  const csrfToken = (form) => form.querySelector("input[name=csrfmiddlewaretoken]")?.value || "";
  const formTarget = (form) => form.getAttribute("action") || window.location.href;
  const targetPath = (form) => new URL(formTarget(form), window.location.href).pathname;
  const setFormPending = (form, pending) => {
    form.querySelectorAll('button[type="submit"], input[type="submit"]').forEach((control) => {
      control.disabled = pending;
    });
  };

  async function requestTicket(form, code) {
    const body = new FormData();
    body.set("target_path", targetPath(form));
    body.set("target_method", (form.method || "POST").toUpperCase());
    if (code) body.set("code", code);
    return fetch(endpoint, {
      method: "POST",
      credentials: "same-origin",
      headers: {"X-CSRFToken": csrfToken(form), "Accept": "application/json"},
      body,
    });
  }

  function openForCode(form) {
    pendingForm = form;
    pendingTicket = null;
    codeField.hidden = false;
    verify.hidden = false;
    confirm.hidden = true;
    status.textContent = "Enter a current code. Nothing will be submitted yet.";
    dialog.showModal();
    codeInput.focus();
  }

  async function submitWithTicket(form, ticket) {
    status.textContent = "Submitting once…";
    const response = await fetch(formTarget(form), {
      method: (form.method || "POST").toUpperCase(),
      credentials: "same-origin",
      headers: {"X-MNEMEX-Action-Ticket": ticket, "Accept": "text/html"},
      body: new FormData(form),
    });
    if (response.redirected) {
      window.location.assign(response.url);
      return;
    }
    if (
      response.ok &&
      response.headers.get("X-MNEMEX-One-Time-Result") === "invitation-secret-v1"
    ) {
      const oneTimeDocument = await response.text();
      document.open();
      document.write(oneTimeDocument);
      document.close();
      return;
    }
    pendingTicket = null;
    inFlightForms.delete(form);
    setFormPending(form, false);
    status.textContent = "The server did not accept the action. Your form is unchanged; verify and try again.";
    codeField.hidden = false;
    verify.hidden = false;
    confirm.hidden = true;
    codeInput.focus();
  }

  document.querySelectorAll("main form[method=post], main form[method=POST]").forEach((form) => {
    form.addEventListener("submit", async (event) => {
      if (form.dataset.noPrivilegedStepUp !== undefined) return;
      event.preventDefault();
      if (inFlightForms.has(form)) return;
      inFlightForms.add(form);
      setFormPending(form, true);
      pendingForm = form;
      try {
        const response = await requestTicket(form, "");
        const payload = await response.json();
        if (response.ok && payload.ticket) {
          await submitWithTicket(form, payload.ticket);
        } else if (response.status === 428) {
          openForCode(form);
        } else {
          openForCode(form);
          status.textContent = "Verification is unavailable. Your form is unchanged.";
        }
      } catch (_error) {
        openForCode(form);
        status.textContent = "Verification is unavailable. Your form is unchanged.";
      }
    });
  });

  verify.addEventListener("click", async () => {
    if (!pendingForm) return;
    verify.disabled = true;
    status.textContent = "Checking code…";
    try {
      const response = await requestTicket(pendingForm, codeInput.value);
      const payload = await response.json();
      if (response.ok && payload.ticket) {
        pendingTicket = payload.ticket;
        codeInput.value = "";
        codeField.hidden = true;
        verify.hidden = true;
        confirm.hidden = false;
        status.textContent = "Verified. Choose Submit now to send this form once.";
        confirm.focus();
      } else {
        status.textContent = "That code was not accepted. Your form is unchanged.";
        codeInput.select();
      }
    } catch (_error) {
      status.textContent = "Verification is unavailable. Your form is unchanged.";
    } finally {
      verify.disabled = false;
    }
  });

  confirm.addEventListener("click", async () => {
    if (!pendingForm || !pendingTicket) return;
    confirm.disabled = true;
    try {
      await submitWithTicket(pendingForm, pendingTicket);
    } catch (_error) {
      pendingTicket = null;
      inFlightForms.delete(pendingForm);
      setFormPending(pendingForm, false);
      status.textContent = "Submission is unavailable. Your form is unchanged.";
      codeField.hidden = false;
      verify.hidden = false;
      confirm.hidden = true;
    } finally {
      confirm.disabled = false;
    }
  });

  cancel.addEventListener("click", () => {
    if (pendingForm) {
      inFlightForms.delete(pendingForm);
      setFormPending(pendingForm, false);
    }
    pendingForm = null;
    pendingTicket = null;
    codeInput.value = "";
    dialog.close();
  });
})();
