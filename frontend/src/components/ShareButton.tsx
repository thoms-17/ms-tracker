import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../api";
import { useSocial, useSocialAction } from "../social";
import Modal from "./Modal";
import ShareActions from "./ShareActions";

/**
 * « Regarder avec… » sur la page d'une série suivie : avec qui elle est partagée,
 * et une fenêtre pour inviter un ami (ou répondre à son invitation).
 */
export default function ShareButton({ tmdbId }: { tmdbId: number }) {
  const [open, setOpen] = useState(false);
  const shares = useQuery({ queryKey: ["shares", tmdbId], queryFn: () => api.seriesShares(tmdbId) });
  const actifs = (shares.data ?? []).filter((s) => s.status === "accepted");
  const avec = actifs.map((s) => s.username).join(", ");
  const enPause = actifs.length > 0 && actifs.every((s) => s.paused);
  return (
    <>
      <button className="btn" onClick={() => setOpen(true)}>
        👥 {avec ? `Avec ${avec}${enPause ? " · en pause" : ""}` : "Regarder avec…"}
      </button>
      {open && <ShareModal tmdbId={tmdbId} onClose={() => setOpen(false)} />}
    </>
  );
}

function ShareModal({ tmdbId, onClose }: { tmdbId: number; onClose: () => void }) {
  const social = useSocial();
  const shares = useQuery({ queryKey: ["shares", tmdbId], queryFn: () => api.seriesShares(tmdbId) });
  const invite = useSocialAction((friendId: number) => api.inviteToShare(tmdbId, friendId),
    "Échec — invitation non envoyée");

  const friends = social.data?.friends ?? [];
  const byFriend = new Map((shares.data ?? []).map((s) => [s.user_id, s]));

  return (
    <Modal onClose={onClose}>
      <h3 className="modal-title">Regarder avec un ami</h3>
      <p className="muted">
        Chaque épisode coché par l'un de vous sera aussi coché pour l'autre, sauf s'il l'a déjà
        vu dans son passage en cours. Décocher reste personnel. « Pause » : chacun avance seul.
      </p>
      {friends.length === 0 ? (
        <p className="muted">
          Tu n'as pas encore d'ami. <Link to="/amis" onClick={onClose}>Ajouter un ami</Link>
        </p>
      ) : (
        <div className="share-list">
          {friends.map((f) => {
            const sh = byFriend.get(f.user_id);
            return (
              <div className="friend-row" key={f.user_id}>
                <span className="avatar">{f.username.slice(0, 1).toUpperCase()}</span>
                <span className="friend-name">
                  {f.username}
                  {sh?.status === "accepted" && <span className="muted"> · {sh.paused ? "en pause" : "ensemble"}</span>}
                  {sh?.status === "pending" && (
                    <span className="muted"> · {sh.incoming ? "t'invite" : "invitation envoyée"}</span>
                  )}
                </span>
                <span className="friend-actions">
                  {sh ? (
                    <ShareActions sh={{ ...sh, pending: sh.status === "pending" }} />
                  ) : (
                    <button className="btn primary" disabled={invite.isPending}
                      onClick={() => invite.mutate(f.user_id)}>Inviter</button>
                  )}
                </span>
              </div>
            );
          })}
        </div>
      )}
      <div className="modal-actions">
        <button className="btn" onClick={onClose}>Fermer</button>
      </div>
    </Modal>
  );
}
