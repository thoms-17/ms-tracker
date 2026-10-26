import Modal from "./Modal";

/**
 * « Rattraper les épisodes précédents ? » — proposé quand on coche un épisode
 * alors que des épisodes réguliers le précédant ne sont pas vus (série suivie
 * ou aperçu d'une série pas encore suivie).
 *
 * `before` : nombre d'épisodes non vus avant `code` ; `seasons` : combien de
 * saisons précédentes ils traversent (0 = tous dans la même saison).
 */
export default function CatchUpModal({ code, before, seasons, onOnlyThis, onCatchUp, onClose }: {
  code: string;
  before: number;
  seasons: number;
  onOnlyThis: () => void;
  onCatchUp: () => void;
  onClose: () => void;
}) {
  const pluriel = before > 1;
  return (
    <Modal onClose={onClose}>
      <h3 className="modal-title">Rattraper les épisodes précédents ?</h3>
      <p className="muted">
        {before} épisode{pluriel ? "s" : ""} avant {code} {pluriel ? "ne sont pas vus" : "n'est pas vu"}
        {seasons > 0 && (
          <>, dont {seasons > 1 ? `ceux de ${seasons} saisons précédentes` : "ceux de la saison précédente"}</>
        )}.
        {" "}Veux-tu {pluriel ? "les" : "l'"} marquer comme vu{pluriel ? "s" : ""} aussi ?
      </p>
      <div className="modal-actions">
        <button className="btn" onClick={() => { onOnlyThis(); onClose(); }}>
          Seulement {code}
        </button>
        <button className="btn primary" onClick={() => { onCatchUp(); onClose(); }}>
          Marquer les {before + 1} épisodes
        </button>
      </div>
    </Modal>
  );
}
