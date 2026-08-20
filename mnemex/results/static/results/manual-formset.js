(() => {
  "use strict";

  const rowsContainer = document.getElementById("manual-result-rows");
  const emptyRowTemplate = document.getElementById("empty-result-row");
  const addButton = document.getElementById("add-result-row");
  const countStatus = document.getElementById("result-row-count");
  const totalForms = document.querySelector('input[name="rows-TOTAL_FORMS"]');
  const configuredMaximum = document.querySelector('input[name="rows-MAX_NUM_FORMS"]');
  const maximumRows = Math.min(Number(configuredMaximum?.value) || 25, 25);

  if (!rowsContainer || !emptyRowTemplate || !addButton || !totalForms) {
    return;
  }

  const replaceIndex = (value, index) =>
    value.replace(/rows-(?:\d+|__prefix__)-/g, `rows-${index}-`);

  const refreshManagementState = () => {
    const rows = [...rowsContainer.querySelectorAll(".manual-result-row")];
    rows.forEach((row, index) => {
      row.dataset.formIndex = String(index);
      row.querySelectorAll("[name]").forEach((field) => {
        field.name = replaceIndex(field.name, index);
      });
      row.querySelectorAll("[id]").forEach((field) => {
        field.id = replaceIndex(field.id, index);
      });
      row.querySelectorAll("label[for]").forEach((label) => {
        label.htmlFor = replaceIndex(label.htmlFor, index);
        label.textContent = `Row ${index + 1} ${label.dataset.fieldLabel || "field"}`;
      });
      const removeButton = row.querySelector(".remove-result-row");
      if (removeButton) {
        removeButton.textContent = `Remove row ${index + 1}`;
        removeButton.setAttribute("aria-label", `Remove result row ${index + 1}`);
        removeButton.disabled = rows.length === 1;
      }
    });
    totalForms.value = String(rows.length);
    addButton.disabled = rows.length >= maximumRows;
    countStatus.textContent = `${rows.length} of ${maximumRows} result rows`;
  };

  addButton.addEventListener("click", () => {
    const currentCount = rowsContainer.querySelectorAll(".manual-result-row").length;
    if (currentCount >= maximumRows) {
      return;
    }
    const fragment = emptyRowTemplate.content.cloneNode(true);
    rowsContainer.appendChild(fragment);
    refreshManagementState();
    rowsContainer.querySelector(".manual-result-row:last-child input")?.focus();
  });

  rowsContainer.addEventListener("click", (event) => {
    const removeButton = event.target.closest(".remove-result-row");
    if (!removeButton) {
      return;
    }
    const rows = rowsContainer.querySelectorAll(".manual-result-row");
    if (rows.length <= 1) {
      return;
    }
    removeButton.closest(".manual-result-row")?.remove();
    refreshManagementState();
  });

  refreshManagementState();
})();
