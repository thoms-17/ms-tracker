import { useEffect, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { useCloseOnScroll } from "../hooks";

/** Boîte de dialogue centrée, rendue dans un portail sur <body>. */
export default function Modal({ onClose, children }: { onClose: () => void; children: ReactNode }) {
  useEffect(() => {
    const onKey = (ev: KeyboardEvent) => ev.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  useCloseOnScroll(onClose);

  return createPortal(
    <div className="modal-layer" onClick={onClose}>
      <div className="modal" role="dialog" aria-modal="true" onClick={(ev) => ev.stopPropagation()}>
        {children}
      </div>
    </div>,
    document.body,
  );
}
