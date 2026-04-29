"use client";

import {
  useEffect,
  useRef,
  useState,
  type CSSProperties,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";

import { INFO_HINTS, type InfoHintKey } from "@/lib/info-hints";

type InfoHintProps =
  | {
      hint: InfoHintKey;
      text?: never;
      ariaLabel?: string;
    }
  | {
      text: string;
      hint?: never;
      content?: never;
      ariaLabel?: string;
    }
  | {
      content: ReactNode;
      text?: never;
      hint?: never;
      ariaLabel?: string;
    };

export default function InfoHint(props: InfoHintProps) {
  const content =
    props.hint !== undefined
      ? INFO_HINTS[props.hint]
      : "text" in props
        ? props.text
        : props.content;
  const [open, setOpen] = useState(false);
  const [popoverStyle, setPopoverStyle] = useState<CSSProperties>({});
  const buttonRef = useRef<HTMLButtonElement | null>(null);
  const popoverRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) return;

    function updatePosition() {
      const button = buttonRef.current;
      if (!button) return;

      const rect = button.getBoundingClientRect();
      const width = Math.min(248, Math.max(180, window.innerWidth - 32));
      const left = Math.min(
        window.innerWidth - width - 16,
        Math.max(16, rect.right - width + 10),
      );
      const top = Math.min(window.innerHeight - 16, rect.bottom + 10);

      setPopoverStyle({
        top: `${top}px`,
        left: `${left}px`,
        width: `${width}px`,
      });
    }

    function handlePointerDown(event: MouseEvent | TouchEvent) {
      const target = event.target as Node | null;
      if (!target) return;
      if (buttonRef.current?.contains(target)) return;
      if (popoverRef.current?.contains(target)) return;
      setOpen(false);
    }

    function handleEscape(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setOpen(false);
      }
    }

    updatePosition();
    window.addEventListener("resize", updatePosition);
    window.addEventListener("scroll", updatePosition, true);
    document.addEventListener("mousedown", handlePointerDown);
    document.addEventListener("touchstart", handlePointerDown);
    document.addEventListener("keydown", handleEscape);

    return () => {
      window.removeEventListener("resize", updatePosition);
      window.removeEventListener("scroll", updatePosition, true);
      document.removeEventListener("mousedown", handlePointerDown);
      document.removeEventListener("touchstart", handlePointerDown);
      document.removeEventListener("keydown", handleEscape);
    };
  }, [open]);

  return (
    <span
      className="mining-info-hint mining-info-hint--card"
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
    >
      <button
        type="button"
        className="mining-info-hint__button mining-info-hint__button--card"
        aria-label={props.ariaLabel || "Показать подсказку"}
        aria-expanded={open}
        ref={buttonRef}
        onClick={() => setOpen((prev) => !prev)}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
      >
        <InfoCircleIcon />
      </button>

      {open && typeof document !== "undefined"
        ? createPortal(
            <div
              ref={popoverRef}
              className="mining-info-hint__popover mining-info-hint__popover--floating"
              role="tooltip"
              style={popoverStyle}
            >
              {content}
            </div>,
            document.body,
          )
        : null}
    </span>
  );
}

function InfoCircleIcon() {
  return (
    <svg
      viewBox="0 0 16 16"
      aria-hidden="true"
      className="mining-info-hint__icon"
    >
      <circle cx="8" cy="8" r="6.3" fill="none" stroke="currentColor" strokeWidth="1.4" />
      <circle cx="8" cy="4.55" r="0.95" fill="currentColor" />
      <path
        d="M8 6.9v4.05"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
      />
    </svg>
  );
}
