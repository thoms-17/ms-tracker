import { useState, type FormEvent } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "../api";

/** Modale de connexion (avec « mot de passe oublié »), ouverte depuis la vitrine publique. */
export default function Login({ onClose }: { onClose: () => void }) {
  const [mode, setMode] = useState<"login" | "forgot">("login");
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="login-card" onClick={(e) => e.stopPropagation()}>
        <button type="button" className="modal-close" onClick={onClose} aria-label="Fermer">×</button>
        {mode === "login"
          ? <LoginForm onForgot={() => setMode("forgot")} />
          : <ForgotForm onBack={() => setMode("login")} />}
      </div>
    </div>
  );
}

function LoginForm({ onForgot }: { onForgot: () => void }) {
  const qc = useQueryClient();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");

  const login = useMutation({
    mutationFn: () => api.login(username.trim(), password),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["me"] }),
  });

  const errorMsg = (() => {
    const e = login.error;
    if (!e) return null;
    if (e instanceof ApiError) {
      if (e.status === 401) return "Identifiant ou mot de passe incorrect.";
      if (e.status === 429) return "Trop de tentatives. Réessaie dans quelques minutes.";
    }
    return "Connexion impossible. Réessaie.";
  })();

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (username.trim() && password) login.mutate();
  };

  return (
    <form onSubmit={onSubmit}>
      <h1 className="login-title">Connexion</h1>
      <p className="login-sub">Accède à ton suivi.</p>

      <label className="login-field">
        <span>Identifiant</span>
        <input
          autoFocus autoCapitalize="none" autoCorrect="off" autoComplete="username"
          value={username} onChange={(e) => setUsername(e.target.value)}
        />
      </label>
      <label className="login-field">
        <span>Mot de passe</span>
        <input
          type="password" autoComplete="current-password"
          value={password} onChange={(e) => setPassword(e.target.value)}
        />
      </label>

      {errorMsg && <p className="login-error">{errorMsg}</p>}

      <button
        type="submit" className="btn primary login-submit"
        disabled={login.isPending || !username.trim() || !password}
      >
        {login.isPending ? "Connexion…" : "Se connecter"}
      </button>
      <button type="button" className="link-btn" onClick={onForgot}>Mot de passe oublié ?</button>
    </form>
  );
}

function ForgotForm({ onBack }: { onBack: () => void }) {
  const [email, setEmail] = useState("");
  const forgot = useMutation({ mutationFn: () => api.forgotPassword(email.trim()) });

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (email.trim()) forgot.mutate();
  };

  if (forgot.isSuccess) {
    return (
      <>
        <h1 className="login-title">Vérifie ta boîte mail</h1>
        <p className="login-sub">{forgot.data.message}</p>
        <button type="button" className="btn login-submit" onClick={onBack}>Retour à la connexion</button>
      </>
    );
  }

  return (
    <form onSubmit={onSubmit}>
      <h1 className="login-title">Mot de passe oublié</h1>
      <p className="login-sub">Entre ton adresse email : on t'enverra un lien de réinitialisation.</p>
      <label className="login-field">
        <span>Email</span>
        <input
          autoFocus type="email" autoCapitalize="none" autoComplete="email"
          value={email} onChange={(e) => setEmail(e.target.value)}
        />
      </label>
      {forgot.error && <p className="login-error">Envoi impossible. Réessaie.</p>}
      <button
        type="submit" className="btn primary login-submit"
        disabled={forgot.isPending || !email.trim()}
      >
        {forgot.isPending ? "Envoi…" : "Envoyer le lien"}
      </button>
      <button type="button" className="link-btn" onClick={onBack}>← Retour à la connexion</button>
    </form>
  );
}
