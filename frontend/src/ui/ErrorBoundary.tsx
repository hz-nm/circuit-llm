import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
  /** Changing this key clears a caught error (e.g. when the user picks another version). */
  resetKey?: unknown;
  label?: string;
}

interface State {
  error: Error | null;
  resetKey: unknown;
}

export class ErrorBoundary extends Component<Props, State> {
  override state: State = { error: null, resetKey: this.props.resetKey };

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { error };
  }

  static getDerivedStateFromProps(props: Props, state: State): Partial<State> | null {
    return props.resetKey !== state.resetKey ? { error: null, resetKey: props.resetKey } : null;
  }

  override componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error("Workspace error", error, info.componentStack);
  }

  override render(): ReactNode {
    const { error } = this.state;
    if (!error) return this.props.children;
    return (
      <div role="alert" className="m-4 rounded-lg border border-danger/40 bg-danger-soft p-4 text-sm">
        <p className="font-semibold text-danger">{this.props.label ?? "This view crashed."}</p>
        <pre className="mt-2 whitespace-pre-wrap font-mono text-xs text-muted">{error.message}</pre>
        <button
          type="button"
          className="mt-3 rounded-md border border-line bg-panel px-3 py-1 text-xs hover:bg-sunken"
          onClick={() => this.setState({ error: null })}
        >
          Try again
        </button>
      </div>
    );
  }
}
