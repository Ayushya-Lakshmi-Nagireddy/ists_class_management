var savedTheme = localStorage.getItem("theme");
if (savedTheme === "dark") {
  document.documentElement.setAttribute("data-theme", "dark");
} else {
  document.documentElement.setAttribute("data-theme", "light");
}

document.addEventListener("DOMContentLoaded", function () {

  function updateThemeButtons() {
    var theme = document.documentElement.getAttribute("data-theme");
    var buttons = document.querySelectorAll(".theme-button");
    for (var i = 0; i < buttons.length; i++) {
      if (theme === "dark") {
        buttons[i].textContent = "\u2600 Light";
      } else {
        buttons[i].textContent = "\uD83C\uDF19 Dark";
      }
    }
  }

  var themeButtons = document.querySelectorAll(".theme-button");
  for (var i = 0; i < themeButtons.length; i++) {
    themeButtons[i].addEventListener("click", function () {
      var current = document.documentElement.getAttribute("data-theme");
      var newTheme = (current === "dark") ? "light" : "dark";
      document.documentElement.setAttribute("data-theme", newTheme);
      localStorage.setItem("theme", newTheme);
      updateThemeButtons();
    });
  }
  updateThemeButtons();

  var showButtons = document.querySelectorAll(".show-button");
  for (var j = 0; j < showButtons.length; j++) {
    showButtons[j].addEventListener("click", function () {
      var box = this.parentElement.querySelector("input");
      if (box.type === "password") {
        box.type = "text";
        this.textContent = "Hide";
      } else {
        box.type = "password";
        this.textContent = "Show";
      }
    });
  }

  var registerForm = document.getElementById("register-form");
  if (registerForm) {
    registerForm.addEventListener("submit", function (event) {
      var password = document.getElementById("password").value;
      var confirm = document.getElementById("confirm_password").value;
      if (password.length < 6) {
        alert("Password must be at least 6 characters.");
        event.preventDefault();
      } else if (password !== confirm) {
        alert("Passwords do not match.");
        event.preventDefault();
      }
    });
  }

  setTimeout(function () {
    var messages = document.querySelectorAll(".message");
    for (var k = 0; k < messages.length; k++) {
      messages[k].style.display = "none";
    }
  }, 5000);
});
