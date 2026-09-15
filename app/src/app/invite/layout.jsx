import LocalBackendGate from "../../components/LocalBackendGate.jsx";

// An invitation is accepted against a backend, and in the desktop shell that
// backend is the bundled sidecar on a port known only at runtime. Without this
// the page called the *hosted* API with the shell's sidecar session, and
// `membersApi` turns that 401 into a sign-out (`endSessionIfUnauthorized`) —
// the invited user is bounced to the front door instead of into the project.
export default function InviteLayout({ children }) {
  return <LocalBackendGate>{children}</LocalBackendGate>;
}
