"use client";

import { createContext, useContext, useState } from "react";

const AuditNavContext = createContext({ isAuditRunning: false, setIsAuditRunning: () => {} });

export function AuditNavProvider({ children }) {
  const [isAuditRunning, setIsAuditRunning] = useState(false);
  return (
    <AuditNavContext.Provider value={{ isAuditRunning, setIsAuditRunning }}>
      {children}
    </AuditNavContext.Provider>
  );
}

export function useAuditNav() {
  return useContext(AuditNavContext);
}
