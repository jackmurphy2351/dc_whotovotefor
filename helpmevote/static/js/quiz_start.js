document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("select-form");
  if (!form) return;

  const questions = Array.from(form.querySelectorAll("input[data-question]"));
  const categories = Array.from(form.querySelectorAll("[data-category]"));
  const counter = form.querySelector("[data-selected-count]");
  const startBtn = form.querySelector("[data-start-btn]");

  const childrenOf = (category) =>
    Array.from(category.querySelectorAll("input[data-question]"));

  const syncCategory = (category) => {
    const toggle = category.querySelector("input[data-category-toggle]");
    const kids = childrenOf(category);
    const checked = kids.filter((c) => c.checked).length;
    toggle.checked = checked === kids.length;
    toggle.indeterminate = checked > 0 && checked < kids.length;
  };

  const refresh = () => {
    const checked = questions.filter((q) => q.checked).length;
    if (counter) counter.textContent = checked;
    if (startBtn) startBtn.disabled = checked === 0;
    categories.forEach(syncCategory);
  };

  // Category master toggle drives its children.
  categories.forEach((category) => {
    const toggle = category.querySelector("input[data-category-toggle]");
    toggle.addEventListener("change", () => {
      childrenOf(category).forEach((c) => {
        c.checked = toggle.checked;
      });
      refresh();
    });
  });

  questions.forEach((q) => q.addEventListener("change", refresh));

  const setAll = (value) => {
    questions.forEach((q) => {
      q.checked = value;
    });
    refresh();
  };
  const selectAll = form.querySelector("[data-select-all]");
  const deselectAll = form.querySelector("[data-deselect-all]");
  if (selectAll) selectAll.addEventListener("click", () => setAll(true));
  if (deselectAll) deselectAll.addEventListener("click", () => setAll(false));

  refresh();
});
