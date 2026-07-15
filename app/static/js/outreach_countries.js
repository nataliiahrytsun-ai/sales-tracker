"use strict";

(() => {
  const rows = document.querySelector("[data-country-rows]");
  const search = document.querySelector("[data-country-search]");
  const addCount = document.querySelector("[data-country-add-count]");
  const addButton = document.querySelector("[data-country-add]");
  const message = document.querySelector("[data-country-message]");
  const summary = document.querySelector("[data-country-summary]");
  const countriesSelected = document.querySelector("[data-countries-selected]");
  const companiesContacted = document.querySelector("[data-companies-contacted]");
  const datalist = document.querySelector("#country_options");

  if (
    !rows || !search || !addCount || !addButton || !message ||
    !summary || !countriesSelected || !companiesContacted || !datalist
  ) {
    return;
  }

  const countries = new Map();
  for (const option of datalist.options) {
    countries.set(option.value.trim().toLocaleLowerCase(), {
      code: option.dataset.countryCode,
      name: option.value,
      option,
    });
  }

  const isWholeNumber = (value) => /^\d+$/.test(value.trim());

  const findRow = (code) => (
    rows.querySelector(`[data-country-row][data-country-code="${code}"]`)
  );

  const setOptionDisabled = (code, disabled) => {
    for (const country of countries.values()) {
      if (country.code === code) {
        country.option.disabled = disabled;
        return;
      }
    }
  };

  const showMessage = (text) => {
    message.textContent = text;
  };

  const updateSummary = () => {
    let total = 0;
    for (const input of rows.querySelectorAll("[data-country-count]")) {
      if (isWholeNumber(input.value)) {
        total += Number.parseInt(input.value, 10);
      }
    }

    countriesSelected.textContent = String(
      rows.querySelectorAll("[data-country-row]").length,
    );
    companiesContacted.textContent = String(total);
  };

  const makeButton = (label, ariaLabel, dataAttribute, className) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = className;
    button.textContent = label;
    button.setAttribute("aria-label", ariaLabel);
    button.setAttribute(dataAttribute, "");
    return button;
  };

  const createRow = (country, count) => {
    const row = document.createElement("div");
    row.className = "country-row";
    row.dataset.countryRow = "";
    row.dataset.countryCode = country.code;

    const name = document.createElement("span");
    name.className = "country-row-name";
    name.textContent = country.name;

    const controls = document.createElement("div");
    controls.className = "country-count-controls";
    const decrease = makeButton(
      "−",
      `Decrease companies contacted in ${country.name}`,
      "data-country-decrease",
      "button button-secondary country-step-button",
    );
    const hiddenCode = document.createElement("input");
    hiddenCode.type = "hidden";
    hiddenCode.name = "country_codes";
    hiddenCode.value = country.code;
    const countInput = document.createElement("input");
    countInput.className = "country-count-input";
    countInput.name = "country_counts";
    countInput.type = "number";
    countInput.min = "0";
    countInput.step = "1";
    countInput.required = true;
    countInput.value = String(count);
    countInput.dataset.countryCount = "";
    countInput.setAttribute(
      "aria-label",
      `Companies contacted in ${country.name}`,
    );
    const increase = makeButton(
      "+",
      `Increase companies contacted in ${country.name}`,
      "data-country-increase",
      "button button-secondary country-step-button",
    );
    const remove = makeButton(
      "Remove",
      `Remove ${country.name} from country breakdown`,
      "data-country-remove",
      "button button-secondary country-remove-button",
    );

    controls.append(decrease, hiddenCode, countInput, increase, remove);
    row.append(name, controls);
    return row;
  };

  const addCountry = () => {
    const country = countries.get(search.value.trim().toLocaleLowerCase());
    if (!country) {
      showMessage("Select a country from the available list.");
      search.focus();
      return;
    }
    if (!isWholeNumber(addCount.value)) {
      showMessage("Enter a non-negative whole number for companies count.");
      addCount.focus();
      return;
    }

    const existing = findRow(country.code);
    if (existing) {
      showMessage("This country is already added");
      const existingCount = existing.querySelector("[data-country-count]");
      existing.classList.add("country-row-highlight");
      existingCount.focus();
      window.setTimeout(
        () => existing.classList.remove("country-row-highlight"),
        900,
      );
      return;
    }

    rows.append(createRow(country, Number.parseInt(addCount.value, 10)));
    setOptionDisabled(country.code, true);
    search.value = "";
    addCount.value = "0";
    showMessage("");
    updateSummary();
    search.focus();
  };

  addButton.addEventListener("click", addCountry);
  for (const input of [search, addCount]) {
    input.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        addCountry();
      }
    });
  }

  rows.addEventListener("click", (event) => {
    const button = event.target.closest("button");
    const row = event.target.closest("[data-country-row]");
    if (!button || !row) {
      return;
    }
    const input = row.querySelector("[data-country-count]");
    const current = isWholeNumber(input.value)
      ? Number.parseInt(input.value, 10)
      : 0;

    if (button.hasAttribute("data-country-increase")) {
      input.value = String(current + 1);
    } else if (button.hasAttribute("data-country-decrease")) {
      input.value = String(Math.max(0, current - 1));
    } else if (button.hasAttribute("data-country-remove")) {
      setOptionDisabled(row.dataset.countryCode, false);
      row.remove();
      showMessage("");
    }
    updateSummary();
  });

  rows.addEventListener("input", updateSummary);
  for (const row of rows.querySelectorAll("[data-country-row]")) {
    setOptionDisabled(row.dataset.countryCode, true);
  }
  updateSummary();
})();
