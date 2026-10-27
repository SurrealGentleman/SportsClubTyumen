document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.admin-toast').forEach((element) => {
    new window.tabler.bootstrap.Toast(element, {delay: 3000}).show();
  });
});
