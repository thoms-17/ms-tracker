import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { api, ApiError, posterUrl } from "../api";
import BackLink from "../components/BackLink";
import ShareActions from "../components/ShareActions";
import Spinner from "../components/Spinner";
import { useSocial, useSocialAction } from "../social";
import type { Person, ShareItem } from "../types";

/**
 * Amis et visionnages partagés : ajouter un ami par son pseudo, répondre aux
 * demandes et aux invitations, arrêter un partage.
 */
export default function Friends() {
  const social = useSocial();
  const accept = useSocialAction(api.acceptFriend, "Échec — demande non acceptée");
  const remove = useSocialAction(api.removeFriend, "Échec — action non enregistrée");

  if (social.isLoading) return <Spinner />;
  const s = social.data;
  if (!s) return <p className="muted">Impossible de charger tes amis.</p>;

  return (
    <div className="friends-page">
      <BackLink />
      <h2>Amis</h2>
      <AddFriend />

      {s.incoming.length > 0 && (
        <section>
          <h3 className="section-title">Demandes reçues</h3>
          {s.incoming.map((p) => (
            <PersonRow key={p.user_id} p={p}>
              <button className="btn primary" onClick={() => accept.mutate(p.user_id)}>Accepter</button>
              <button className="btn" onClick={() => remove.mutate(p.user_id)}>Refuser</button>
            </PersonRow>
          ))}
        </section>
      )}

      {s.share_invites.length > 0 && (
        <section>
          <h3 className="section-title">Invitations à regarder ensemble</h3>
          {s.share_invites.map((sh) => (
            <ShareRow key={sh.id} sh={sh} label={<><strong>{sh.username}</strong> t'invite</>}>
              <ShareActions sh={{ ...sh, pending: true, incoming: true }} />
            </ShareRow>
          ))}
        </section>
      )}

      <section>
        <h3 className="section-title">Mes amis ({s.friends.length})</h3>
        {s.friends.length === 0 ? (
          <p className="muted">Ajoute un ami avec son pseudo pour regarder des séries ensemble.</p>
        ) : s.friends.map((p) => (
          <PersonRow key={p.user_id} p={p}>
            <ConfirmButton label="Retirer" onConfirm={() => remove.mutate(p.user_id)}
              question={`Retirer ${p.username} ? Vos visionnages partagés s'arrêteront.`} />
          </PersonRow>
        ))}
        {s.outgoing.map((p) => (
          <PersonRow key={p.user_id} p={p} note="demande envoyée">
            <button className="btn" onClick={() => remove.mutate(p.user_id)}>Annuler</button>
          </PersonRow>
        ))}
      </section>

      {s.shared.length > 0 && (
        <section>
          <h3 className="section-title">Regardées ensemble</h3>
          <p className="muted friends-hint">
            Chaque épisode coché par l'un est aussi coché pour l'autre, sauf s'il l'a déjà vu
            dans son passage en cours. Décocher reste personnel. « Pause » : chacun avance seul.
          </p>
          {s.shared.map((sh) => (
            <ShareRow key={sh.id} sh={sh}
              label={<>avec <strong>{sh.username}</strong>{sh.paused && " · en pause"}</>}>
              <ShareActions sh={{ ...sh, pending: false, incoming: false }} />
            </ShareRow>
          ))}
        </section>
      )}
    </div>
  );
}

function AddFriend() {
  const [pseudo, setPseudo] = useState("");
  const [message, setMessage] = useState<{ ok: boolean; texte: string } | null>(null);
  const add = useSocialAction(api.requestFriend, "");

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const nom = pseudo.trim();
    if (!nom) return;
    setMessage(null);
    add.mutate(nom, {
      onSuccess: (res) => {
        setPseudo("");
        setMessage({ ok: true, texte: (res as { status: string }).status === "accepted"
          ? `${nom} t'avait déjà demandé : vous êtes amis !` : `Demande envoyée à ${nom}.` });
      },
      // Le refus (pseudo inconnu, déjà amis…) s'affiche sous le champ, pas en toast.
      onError: (err) => setMessage({ ok: false, texte: err instanceof ApiError ? err.message : "Échec de l'envoi" }),
    });
  };

  return (
    <form className="friend-add" onSubmit={submit}>
      <input
        value={pseudo} onChange={(e) => setPseudo(e.target.value)} placeholder="Pseudo de ton ami"
        autoCapitalize="none" autoCorrect="off" spellCheck={false} aria-label="Pseudo de ton ami"
      />
      <button className="btn primary" type="submit" disabled={add.isPending || !pseudo.trim()}>Ajouter</button>
      {message && <p className={message.ok ? "friend-msg muted" : "friend-msg error"}>{message.texte}</p>}
    </form>
  );
}

function PersonRow({ p, note, children }: { p: Person; note?: string; children: React.ReactNode }) {
  return (
    <div className="friend-row">
      <span className="avatar">{p.username.slice(0, 1).toUpperCase()}</span>
      <span className="friend-name">{p.username}{note && <span className="muted"> · {note}</span>}</span>
      <span className="friend-actions">{children}</span>
    </div>
  );
}

function ShareRow({ sh, label, children }: { sh: ShareItem; label: React.ReactNode; children: React.ReactNode }) {
  const url = posterUrl(sh.poster_path);
  return (
    <div className="friend-row">
      {/* L'aperçu TMDB bascule sur la page de la série si elle est déjà suivie. */}
      <Link to={`/tmdb/tv/${sh.tmdb_id}`} className="friend-share">
        {url ? <img src={url} alt="" /> : <span className="friend-poster-empty" />}
        <span className="friend-name">
          {sh.title}<br /><span className="muted">{label}</span>
        </span>
      </Link>
      <span className="friend-actions">{children}</span>
    </div>
  );
}

/** Bouton d'une action qui casse un lien : demande confirmation avant d'agir. */
function ConfirmButton({ label, question, onConfirm }: { label: string; question: string; onConfirm: () => void }) {
  return (
    <button className="btn" onClick={() => window.confirm(question) && onConfirm()}>{label}</button>
  );
}
