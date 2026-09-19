import LocalBackendGate from "../../components/LocalBackendGate.jsx";
import LanguageMenu from "../../components/LanguageMenu.jsx";

// Sign-in builds its OAuth authorize URL from the API base, so the base has to
// be settled before this subtree renders — in the desktop shell that means
// waiting for the bundled backend to report its port.
export default function AuthLayout({ children }) {
  return (
    <LocalBackendGate>
      {/* The one control on the sign-in screen that is not sign-in. Someone
          who arrived in the wrong language has to be able to fix that before
          they can read anything else, so it sits where every app puts it. */}
      <div className="fixed right-3 top-3 z-20">
        <LanguageMenu compact />
      </div>
      {children}
    </LocalBackendGate>
  );
}
