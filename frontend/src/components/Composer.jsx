import { useEffect, useRef } from "react";
import Icon from "./Icon";

const MAX_LENGTH = 500;

export default function Composer({
  value,
  onChange,
  onSend,
  onStop,
  sending,
  editing,
  onCancelEdit,
  inputRef,
}) {
  const fallbackRef = useRef(null);
  const ref = inputRef || fallbackRef;

  // Grow with the content, up to about six lines, then scroll.
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }, [value, ref]);

  function handleKeyDown(event) {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      onSend();
    }
  }

  const nearLimit = value.length > MAX_LENGTH - 80;

  return (
    <form
      className="composer"
      onSubmit={(event) => {
        event.preventDefault();
        onSend();
      }}
    >
      {editing && (
        <div className="composer-editing">
          <span>Editing your last question</span>
          <button type="button" className="text-button" onClick={onCancelEdit}>
            Cancel
          </button>
        </div>
      )}
      <div className="composer-box">
        <textarea
          ref={ref}
          rows={1}
          value={value}
          maxLength={MAX_LENGTH}
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask a question about your data"
          aria-label="Your question"
          readOnly={sending}
          aria-busy={sending}
        />
        {nearLimit && (
          <span className="composer-count">
            {value.length}/{MAX_LENGTH}
          </span>
        )}
        {sending ? (
          <button
            type="button"
            className="composer-button composer-stop"
            onClick={onStop}
            aria-label="Stop"
          >
            <Icon name="stop" />
          </button>
        ) : (
          <button
            type="submit"
            className="composer-button"
            disabled={!value.trim()}
            aria-label="Send"
          >
            <Icon name="send" />
          </button>
        )}
      </div>
      <p className="composer-hint">Enter to send · Shift+Enter for a new line</p>
    </form>
  );
}
