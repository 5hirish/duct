import LocalBackendGate from "../../components/LocalBackendGate.jsx";

// Outside the (app) group for the invitation page's reason: the person an
// agent sends here is often signed out, and must see who is asking before
// anything asks them to sign in. Gated like every page that reaches a backend.
export default function AuthorizeLayout({ children }) {
  return <LocalBackendGate>{children}</LocalBackendGate>;
}
