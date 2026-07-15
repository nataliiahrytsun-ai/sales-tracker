"use strict";

(() => {
  for (const filter of document.querySelectorAll("[data-date-filter]")) {
    const fromInput = filter.querySelector("[data-filter-from]");
    const toInput = filter.querySelector("[data-filter-to]");
    const applyButton = filter.querySelector("[data-filter-apply]");
    const resetButton = filter.querySelector("[data-filter-reset]");

    if (!fromInput || !toInput || !applyButton || !resetButton) {
      continue;
    }

    const updateButtons = () => {
      const fromValue = fromInput.value;
      const toValue = toInput.value;
      const isComplete = fromValue !== "" && toValue !== "";
      const isValid = (
        isComplete
        && fromValue <= toValue
        && toValue <= filter.dataset.defaultTo
      );
      const hasChanged = (
        fromValue !== filter.dataset.appliedFrom
        || toValue !== filter.dataset.appliedTo
      );
      const isDefault = (
        fromValue === filter.dataset.defaultFrom
        && toValue === filter.dataset.defaultTo
      );

      applyButton.disabled = !isValid || !hasChanged;
      resetButton.disabled = isDefault;
    };

    fromInput.addEventListener("input", updateButtons);
    fromInput.addEventListener("change", updateButtons);
    toInput.addEventListener("input", updateButtons);
    toInput.addEventListener("change", updateButtons);
    updateButtons();
  }
})();
