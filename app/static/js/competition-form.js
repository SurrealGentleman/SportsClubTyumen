(() => {
  const registrationType = document.querySelector('[name="registration_type"]');
  const minimum = document.querySelector('[name="min_team_size"]');
  const maximum = document.querySelector('[name="max_team_size"]');
  if (!registrationType || !minimum || !maximum) return;

  const refresh = () => {
    const isTeam = registrationType.value === "team";
    [minimum, maximum].forEach((field) => {
      field.required = isTeam;
      field.disabled = !isTeam;
      field.min = "1";
      field.step = "1";
      const label = field.closest(".form-group")?.querySelector("label");
      if (label) {
        label.classList.toggle("required-label", isTeam);
        if (isTeam) label.title = "Обязательное поле";
        else label.removeAttribute("title");
      }
    });
    maximum.min = String(Math.max(1, Number(minimum.value) || 1));
  };

  registrationType.addEventListener("change", refresh);
  minimum.addEventListener("input", refresh);
  refresh();
})();
