/* Authentication page JavaScript */

const loginForm = document.getElementById("loginForm");
const registerForm = document.getElementById("registerForm");
const loginTab = document.getElementById("loginTab");
const registerTab = document.getElementById("registerTab");

// Tab switching
loginTab.addEventListener("click", () => {
  loginTab.classList.add("active");
  registerTab.classList.remove("active");
  loginForm.classList.remove("hidden");
  registerForm.classList.add("hidden");
});

registerTab.addEventListener("click", () => {
  registerTab.classList.add("active");
  loginTab.classList.remove("active");
  registerForm.classList.remove("hidden");
  loginForm.classList.add("hidden");
});

// Login handler
loginForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const errorEl = document.getElementById("loginError");
  errorEl.classList.add("hidden");

  const email = document.getElementById("loginEmail").value.trim();
  const password = document.getElementById("loginPassword").value;
  const rememberMe = document.getElementById("rememberMe").checked;

  const submitBtn = loginForm.querySelector('button[type="submit"]');
  submitBtn.disabled = true;
  submitBtn.textContent = "Logging in...";

  try {
    const res = await fetch("/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password, remember_me: rememberMe })
    });

    const data = await res.json();

    if (data.ok) {
      window.location.href = "/auth/lobby";
    } else {
      errorEl.textContent = data.error || "Login failed";
      errorEl.classList.remove("hidden");
    }
  } catch (err) {
    errorEl.textContent = "Network error. Please try again.";
    errorEl.classList.remove("hidden");
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = "Login";
  }
});

// Register handler
registerForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const errorEl = document.getElementById("registerError");
  const successEl = document.getElementById("registerSuccess");
  errorEl.classList.add("hidden");
  successEl.classList.add("hidden");

  const email = document.getElementById("regEmail").value.trim();
  const displayName = document.getElementById("regDisplayName").value.trim();
  const password = document.getElementById("regPassword").value;
  const confirmPassword = document.getElementById("regConfirmPassword").value;

  if (password !== confirmPassword) {
    errorEl.textContent = "Passwords do not match";
    errorEl.classList.remove("hidden");
    return;
  }

  const submitBtn = registerForm.querySelector('button[type="submit"]');
  submitBtn.disabled = true;
  submitBtn.textContent = "Registering...";

  try {
    const res = await fetch("/auth/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password, display_name: displayName })
    });

    const data = await res.json();

    if (data.ok) {
      successEl.textContent = data.message;
      successEl.classList.remove("hidden");
      registerForm.reset();
    } else {
      const errors = data.errors || [data.error || "Registration failed"];
      errorEl.textContent = errors.join(", ");
      errorEl.classList.remove("hidden");
    }
  } catch (err) {
    errorEl.textContent = "Network error. Please try again.";
    errorEl.classList.remove("hidden");
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = "Register";
  }
});

// Check if URL indicates we should show register tab
if (window.location.search.includes("register") || window.location.hash === "#register") {
  registerTab.click();
}
