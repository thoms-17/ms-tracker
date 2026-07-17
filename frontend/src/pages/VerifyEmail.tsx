import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api";

/** Vérification d'email via lien reçu par mail : /verify/:token */
export default function VerifyEmail() {
  const { token = "" } = useParams();
  // useQuery (et non useMutation) : React Query dédoublonne l'appel, ce qui évite
  // que le double-montage de StrictMode ne consomme le token deux fois.
  const verify = useQuery({
    queryKey: ["verify", token],
    queryFn: () => api.verifyEmail(token),
    retry: false,
    staleTime: Infinity,
    gcTime: Infinity,
  });

  return (
    <div className="login-wrap">
      <div className="login-card">
        {verify.isLoading && <p className="muted">Vérification en cours…</p>}
        {verify.isError && (
          <>
            <h1 className="login-title">Lien invalide</h1>
            <p className="login-sub">Ce lien de vérification est invalide ou a expiré.</p>
            <Link to="/" className="btn login-submit" style={{ textAlign: "center" }}>Retour à l'accueil</Link>
          </>
        )}
        {verify.isSuccess && (
          <>
            <h1 className="login-title">✅ Email vérifié</h1>
            <p className="login-sub">
              Ton compte <strong>{verify.data.username}</strong> est activé. Tu peux maintenant te connecter.
            </p>
            <Link to="/" className="btn primary login-submit" style={{ textAlign: "center" }}>Se connecter</Link>
          </>
        )}
      </div>
    </div>
  );
}
