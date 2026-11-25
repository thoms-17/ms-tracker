import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../api";
import { useCloseOnScroll } from "../hooks";
import { clearPersistedCache } from "../persist";
import { pendingCount, useSocial } from "../social";
import VersionInfo from "./VersionInfo";

/** Pastille du profil connecté + menu (amis, déconnexion). */
export default function UserMenu({ username }: { username: string }) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const nav = useNavigate();
  // Demandes d'ami et invitations reçues : pastille sur l'avatar et dans le menu.
  const enAttente = pendingCount(useSocial().data);
  const logout = useMutation({
    mutationFn: api.logout,
    onSuccess: () => {
      qc.setQueryData(["me"], null); // repasse au login
      qc.clear(); // vide le cache mémoire (données de l'utilisateur précédent)
      clearPersistedCache(); // …et sa copie sur l'appareil, sinon elle survivrait
    },
  });

  // Popover ancré à l'avatar : un défilement le décrocherait de son bouton.
  useCloseOnScroll(() => setOpen(false), open);

  return (
    <div className="usermenu">
      <button
        className="usermenu-btn" onClick={() => setOpen((o) => !o)}
        aria-haspopup="menu" aria-expanded={open} title={username}
      >
        <span className="avatar">{username.slice(0, 1).toUpperCase()}</span>
        {enAttente > 0 && <span className="notif-dot" aria-label={`${enAttente} en attente`} />}
        <span className="usermenu-name">{username}</span>
      </button>
      {open && (
        <>
          <div className="menu-backdrop" onClick={() => setOpen(false)} />
          <div className="usermenu-pop" role="menu">
            <div className="usermenu-head">
              Connecté en tant que<br /><strong>{username}</strong>
            </div>
            <button className="menu-item" role="menuitem" onClick={() => { setOpen(false); nav("/amis"); }}>
              Amis{enAttente > 0 && <span className="notif-count">{enAttente}</span>}
            </button>
            <button
              className="menu-item danger" disabled={logout.isPending}
              onClick={() => logout.mutate()}
            >
              Se déconnecter
            </button>
            <VersionInfo />
          </div>
        </>
      )}
    </div>
  );
}
