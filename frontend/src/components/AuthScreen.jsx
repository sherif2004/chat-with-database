import { useState } from "react";
import { logIn, signUp } from "../api";

const MODES = {
  login: {
    title: "Welcome back",
    subtitle: "Sign in to pick up your conversations and databases.",
    submit: "Sign in",
    busy: "Signing in…",
    switchPrompt: "New here?",
    switchLabel: "Create an account",
    password: "current-password",
  },
  signup: {
    title: "Create your account",
    subtitle: "Your chats and database connections stay private to you.",
    submit: "Create account",
    busy: "Creating account…",
    switchPrompt: "Already have an account?",
    switchLabel: "Sign in",
    password: "new-password",
  },
};

export default function AuthScreen({ onAuthenticated }) {
  const [mode, setMode] = useState("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const copy = MODES[mode];

  function switchMode() {
    setMode((current) => (current === "login" ? "signup" : "login"));
    setError(null);
  }

  async function handleSubmit(event) {
    event.preventDefault();
    if (busy) return;

    setBusy(true);
    setError(null);

    try {
      const action = mode === "login" ? logIn : signUp;
      onAuthenticated(await action(email.trim(), password));
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  }

  return (
    <main className="auth">
      <form className="auth-card" onSubmit={handleSubmit}>
        <h1 className="auth-title">{copy.title}</h1>
        <p className="auth-subtitle">{copy.subtitle}</p>

        <label className="auth-field">
          <span>Email</span>
          <input
            type="email"
            autoComplete="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            required
            autoFocus
          />
        </label>

        <label className="auth-field">
          <span>Password</span>
          <input
            type="password"
            autoComplete={copy.password}
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            minLength={mode === "signup" ? 8 : undefined}
            required
          />
          {mode === "signup" && (
            <small className="auth-hint">At least 8 characters.</small>
          )}
        </label>

        {error && (
          <div className="auth-error" role="alert">
            {error}
          </div>
        )}

        <button type="submit" className="auth-submit" disabled={busy}>
          {busy ? copy.busy : copy.submit}
        </button>

        <p className="auth-switch">
          {copy.switchPrompt}{" "}
          <button type="button" className="auth-switch-button" onClick={switchMode}>
            {copy.switchLabel}
          </button>
        </p>
      </form>
    </main>
  );
}
