"use strict";

document.querySelectorAll("[data-dashboard-filter]").forEach((form) => {
  const period = form.querySelector("[data-period-select]");
  const customDates = form.querySelector("[data-custom-dates]");
  const fromInput = form.querySelector("[data-from]");
  const toInput = form.querySelector("[data-to]");
  const applyButton = form.querySelector("[data-apply]");
  const resetButton = form.querySelector("[data-reset]");
  const initial = {
    period: form.dataset.initialPeriod,
    from: form.dataset.initialFrom,
    to: form.dataset.initialTo,
  };

  const isCustom = () => period.value === "custom";
  const isValid = () => {
    if (!isCustom()) return true;
    return Boolean(
      fromInput.value &&
      toInput.value &&
      fromInput.value <= toInput.value &&
      toInput.value <= form.dataset.today,
    );
  };
  const isChanged = () => {
    if (period.value !== initial.period) return true;
    if (!isCustom()) return false;
    return fromInput.value !== initial.from || toInput.value !== initial.to;
  };
  const isDefault = () => period.value === "current-week";

  const update = () => {
    customDates.hidden = !isCustom();
    fromInput.disabled = !isCustom();
    toInput.disabled = !isCustom();
    applyButton.disabled = !(isChanged() && isValid());
    resetButton.disabled = isDefault();
  };

  period.addEventListener("change", update);
  fromInput.addEventListener("input", update);
  toInput.addEventListener("input", update);
  update();
});

document.querySelectorAll("[data-grouped-chart]").forEach((chart) => {
  chart.style.setProperty("--chart-columns", chart.dataset.columns);
  chart.querySelectorAll("[data-bar-height]").forEach((barGroup) => {
    barGroup.style.setProperty(
      "--bar-height",
      `${barGroup.dataset.barHeight}%`,
    );
  });
});
