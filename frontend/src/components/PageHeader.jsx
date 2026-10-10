import Icon from "./Icon";

/** The bar across the top of an admin page: the narrow-screen menu button,
 *  the page title and any page-level actions. */
export default function PageHeader({ title, onOpenRail, children }) {
  return (
    <header className="chat-bar page-bar">
      <button
        type="button"
        className="icon-button chat-menu"
        aria-label="Open conversations"
        onClick={onOpenRail}
      >
        <Icon name="menu" size={20} />
      </button>
      <h1 className="chat-title">{title}</h1>
      <div className="page-actions">{children}</div>
    </header>
  );
}
