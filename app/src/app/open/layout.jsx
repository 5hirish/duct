import LocalBackendGate from "../../components/LocalBackendGate.jsx";

// Resuming a shared audit reads the session and then hands off into the app,
// so it has to agree with the app about which backend minted that session.
// See `lib/localBackend.js` for why the base is not known until boot.
export default function OpenLayout({ children }) {
  return <LocalBackendGate>{children}</LocalBackendGate>;
}
