(() => {
  const members = document.querySelector("#team-members");
  const template = document.querySelector("#team-member-template");
  const addButton = document.querySelector("#add-team-member");
  const teamSize = document.querySelector("#team-size");

  if (!members || !template || !addButton || !teamSize) return;

  const minTeamSize = Number(members.dataset.minTeamSize);
  const maxTeamSize = Number(members.dataset.maxTeamSize);

  const refresh = () => {
    const rows = [...members.querySelectorAll(".team-member-card")];
    const total = rows.length + 1;
    teamSize.textContent = String(total);
    addButton.disabled = total >= maxTeamSize;

    rows.forEach((row, index) => {
      const number = row.querySelector("[data-member-number]");
      const removeButton = row.querySelector("[data-remove-member]");
      if (number) number.textContent = String(index + 2);
      if (removeButton) removeButton.disabled = total <= minTeamSize;
    });
  };

  addButton.addEventListener("click", () => {
    const total = members.querySelectorAll(".team-member-card").length + 1;
    if (total >= maxTeamSize) return;
    members.append(template.content.cloneNode(true));
    refresh();
  });

  members.addEventListener("click", (event) => {
    const removeButton = event.target.closest("[data-remove-member]");
    if (!removeButton || removeButton.disabled) return;
    removeButton.closest(".team-member-card")?.remove();
    refresh();
  });

  refresh();
})();
