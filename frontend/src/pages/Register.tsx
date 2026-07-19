import { useState, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import { api, ApiError } from "../api";

/** Inscription via lien d'invitation : /register/:token */
export default function Register() {
  const { token = "" } = useParams();
  const invite = useQuery({
    queryKey: ["invite", token],
    queryFn: () => api.inviteInfo(token),
    retry: false,
  });

  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  const boundEmail = invite.data?.email ?? null;
  const emailValue = boundEmail ?? email;

  const register = useMutation({
    mutationFn: () => api.register(token, username.trim(), emailValue.trim(), password),
  });

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (username.trim() && emailValue.trim() && password) register.mutate();
  };

  // États : chargement / invitation invalide / succès / formulaire
  const shell = (children: React.ReactNode) => (
    <div className="login-wrap"><div className="login-card">{children}</div></div>
  );

  if (invite.isLoading) return shell(<p className="muted">Vérification de l'invitation…</p>);

  if (!invite.data?.valid) {
    return shell(
      <>
        <h1 className="login-title">Invitation invalide</h1>
        <p className="login-sub">Ce lien d'invitation est invalide ou a expiré.</p>
        <Link to="/" className="btn login-submit" style={{ textAlign: "center" }}>Retour à l'accueil</Link>
      </>,
    );
  }

  if (register.isSuccess) {
    return shell(
      <>
        <h1 className="login-title">Vérifie ta boîte mail</h1>
        <p className="login-sub">
          Compte créé. Un email de confirmation vient d'être envoyé à <strong>{emailValue}</strong>.
          Clique sur le lien (valable 24 h) pour activer ton compte.
        </p>
        <Link to="/" className="btn login-submit" style={{ textAlign: "center" }}>Retour à l'accueil</Link>
      </>,
    );
  }

  const errorMsg =
    register.error instanceof ApiError ? register.error.message
      : register.error ? "Inscription impossible. Réessaie." : null;

  return (
    <div className="login-wrap">
      <form className="login-card" onSubmit={onSubmit}>
        <h1 className="login-title">Créer ton compte</h1>
        <p className="login-sub">Tu as été invité à rejoindre MS Tracker.</p>

        <label className="login-field">
          <span>Identifiant</span>
          <input
            autoFocus autoCapitalize="none" autoCorrect="off" autoComplete="username"
            value={username} onChange={(e) => setUsername(e.target.value)}
          />
        </label>
        <label className="login-field">
          <span>Email</span>
          <input
            type="email" autoCapitalize="none" autoComplete="email"
            value={emailValue} disabled={!!boundEmail}
            onChange={(e) => setEmail(e.target.value)}
          />
        </label>
        <label className="login-field">
          <span>Mot de passe (8 caractères minimum)</span>
          <input
            type="password" autoComplete="new-password"
            value={password} onChange={(e) => setPassword(e.target.value)}
          />
        </label>

        {errorMsg && <p className="login-error">{errorMsg}</p>}

        <button
          type="submit" className="btn primary login-submit"
          disabled={register.isPending || !username.trim() || !emailValue.trim() || password.length < 8}
        >
          {register.isPending ? "Création…" : "Créer mon compte"}
        </button>
      </form>
    </div>
  );
}
