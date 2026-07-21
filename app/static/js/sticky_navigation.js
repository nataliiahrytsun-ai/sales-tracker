"use strict";

const navigationStack = document.querySelector("[data-sticky-navigation]");

if (navigationStack && "ResizeObserver" in window) {
  const updateStackHeight = () => {
    const height = Math.ceil(navigationStack.getBoundingClientRect().height);
    document.documentElement.style.setProperty(
      "--app-navigation-stack-height",
      `${height}px`,
    );
  };

  const observer = new ResizeObserver(updateStackHeight);
  observer.observe(navigationStack);
  updateStackHeight();
}
