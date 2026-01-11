/* Authentication page JavaScript */

const loginForm = document.getElementById("loginForm");
const registerForm = document.getElementById("registerForm");

// Login handler (only runs if loginForm exists)
if (loginForm) {
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
}

// Register handler (only runs if registerForm exists)
if (registerForm) {
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

    // Password confirmation validation
    if (password !== confirmPassword) {
      errorEl.textContent = "Passwords do not match";
      errorEl.classList.remove("hidden");
      return;
    }

    const submitBtn = registerForm.querySelector('button[type="submit"]');
    submitBtn.disabled = true;
    submitBtn.textContent = "Registering...";

    try {
      // Get reCAPTCHA v3 token if enabled
      let captchaToken = null;
      if (window.RECAPTCHA_SITE_KEY && window.grecaptcha) {
        try {
          captchaToken = await grecaptcha.execute(window.RECAPTCHA_SITE_KEY, { action: "register" });
        } catch (captchaErr) {
          errorEl.textContent = "CAPTCHA error. Please refresh and try again.";
          errorEl.classList.remove("hidden");
          submitBtn.disabled = false;
          submitBtn.textContent = "Register";
          return;
        }
      }

      const payload = { email, password, display_name: displayName };
      if (captchaToken) {
        payload.captcha_token = captchaToken;
      }

      const res = await fetch("/auth/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
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
}
