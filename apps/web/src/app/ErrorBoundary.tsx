import { Component, type ReactNode } from "react";
import { ErrorState } from "../components/ui";

/** Catches render errors so one broken view never blanks the whole app. */
export class ErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null };
  static getDerivedStateFromError(error: Error) { return { error }; }
  render() {
    if (this.state.error) return <ErrorState title="This view failed to render" error={this.state.error} onRetry={() => this.setState({ error: null })} />;
    return this.props.children;
  }
}
