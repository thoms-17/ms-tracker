import { useState, type FormEvent, type ReactNode } from "react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import { api, ApiError } from "../api";

/** Réinitialisation du mot de passe via lien reçu par email : /reset/:token */
export default function ResetPassword() {
  const { token = "" } = useParams();
  const info = useQuery({
    queryKey: ["reset", token],
    queryFn: () => api.resetInfo(token),
    retry: false,
  });

  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");

  const reset = useMutation({ mutationFn: () => api.resetPassword(token, password) });

  const shell = (children: ReactNode) => (
    <div className="login-wrap"><div className="login-card">{children}</div></div>
  );

  if (info.isLoading) return shell(<p className="muted">Vérification du lien…</p>);

  if (!info.data?.valid) {
    return shell(
      <>
        <h1 className="login-title">Lien invalide</h1>
        <p className="login-sub">Ce lien de réinitialisation est invalide ou a expiré (validité : 1 h).</p>
        <Link to="/" className="btn login-submit" style={{ textAlign: "center" }}>Retour à l'accueil</Link>
      </>,
    );
  }

  if (reset.isSuccess) {
    return shell(
      <>
        <h1 className="login-title">✅ Mot de passe mis à jour</h1>
        <p className="login-sub">Tu peux maintenant te connecter avec ton nouveau mot de passe.</p>
        <Link to="/" className="btn primary login-submit" style={{ textAlign: "center" }}>Se connecter</Link>
      </>,
    );
  }

  const mismatch = confirm.length > 0 && password !== confirm;
  const errorMsg = reset.error instanceof ApiError ? reset.error.message
    : reset.error ? "Réinitialisation impossible." : null;

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (password.length >= 8 && password === confirm) reset.mutate();
  };

  return (
    <div className="login-wrap">
      <form className="login-card" onSubmit={onSubmit}>
        <h1 className="login-title">Nouveau mot de passe</h1>
        <p className="login-sub">Choisis un nouveau mot de passe (8 caractères minimum).</p>
        <label className="login-field">
          <span>Nouveau mot de passe</span>
          <input
            autoFocus type="password" autoComplete="new-password"
            value={password} onChange={(e) => setPassword(e.target.value)}
          />
        </label>
        <label className="login-field">
          <span>Confirme le mot de passe</span>
          <input
            type="password" autoComplete="new-password"
            value={confirm} onChange={(e) => setConfirm(e.target.value)}
          />
        </label>
        {mismatch && <p className="login-error">Les mots de passe ne correspondent pas.</p>}
        {errorMsg && <p className="login-error">{errorMsg}</p>}
        <button
          type="submit" className="btn primary login-submit"
          disabled={reset.isPending || password.length < 8 || password !== confirm}
        >
          {reset.isPending ? "Mise à jour…" : "Réinitialiser"}
        </button>
      </form>
    </div>
  );
}
