"use strict";

const removeCommentsFragmentAfterNativeScroll = () => {
  if (window.location.hash === "#comments-overview") {
    window.requestAnimationFrame(() => {
      if (window.location.hash === "#comments-overview") {
        window.history.replaceState(
          null,
          "",
          window.location.pathname + window.location.search,
        );
      }
    });
  }
};

if (document.readyState === "loading") {
  document.addEventListener(
    "DOMContentLoaded",
    removeCommentsFragmentAfterNativeScroll,
    {once: true},
  );
} else {
  removeCommentsFragmentAfterNativeScroll();
}

document.querySelectorAll("[data-dashboard-filter]").forEach((form) => {
  const period = form.querySelector("[data-period-select]");
  const customDates = form.querySelector("[data-custom-dates]");
  const fromInput = form.querySelector("[data-from]");
  const toInput = form.querySelector("[data-to]");
  const applyButton = form.querySelector("[data-apply]");
  const dateValidation = form.querySelector("[data-date-validation]");
  const customAppliedSummary = form.querySelector(
    "[data-custom-applied-summary]",
  );
  const editDatesButton = form.querySelector("[data-edit-dates]");
  const usersDropdown = form.querySelector("[data-users-dropdown]");
  const usersTrigger = form.querySelector("[data-users-trigger]");
  const usersPanel = form.querySelector("[data-users-panel]");
  const usersSummary = form.querySelector("[data-users-summary]");
  const allUsers = form.querySelector("[data-all-users]");
  const resetFilters = form.querySelector(".dashboard-reset-filters");
  const userCheckboxes = Array.from(
    form.querySelectorAll("[data-user-checkbox]"),
  );
  const userScope = form.querySelector("[data-user-scope]");
  const usersOpenStorageKey = "dashboard-users-dropdown-open";
  let customDatesEditing = form.dataset.customApplied !== "true";

  const isCustom = () => period.value === "custom";
  const checkedUsers = () => userCheckboxes.filter((checkbox) => checkbox.checked);
  const currentUserScope = () => (
    userCheckboxes.length > 0 && userCheckboxes.length === checkedUsers().length
      ? "all"
      : "selected"
  );
  const setUsersOpen = (open, focusFirst = false) => {
    usersPanel.hidden = !open;
    usersTrigger.setAttribute("aria-expanded", String(open));
    usersTrigger.setAttribute("aria-controls", usersPanel.id);
    if (open && focusFirst) {
      allUsers.focus();
    }
  };
  const updateUsersSummary = (allChecked, selected) => {
    if (allChecked) {
      usersSummary.textContent = "All users";
    } else if (selected.length === 1) {
      usersSummary.textContent = selected[0].labels[0].textContent.trim();
    } else if (selected.length === 0) {
      usersSummary.textContent = "Select users";
    } else {
      usersSummary.textContent = `${selected.length} users selected`;
    }
  };
  const dateValidationMessage = () => {
    if (!isCustom() || (!fromInput.value && !toInput.value)) return "";
    if (!fromInput.value || !toInput.value) {
      return "Select both From and To dates.";
    }
    if (fromInput.value > toInput.value) {
      return "From cannot be later than To.";
    }
    if (toInput.value > form.dataset.today) {
      return "To cannot be in the future.";
    }
    return "";
  };
  const datesAreValid = () => Boolean(
    fromInput.value &&
    toInput.value &&
    !dateValidationMessage()
  );
  const rememberOpenUsersDropdown = () => {
    try {
      window.sessionStorage.setItem(usersOpenStorageKey, "true");
    } catch (_error) {
      // Filtering still works when session storage is unavailable.
    }
  };
  const currentUrlAndParams = () => {
    const url = new URL(form.action, window.location.origin);
    const params = new URLSearchParams(window.location.search);
    return {url, params};
  };
  const navigateWithParams = (url, params) => {
    url.search = params.toString();
    url.hash = "";
    window.location.assign(url.toString());
  };
  const replaceUserParams = (params) => {
    params.delete("user_scope");
    params.delete("user_id");
    const scope = currentUserScope();
    params.set("user_scope", scope);
    if (scope === "selected") {
      checkedUsers().forEach((checkbox) => {
        params.append("user_id", checkbox.value);
      });
    }
  };

  const update = () => {
    const selected = checkedUsers();
    const selectedCount = selected.length;
    const allChecked = userCheckboxes.length > 0 && (
      userCheckboxes.length === selectedCount
    );
    const dateError = dateValidationMessage();
    const showCustomDates = isCustom() && customDatesEditing;
    customDates.hidden = !showCustomDates;
    customAppliedSummary.hidden = !(
      isCustom() &&
      !customDatesEditing &&
      form.dataset.customApplied === "true"
    );
    fromInput.disabled = !showCustomDates;
    toInput.disabled = !showCustomDates;
    allUsers.checked = allChecked;
    allUsers.indeterminate = selectedCount > 0 && !allChecked;
    userScope.value = allChecked ? "all" : "selected";
    updateUsersSummary(allChecked, selected);
    dateValidation.textContent = dateError;
    dateValidation.hidden = !showCustomDates || !dateError;
    applyButton.disabled = !datesAreValid();
  };
  const applyUsersFilter = () => {
    update();
    const {url, params} = currentUrlAndParams();
    replaceUserParams(params);
    rememberOpenUsersDropdown();
    navigateWithParams(url, params);
  };
  const applyPresetPeriod = () => {
    const {url, params} = currentUrlAndParams();
    params.set("period", period.value);
    navigateWithParams(url, params);
  };
  const applyCustomRange = () => {
    const {url, params} = currentUrlAndParams();
    params.set("period", "custom");
    params.set("from", fromInput.value);
    params.set("to", toInput.value);
    replaceUserParams(params);
    navigateWithParams(url, params);
  };

  allUsers.addEventListener("change", () => {
    userCheckboxes.forEach((checkbox) => {
      checkbox.checked = allUsers.checked;
    });
    applyUsersFilter();
  });
  userCheckboxes.forEach((checkbox) => {
    checkbox.addEventListener("change", () => {
      applyUsersFilter();
    });
  });
  usersTrigger.addEventListener("click", () => {
    setUsersOpen(usersPanel.hidden);
  });
  usersTrigger.addEventListener("keydown", (event) => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setUsersOpen(true, true);
    }
  });
  document.addEventListener("click", (event) => {
    if (!usersDropdown.contains(event.target)) {
      setUsersOpen(false);
    }
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !usersPanel.hidden) {
      setUsersOpen(false);
      usersTrigger.focus();
    }
  });
  period.addEventListener("change", () => {
    if (isCustom()) customDatesEditing = true;
    update();
    if (!isCustom()) applyPresetPeriod();
  });
  editDatesButton.addEventListener("click", () => {
    customDatesEditing = true;
    update();
    fromInput.focus();
  });
  fromInput.addEventListener("input", update);
  toInput.addEventListener("input", update);
  resetFilters.addEventListener("click", () => {
    const resetUrl = new URL(resetFilters.href, window.location.origin);
    resetUrl.hash = "";
    resetFilters.href = resetUrl.toString();
  });
  form.addEventListener("submit", (event) => {
    update();
    if (isCustom() && !datesAreValid()) {
      event.preventDefault();
      return;
    }
    const actionUrl = new URL(form.action, window.location.origin);
    actionUrl.hash = "";
    form.action = actionUrl.toString();
    if (isCustom()) {
      event.preventDefault();
      applyCustomRange();
    }
  });
  update();
  try {
    if (window.sessionStorage.getItem(usersOpenStorageKey) === "true") {
      window.sessionStorage.removeItem(usersOpenStorageKey);
      setUsersOpen(true);
    }
  } catch (_error) {
    // The dropdown simply starts closed when session storage is unavailable.
  }
});

document.querySelectorAll("[data-grouped-chart]").forEach((chart) => {
  chart.style.setProperty("--chart-columns", chart.dataset.columns);
  chart.style.setProperty("--chart-label-stride", chart.dataset.labelStride);
  chart.querySelectorAll("[data-bar-height]").forEach((barGroup) => {
    barGroup.style.setProperty(
      "--bar-height",
      `${barGroup.dataset.barHeight}%`,
    );
  });
});

document.querySelectorAll("[data-expand-toggle]").forEach((toggle) => {
  const list = document.getElementById(toggle.getAttribute("aria-controls"));
  if (!list) return;
  const rows = Array.from(list.querySelectorAll("[data-expandable-row]"));
  const label = toggle.dataset.label;
  const grid = toggle.closest(".dashboard-analysis-grid");

  const isDesktop = () => window.matchMedia("(min-width: 64rem)").matches;
  const cards = () => (
    grid ? Array.from(grid.querySelectorAll(".dashboard-analysis-card")) : []
  );
  const clearCardBaseline = () => {
    cards().forEach((card) => {
      card.style.removeProperty("min-height");
    });
    if (grid) delete grid.dataset.collapsedCardHeight;
  };
  const captureCardBaseline = () => {
    if (!grid || !isDesktop() || grid.dataset.collapsedCardHeight) return;
    const baseline = Math.max(
      ...cards().map((card) => card.getBoundingClientRect().height),
    );
    grid.dataset.collapsedCardHeight = String(baseline);
    cards().forEach((card) => {
      card.style.minHeight = `${baseline}px`;
    });
  };

  const syncGridExpansion = () => {
    if (!grid) return;
    const hasExpandedCard = Array.from(
      grid.querySelectorAll("[data-expand-toggle]"),
    ).some((control) => control.getAttribute("aria-expanded") === "true");
    if (!isDesktop()) {
      clearCardBaseline();
      grid.classList.remove("has-expanded-card");
      return;
    }
    grid.classList.toggle("has-expanded-card", hasExpandedCard);
    if (!hasExpandedCard) clearCardBaseline();
  };

  toggle.addEventListener("click", () => {
    const expanded = toggle.getAttribute("aria-expanded") === "true";
    if (!expanded) captureCardBaseline();
    rows.forEach((row) => {
      row.hidden = expanded;
    });
    toggle.setAttribute("aria-expanded", String(!expanded));
    toggle.textContent = expanded ? "View all" : "Show less";
    toggle.setAttribute(
      "aria-label",
      `${expanded ? "View all" : "Show less"} ${label}`,
    );
    syncGridExpansion();
  });
});
