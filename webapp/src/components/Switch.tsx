// iOS / Telegram-style toggle switch. A pill track with a sliding
// knob; the track fills with the accent color when on. Used for
// boolean settings (the "выключить / включить" affordance).
//
// ``presentational`` renders a non-interactive visual span (no nested
// button) when the whole surrounding row already handles the click.

import { haptic } from "../lib/telegram";

interface Props {
  checked: boolean;
  onChange?: (next: boolean) => void;
  disabled?: boolean;
  ariaLabel?: string;
  presentational?: boolean;
}

function Track({ checked }: { checked: boolean }) {
  return (
    <span
      className={
        "ease-apple relative inline-flex h-[31px] w-[51px] shrink-0 items-center rounded-full transition-colors duration-300 " +
        (checked ? "bg-tg-button" : "bg-tg-hint/30")
      }
    >
      <span
        className="inline-block h-[27px] w-[27px] rounded-full bg-tg-button-text shadow-bento transition-transform duration-300 ease-spring"
        style={{ transform: checked ? "translateX(22px)" : "translateX(2px)" }}
      />
    </span>
  );
}

export function Switch({
  checked,
  onChange,
  disabled = false,
  ariaLabel,
  presentational = false,
}: Props) {
  if (presentational) {
    return <Track checked={checked} />;
  }
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={ariaLabel}
      disabled={disabled}
      onClick={() => {
        if (disabled) return;
        haptic("select");
        onChange?.(!checked);
      }}
      className="ease-apple inline-flex shrink-0 disabled:opacity-50"
    >
      <Track checked={checked} />
    </button>
  );
}
