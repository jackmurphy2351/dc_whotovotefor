// Highlight selected radio options visually
document.addEventListener("DOMContentLoaded", () => {
  const highlightSelected = (container) => {
    const radios = container.querySelectorAll("input[type=radio]");
    radios.forEach((radio) => {
      const label = radio.closest("label");
      if (!label) return;

      const update = () => {
        container.querySelectorAll("label").forEach((l) => l.classList.remove("selected"));
        if (radio.checked) label.classList.add("selected");
      };

      radio.addEventListener("change", () => {
        container.querySelectorAll("input[type=radio]").forEach((r) => {
          const l = r.closest("label");
          if (l) l.classList.remove("selected");
        });
        label.classList.add("selected");
      });

      if (radio.checked) label.classList.add("selected");
    });
  };

  document.querySelectorAll(".stance-fieldset, .importance-fieldset").forEach(highlightSelected);
});
