"use strict";

const calendarMonths = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

const parseCalendarDate = (value) => {
  const [year, month, day] = value.split("-").map(Number);
  return new Date(Date.UTC(year, month - 1, day));
};

const calendarDateValue = (value) => [
  value.getUTCFullYear(),
  String(value.getUTCMonth() + 1).padStart(2, "0"),
  String(value.getUTCDate()).padStart(2, "0"),
].join("-");

const isoWeekValue = (selectedDate) => {
  const monday = new Date(selectedDate);
  const mondayOffset = (monday.getUTCDay() + 6) % 7;
  monday.setUTCDate(monday.getUTCDate() - mondayOffset);

  const thursday = new Date(monday);
  thursday.setUTCDate(thursday.getUTCDate() + 3);
  const isoYear = thursday.getUTCFullYear();

  const januaryFourth = new Date(Date.UTC(isoYear, 0, 4));
  const firstMondayOffset = (januaryFourth.getUTCDay() + 6) % 7;
  januaryFourth.setUTCDate(januaryFourth.getUTCDate() - firstMondayOffset);
  const weekNumber = 1 + Math.round(
    (monday.getTime() - januaryFourth.getTime()) / 604800000,
  );
  return `${isoYear}-W${String(weekNumber).padStart(2, "0")}`;
};

document.querySelectorAll("[data-week-picker]").forEach((picker) => {
  const form = picker.closest("[data-target-week-form]");
  const trigger = picker.querySelector("[data-week-trigger]");
  const calendar = picker.querySelector("[data-week-calendar]");
  const monthLabel = picker.querySelector("[data-calendar-month]");
  const grid = picker.querySelector("[data-calendar-grid]");
  const previousMonth = picker.querySelector("[data-calendar-previous]");
  const nextMonth = picker.querySelector("[data-calendar-next]");
  const weekValue = form.querySelector("[data-target-week-value]");
  const selectedDate = parseCalendarDate(picker.dataset.selectedDate);
  let viewedMonth = new Date(Date.UTC(
    selectedDate.getUTCFullYear(),
    selectedDate.getUTCMonth(),
    1,
  ));

  const renderCalendar = () => {
    const year = viewedMonth.getUTCFullYear();
    const month = viewedMonth.getUTCMonth();
    monthLabel.textContent = `${calendarMonths[month]} ${year}`;
    grid.replaceChildren();

    const firstVisibleDate = new Date(viewedMonth);
    firstVisibleDate.setUTCDate(
      firstVisibleDate.getUTCDate() - ((firstVisibleDate.getUTCDay() + 6) % 7),
    );
    for (let offset = 0; offset < 42; offset += 1) {
      const date = new Date(firstVisibleDate);
      date.setUTCDate(firstVisibleDate.getUTCDate() + offset);
      const dateValue = calendarDateValue(date);
      const button = document.createElement("button");
      button.type = "button";
      button.className = "target-week-calendar-day";
      button.dataset.calendarDate = dateValue;
      button.textContent = String(date.getUTCDate());
      button.setAttribute(
        "aria-label",
        `${date.getUTCDate()} ${calendarMonths[date.getUTCMonth()]} ${date.getUTCFullYear()}`,
      );
      button.setAttribute(
        "aria-selected",
        String(dateValue === calendarDateValue(selectedDate)),
      );
      if (date.getUTCMonth() !== month) {
        button.classList.add("is-outside-month");
      }
      grid.append(button);
    }
  };

  const setOpen = (open, focusSelected = false) => {
    calendar.hidden = !open;
    trigger.setAttribute("aria-expanded", String(open));
    if (open) {
      renderCalendar();
      if (focusSelected) {
        const selected = grid.querySelector(
          `[data-calendar-date="${calendarDateValue(selectedDate)}"]`,
        );
        (selected || grid.querySelector("[data-calendar-date]")).focus();
      }
    }
  };

  const openSelectedWeek = (date) => {
    weekValue.value = isoWeekValue(date);
    const url = new URL(form.dataset.weekUrl, window.location.origin);
    url.searchParams.set("week", weekValue.value);
    window.location.assign(url.toString());
  };

  trigger.addEventListener("click", () => {
    setOpen(calendar.hidden, calendar.hidden);
  });
  previousMonth.addEventListener("click", () => {
    viewedMonth.setUTCMonth(viewedMonth.getUTCMonth() - 1);
    renderCalendar();
  });
  nextMonth.addEventListener("click", () => {
    viewedMonth.setUTCMonth(viewedMonth.getUTCMonth() + 1);
    renderCalendar();
  });
  grid.addEventListener("click", (event) => {
    const day = event.target.closest("[data-calendar-date]");
    if (day) openSelectedWeek(parseCalendarDate(day.dataset.calendarDate));
  });
  grid.addEventListener("keydown", (event) => {
    const day = event.target.closest("[data-calendar-date]");
    const offsets = {ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7};
    if (!day || !(event.key in offsets)) return;
    event.preventDefault();
    const nextDate = parseCalendarDate(day.dataset.calendarDate);
    nextDate.setUTCDate(nextDate.getUTCDate() + offsets[event.key]);
    viewedMonth = new Date(Date.UTC(
      nextDate.getUTCFullYear(),
      nextDate.getUTCMonth(),
      1,
    ));
    renderCalendar();
    grid.querySelector(
      `[data-calendar-date="${calendarDateValue(nextDate)}"]`,
    ).focus();
  });
  document.addEventListener("click", (event) => {
    if (!picker.contains(event.target)) setOpen(false);
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !calendar.hidden) {
      setOpen(false);
      trigger.focus();
    }
  });
});
