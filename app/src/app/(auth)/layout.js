import LocalBackendGate from "../../components/LocalBackendGate.jsx";

// Sign-in builds its OAuth authorize URL from the API base, so the base has to
// be settled before this subtree renders — in the desktop shell that means
// waiting for the bundled backend to report its port.
export default function AuthLayout({ children }) {
  return <LocalBackendGate>{children}</LocalBackendGate>;
}
