import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { TOAST_EVENT } from "../toast";

type Message = { id: number; texte: string };
const DUREE = 4000;

/**
 * Messages d'échec discrets, empilés en bas de l'écran.
 *
 * Nécessaire depuis la mise à jour optimiste : le compteur monte au clic puis
 * redescend si l'écriture échoue. Sans ce message, l'annulation passerait
 * inaperçue et l'utilisateur croirait son visionnage enregistré.
 */
export default function Toast() {
  const [messages, setMessages] = useState<Message[]>([]);

  useEffect(() => {
    const onToast = (e: Event) => {
      const texte = (e as CustomEvent<string>).detail;
      const id = Date.now() + Math.random();
      setMessages((m) => [...m, { id, texte }]);
      setTimeout(() => setMessages((m) => m.filter((x) => x.id !== id)), DUREE);
    };
    window.addEventListener(TOAST_EVENT, onToast);
    return () => window.removeEventListener(TOAST_EVENT, onToast);
  }, []);

  if (!messages.length) return null;
  return createPortal(
    <div className="toasts" role="status" aria-live="polite">
      {messages.map((m) => (
        <div className="toast" key={m.id}>{m.texte}</div>
      ))}
    </div>,
    document.body,
  );
}
