"use strict";

document.querySelectorAll("form[data-confirm-message]").forEach((form) => {
  form.addEventListener("submit", (event) => {
    if (!window.confirm(form.dataset.confirmMessage)) {
      event.preventDefault();
    }
  });
});
