import { useEffect, useRef, type ReactNode } from "react";

export function LifecycleDialog({
  title,
  onDismiss,
  children,
  returnFocus,
}: {
  title: string;
  onDismiss: () => void;
  children: ReactNode;
  returnFocus?: HTMLElement | null;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const previous = returnFocus ?? document.activeElement;
    const dialog = ref.current;
    if (dialog?.showModal) dialog.showModal();
    else dialog?.setAttribute("open", "");
    return () => {
      if (dialog?.close) dialog.close();
      if (previous instanceof HTMLElement) previous.focus();
    };
  }, [returnFocus]);
  return (
    <dialog
      ref={ref}
      aria-label={title}
      onCancel={(event) => {
        event.preventDefault();
        onDismiss();
      }}
    >
      {children}
    </dialog>
  );
}
