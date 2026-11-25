import { useState } from "react";
import { api } from "../api";
import { useSocialAction } from "../social";
import Modal from "./Modal";

/** Ce qu'il faut savoir d'un partage pour proposer les bonnes actions. */
export type ShareState = {
  id: number;
  username: string;
  pending: boolean;   // invitation pas encore acceptée
  incoming: boolean;  // invitation reçue (sinon envoyée)
  paused: boolean;
  ahead: number;      // épisodes que l'ami a vus et pas moi
};

const pluriel = (n: number) => (n > 1 ? "s" : "");

/**
 * Boutons d'un partage, partagés par la page Amis et la fenêtre « Regarder avec » :
 * accepter (en proposant de se mettre au niveau), mettre en pause / reprendre,
 * se mettre au niveau, arrêter (ou refuser / annuler une invitation).
 */
export default function ShareActions({ sh }: { sh: ShareState }) {
  const [askAlign, setAskAlign] = useState(false);
  const accept = useSocialAction((align: boolean) => api.acceptShare(sh.id, align), "Échec — invitation non acceptée");
  const align = useSocialAction(() => api.alignShare(sh.id), "Échec — mise au niveau non enregistrée");
  const pause = useSocialAction((p: boolean) => api.pauseShare(sh.id, p), "Échec — partage non modifié");
  const end = useSocialAction(() => api.endShare(sh.id), "Échec — partage non modifié");

  if (sh.pending) {
    return (
      <>
        {sh.incoming && (
          <button className="btn primary" disabled={accept.isPending}
            onClick={() => (sh.ahead > 0 ? setAskAlign(true) : accept.mutate(false))}>Accepter</button>
        )}
        <button className="btn" onClick={() => end.mutate(undefined)}>{sh.incoming ? "Refuser" : "Annuler"}</button>
        {askAlign && (
          <Modal onClose={() => setAskAlign(false)}>
            <h3 className="modal-title">Partir du même point ?</h3>
            <p className="muted">
              {sh.username} a vu {sh.ahead} épisode{pluriel(sh.ahead)} que tu n'as pas vu{pluriel(sh.ahead)}.
              {" "}Veux-tu {sh.ahead > 1 ? "les" : "le"} marquer comme vu{pluriel(sh.ahead)} pour démarrer au même endroit ?
            </p>
            <div className="modal-actions">
              <button className="btn" onClick={() => { accept.mutate(false); setAskAlign(false); }}>
                Accepter seulement
              </button>
              <button className="btn primary" onClick={() => { accept.mutate(true); setAskAlign(false); }}>
                Me mettre au niveau
              </button>
            </div>
          </Modal>
        )}
      </>
    );
  }

  return (
    <>
      {sh.ahead > 0 && (
        <button className="btn" disabled={align.isPending}
          title={`Marquer comme vus les ${sh.ahead} épisodes que ${sh.username} a vus et pas toi`}
          onClick={() => window.confirm(
            `Marquer comme vu${pluriel(sh.ahead)} ${sh.ahead} épisode${pluriel(sh.ahead)} vu${pluriel(sh.ahead)} par ${sh.username} ?`,
          ) && align.mutate(undefined)}>
          Rattraper ({sh.ahead})
        </button>
      )}
      <button className="btn" disabled={pause.isPending} onClick={() => pause.mutate(!sh.paused)}
        title={sh.paused ? "Recocher chez l'autre ce que chacun coche" : "Avancer chacun de son côté, sans rien cocher chez l'autre"}>
        {sh.paused ? "Reprendre" : "Pause"}
      </button>
      <button className="btn" onClick={() => window.confirm(`Arrêter de regarder avec ${sh.username} ?`) && end.mutate(undefined)}>
        Arrêter
      </button>
    </>
  );
}
