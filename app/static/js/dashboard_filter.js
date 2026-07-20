"use strict";

document.querySelectorAll(".dashboard-section-navigation").forEach(
  (navigation) => {
    const links = Array.from(
      navigation.querySelectorAll('a[href^="#"]'),
    );
    const sections = links.map((link) => (
      document.querySelector(link.getAttribute("href"))
    ));
    if (sections.some((section) => !section)) return;

    const shell = navigation.closest(".dashboard-section-navigation-shell");
    let activeIndex = -1;
    let requestedIndex = null;
    let updateFrame = null;
    let scrollFallback = null;

    const stickyOffset = () => (
      (shell || navigation).getBoundingClientRect().height + 8
    );
    const activationOffset = () => Math.max(
      stickyOffset(),
      Number.parseFloat(window.getComputedStyle(sections[0]).scrollMarginTop) ||
        0,
    ) + 1;
    const sectionIndexFromHash = () => links.findIndex(
      (link) => link.getAttribute("href") === window.location.hash,
    );
    const replaceHash = (index) => {
      const hash = links[index].getAttribute("href");
      if (window.location.hash === hash) return;
      window.history.replaceState(
        null,
        "",
        window.location.pathname + window.location.search + hash,
      );
    };
    const setActive = (index, updateHash = false) => {
      links.forEach((link, linkIndex) => {
        if (linkIndex === index) {
          link.setAttribute("aria-current", "location");
        } else {
          link.removeAttribute("aria-current");
        }
      });
      if (activeIndex !== index) {
        activeIndex = index;
        links[index].scrollIntoView({block: "nearest", inline: "nearest"});
      }
      if (updateHash) replaceHash(index);
    };
    const isAtPageBottom = () => (
      window.innerHeight + window.scrollY >=
      document.documentElement.scrollHeight - 2
    );
    const visibleSectionIndex = () => {
      if (window.scrollY <= 2) return 0;
      if (isAtPageBottom()) return sections.length - 1;
      const offset = activationOffset();
      let index = 0;
      sections.forEach((section, sectionIndex) => {
        if (section.getBoundingClientRect().top <= offset) {
          index = sectionIndex;
        }
      });
      return index;
    };
    const updateActiveSection = () => {
      updateFrame = null;
      if (requestedIndex !== null) {
        setActive(requestedIndex);
        return;
      }
      setActive(visibleSectionIndex(), true);
    };
    const scheduleUpdate = () => {
      if (updateFrame !== null) return;
      updateFrame = window.requestAnimationFrame(updateActiveSection);
    };
    const scrollToSection = (index, smooth, preserveHash = false) => {
      requestedIndex = smooth || preserveHash ? index : null;
      setActive(index);
      sections[index].scrollIntoView({
        behavior: smooth ? "smooth" : "auto",
        block: "start",
      });
      if (smooth) {
        window.clearTimeout(scrollFallback);
        scrollFallback = window.setTimeout(() => {
          requestedIndex = null;
          scheduleUpdate();
        }, 900);
      }
    };

    links.forEach((link, index) => {
      link.addEventListener("click", (event) => {
        event.preventDefault();
        window.history.pushState(
          null,
          "",
          window.location.pathname +
            window.location.search +
            link.getAttribute("href"),
        );
        scrollToSection(index, true);
      });
    });

    const observer = new IntersectionObserver(scheduleUpdate, {
      rootMargin: `-${activationOffset()}px 0px -65% 0px`,
      threshold: [0, 1],
    });
    sections.forEach((section) => observer.observe(section));
    window.addEventListener("scroll", scheduleUpdate, {passive: true});
    window.addEventListener("resize", scheduleUpdate);
    ["wheel", "touchstart", "pointerdown", "keydown"].forEach((eventName) => {
      window.addEventListener(eventName, () => {
        if (requestedIndex === null) return;
        window.clearTimeout(scrollFallback);
        requestedIndex = null;
        scheduleUpdate();
      }, {passive: true});
    });
    window.addEventListener("hashchange", () => {
      const index = sectionIndexFromHash();
      if (index >= 0) scrollToSection(index, false, true);
    });

    const initialIndex = sectionIndexFromHash();
    if (initialIndex >= 0) {
      scrollToSection(initialIndex, false, true);
    } else {
      setActive(0);
    }
  },
);

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
  editDatesButton.addEventListener("click", (event) => {
    event.preventDefault();
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

document.querySelectorAll("[data-comment-group-select]").forEach((select) => {
  select.addEventListener("change", () => {
    window.location.assign(select.value);
  });
});

document.querySelectorAll("[data-expand-toggle]").forEach((toggle) => {
  const list = document.getElementById(toggle.getAttribute("aria-controls"));
  if (!list) return;
  const rows = Array.from(list.querySelectorAll("[data-expandable-row]"));
  const label = toggle.dataset.label;

  toggle.addEventListener("click", () => {
    const expanded = toggle.getAttribute("aria-expanded") === "true";
    rows.forEach((row) => {
      row.hidden = expanded;
    });
    toggle.setAttribute("aria-expanded", String(!expanded));
    toggle.textContent = expanded ? "View all" : "Show less";
    toggle.setAttribute(
      "aria-label",
      `${expanded ? "View all" : "Show less"} ${label}`,
    );
  });
});
