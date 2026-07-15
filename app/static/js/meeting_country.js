"use strict";

(() => {
  const search = document.querySelector("[data-meeting-country-search]");
  const countryCode = document.querySelector("[data-meeting-country-code]");
  const datalist = document.querySelector("#meeting_country_options");

  if (!search || !countryCode || !datalist) {
    return;
  }

  const countryCodesByName = new Map();
  for (const option of datalist.options) {
    countryCodesByName.set(
      option.value.trim().toLocaleLowerCase(),
      option.dataset.countryCode,
    );
  }

  const updateCountryCode = () => {
    const enteredName = search.value.trim();
    countryCode.value = countryCodesByName.get(
      enteredName.toLocaleLowerCase(),
    ) || enteredName;
  };

  search.addEventListener("input", updateCountryCode);
  search.form.addEventListener("submit", updateCountryCode);
})();
